"""Unit tests for backup_jobs_section pure helpers and layout shape."""
from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _clear_cache():
    from src.services import cache_service as cs

    cs.clear()
    yield


# Importing the module registers Dash callbacks as a side effect — Dash allows
# this only once per process. Pytest collection imports the module a single time,
# which is fine.
from src.components import backup_jobs_section as bjs  # noqa: E402


# ---- aggregate_series_by ----------------------------------------------------


def test_aggregate_series_by_status_buckets_per_period():
    series = [
        {"period": "2026-05-01", "status": "success", "job_type": "Full", "policy_type": "Daily", "count": 10},
        {"period": "2026-05-01", "status": "failed", "job_type": "Full", "policy_type": "Daily", "count": 2},
        {"period": "2026-05-01", "status": "success", "job_type": "Incr", "policy_type": "Hourly", "count": 5},
        {"period": "2026-05-02", "status": "success", "job_type": "Full", "policy_type": "Daily", "count": 7},
    ]
    out = bjs.aggregate_series_by(series, "status")
    assert out["2026-05-01"]["success"] == 15
    assert out["2026-05-01"]["failed"] == 2
    assert out["2026-05-02"]["success"] == 7
    assert "failed" not in out["2026-05-02"]


def test_aggregate_series_by_job_type():
    series = [
        {"period": "2026-05-01", "status": "success", "job_type": "Full", "count": 10},
        {"period": "2026-05-01", "status": "failed", "job_type": "Full", "count": 2},
        {"period": "2026-05-01", "status": "success", "job_type": "Incr", "count": 5},
    ]
    out = bjs.aggregate_series_by(series, "job_type")
    assert out["2026-05-01"]["Full"] == 12
    assert out["2026-05-01"]["Incr"] == 5


def test_aggregate_series_by_handles_missing_group_value():
    series = [
        {"period": "2026-05-01", "status": "success", "policy_type": None, "count": 3},
        {"period": "2026-05-01", "status": "success", "policy_type": "", "count": 2},
    ]
    out = bjs.aggregate_series_by(series, "policy_type")
    assert out["2026-05-01"]["Unknown"] == 5


def test_aggregate_series_by_empty_returns_empty_dict():
    assert bjs.aggregate_series_by([], "status") == {}
    assert bjs.aggregate_series_by(None, "status") == {}


# ---- build_figure -----------------------------------------------------------


def _payload(series):
    return {"vendor": "veeam", "granularity": "day", "range": {}, "series": series, "totals": {}}


def test_build_figure_empty_series_returns_placeholder():
    fig = bjs.build_figure(_payload([]), "status")
    assert fig.data == ()
    assert fig.layout.annotations  # placeholder text shown


def test_build_figure_status_orders_success_first():
    series = [
        {"period": "2026-05-01", "status": "failed", "count": 1},
        {"period": "2026-05-01", "status": "success", "count": 10},
        {"period": "2026-05-01", "status": "warning", "count": 2},
    ]
    fig = bjs.build_figure(_payload(series), "status")
    trace_names = [tr.name for tr in fig.data]
    # success → warning → failed (matches the priority order)
    assert trace_names.index("Success") < trace_names.index("Warning") < trace_names.index("Failed")


def test_build_figure_stacks_with_barmode():
    series = [
        {"period": "2026-05-01", "status": "success", "count": 10},
        {"period": "2026-05-01", "status": "failed", "count": 2},
    ]
    fig = bjs.build_figure(_payload(series), "status")
    assert fig.layout.barmode == "stack"


# ---- build_kpis -------------------------------------------------------------


def test_build_kpis_returns_four_cards():
    payload = {"totals": {"total": 1234, "success": 1200, "failed": 30, "warning": 4, "other": 0,
                          "success_rate": 97.3, "avg_per_period": 411.0, "period_count": 3}}
    kpis = bjs.build_kpis(payload)
    assert len(kpis) == 4


def test_build_kpis_handles_empty_totals():
    kpis = bjs.build_kpis({})
    assert len(kpis) == 4


# ---- build_job_stats_section ------------------------------------------------


def test_section_unknown_vendor_raises():
    with pytest.raises(ValueError):
        bjs.build_job_stats_section("unknown")


@pytest.mark.parametrize("vendor", ["zerto", "veeam", "netbackup"])
def test_section_layout_has_expected_ids(vendor):
    section = bjs.build_job_stats_section(vendor)
    # Render to string-ish: walk children recursively and collect ids
    found_ids = set()

    def _walk(node):
        if node is None:
            return
        if hasattr(node, "id") and getattr(node, "id", None):
            found_ids.add(node.id)
        children = getattr(node, "children", None)
        if isinstance(children, (list, tuple)):
            for c in children:
                _walk(c)
        elif children is not None:
            _walk(children)

    _walk(section)
    expected = {
        f"backup-jobs-{vendor}-granularity",
        f"backup-jobs-{vendor}-groupby",
        f"backup-jobs-{vendor}-kpis",
        f"backup-jobs-{vendor}-chart",
        f"backup-jobs-{vendor}-refresh",
        f"backup-jobs-{vendor}-asof",
        f"backup-jobs-{vendor}-loading",
    }
    assert expected.issubset(found_ids), f"missing ids: {expected - found_ids}"


# ---- _extract_dc_id ---------------------------------------------------------


@pytest.mark.parametrize(
    "pathname,expected",
    [
        ("/datacenter/DC13", "DC13"),
        ("/dc-detail/UZ11/", "UZ11"),
        ("/home", None),
        (None, None),
    ],
)
def test_extract_dc_id(pathname, expected):
    assert bjs._extract_dc_id(pathname) == expected


# ---- API wrapper dispatch ---------------------------------------------------


def test_api_wrapper_dispatch():
    from src.services import api_client as api

    assert bjs._api_wrapper("veeam") is api.get_dc_veeam_jobs
    assert bjs._api_wrapper("zerto") is api.get_dc_zerto_jobs
    assert bjs._api_wrapper("netbackup") is api.get_dc_netbackup_jobs


def test_api_wrapper_unknown_raises():
    with pytest.raises(ValueError):
        bjs._api_wrapper("foo")


# ---- format_as_of -----------------------------------------------------------


# ---- should_skip_fetch (lazy fetch gate) ------------------------------------


@pytest.mark.parametrize(
    "active_tab,dc_id,expected_skip",
    [
        ("backup", "DC13", False),       # En sıcak yol: tab aktif + DC seçili
        ("backup", "", True),            # DC bilinmiyor → skip
        ("backup", None, True),          # DC None → skip
        ("summary", "DC13", True),       # Backup tab kapalı → skip (ana lazy)
        ("virtualization", "DC13", True),
        ("storage", "DC13", True),
        ("availability", "DC13", True),
        ("phys-inv", "DC13", True),
        (None, "DC13", True),            # Tab değeri yok → skip
        ("", "DC13", True),              # Boş string → skip
    ],
)
def test_should_skip_fetch(active_tab, dc_id, expected_skip):
    assert bjs.should_skip_fetch(active_tab, dc_id) is expected_skip


@pytest.mark.parametrize(
    "vendor,category,category_tab,image_tab,replication_tab,expected_skip",
    [
        ("veeam", None, "image", None, None, True),
        ("veeam", None, "replication", None, "veeam", False),
        ("veeam", None, "replication", None, "zerto", True),
        ("zerto", None, "replication", None, "zerto", False),
        ("netbackup", "image", "image", "km", None, False),
        ("netbackup", "image", "image", "hc", None, True),
        ("netbackup", "application", "application", None, None, False),
        ("netbackup", "application", "image", None, None, True),
        # Store defaults: None category → image; None image → km
        ("veeam", None, None, None, None, True),
        ("netbackup", "image", None, None, None, False),
        ("zerto", None, None, None, None, True),
        ("zerto", None, "replication", None, None, False),
    ],
)
def test_should_skip_fetch_vendor_visibility(
    vendor, category, category_tab, image_tab, replication_tab, expected_skip
):
    assert bjs.should_skip_fetch(
        "backup",
        "DC13",
        vendor=vendor,
        category=category,
        backup_category_tab=category_tab,
        backup_image_tab=image_tab,
        backup_replication_tab=replication_tab,
    ) is expected_skip


@pytest.mark.parametrize(
    "value,expected_substring",
    [
        ("2026-05-14T14:35:00Z", "14:35"),
        ("2026-05-14T14:35:00+00:00", "14:35"),
        ("", ""),
        (None, ""),
        ("not-a-date", ""),
    ],
)
def test_format_as_of(value, expected_substring):
    out = bjs.format_as_of(value)
    if expected_substring == "":
        assert out == ""
    else:
        assert expected_substring in out
        assert out.startswith("· Son güncelleme:")


# ---- callback registration (mount gate) -------------------------------------


_NESTED_BACKUP_TAB_IDS = {
    "backup-category-tabs",
    "backup-image-tabs",
    "backup-replication-tabs",
}
_ALWAYS_PRESENT_BACKUP_INPUTS = {
    "backup-panels-ready",
    "backup-time-range",
    "backup-category-tab-store",
    "backup-image-tab-store",
    "backup-replication-tab-store",
}


def test_job_stats_callbacks_gate_on_backup_panels_ready():
    """DC job-stats must wait for Backup panel mount, not raw tab click."""
    from dash import _callback

    found = False
    for key, meta in _callback.GLOBAL_CALLBACK_MAP.items():
        if "backup-jobs-veeam-chart" not in str(key):
            continue
        input_ids = [i["id"] for i in meta["inputs"]]
        state_ids = [s["id"] for s in meta["state"]]
        assert "backup-panels-ready" in input_ids
        assert "dc-main-tabs" not in input_ids
        assert "dc-main-tabs" in state_ids
        for store_id in (
            "backup-category-tab-store",
            "backup-image-tab-store",
            "backup-replication-tab-store",
        ):
            assert store_id in input_ids
        assert not (_NESTED_BACKUP_TAB_IDS & set(input_ids)), input_ids
        found = True
        break
    assert found, "veeam job-stats callback not registered"


def test_job_stats_callbacks_use_only_store_tab_inputs():
    """Nested Tabs must never be Inputs — they are lazy-mounted and cause IndexError."""
    from dash import _callback

    checked = 0
    for key, meta in _callback.GLOBAL_CALLBACK_MAP.items():
        if "backup-jobs-" not in str(key) or "-chart" not in str(key):
            continue
        input_ids = {i["id"] for i in meta["inputs"]}
        assert not (_NESTED_BACKUP_TAB_IDS & input_ids), (key, input_ids)
        assert _ALWAYS_PRESENT_BACKUP_INPUTS <= input_ids
        checked += 1
    assert checked >= 4, f"expected multiple job-stats callbacks, found {checked}"
