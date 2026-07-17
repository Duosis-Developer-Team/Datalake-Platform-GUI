"""Smoke tests for unique-jobs inventory panel helpers."""

from unittest.mock import patch

from src.components.backup_unique_jobs_panel import (
    _fetch_table_payload,
    build_unique_jobs_inventory_section,
    build_unique_jobs_visuals,
    unique_jobs_table,
)


def test_unique_jobs_table_renders_rows():
    items = [
        {"name": "Job-A", "type": "Backup", "status": "success", "source_ip": "10.0.0.1"},
    ]
    out = unique_jobs_table("veeam", items)
    assert out is not None


def test_build_unique_jobs_visuals_empty_totals():
    kpis, donut, status = build_unique_jobs_visuals({}, "veeam")
    assert kpis is not None
    assert donut is not None
    assert status is not None


def test_build_unique_jobs_inventory_section_layout():
    panel = build_unique_jobs_inventory_section(
        "veeam",
        scope="dc",
        initial={
            "rows": [
                {
                    "name": "Job-A",
                    "type": "Backup",
                    "status": "success",
                    "source_ip": "10.0.0.1",
                }
            ],
            "totals": {
                "total_jobs": 1,
                "by_status": {"success": 1},
                "by_type": {"Backup": 1},
            },
        },
    )
    assert panel is not None


def test_dc_unique_jobs_callbacks_defer_after_mount():
    """DC unique-jobs fetch on Interval (stampede guard), not raw tab click."""
    from dash import _callback

    found = False
    for key, meta in _callback.GLOBAL_CALLBACK_MAP.items():
        if "backup-uj-dc-veeam-kpis" not in str(key):
            continue
        input_ids = [i["id"] for i in meta["inputs"]]
        state_ids = [s["id"] for s in meta["state"]]
        assert "backup-uj-defer" in input_ids
        assert "backup-category-tabs" in input_ids
        assert "dc-main-tabs" not in input_ids
        assert "dc-main-tabs" in state_ids
        found = True
        break
    assert found, "veeam unique-jobs DC callback not registered"


def test_unscoped_netbackup_unique_jobs_callbacks_not_registered():
    from dash import _callback

    for key in _callback.GLOBAL_CALLBACK_MAP:
        sk = str(key)
        if "backup-uj-dc-netbackup-kpis" in sk and "image" not in sk and "application" not in sk:
            raise AssertionError(f"unscoped netbackup unique-jobs still registered: {sk}")
        if (
            "backup-uj-customer-netbackup-kpis" in sk
            and "image" not in sk
            and "application" not in sk
        ):
            raise AssertionError(f"unscoped customer netbackup unique-jobs still registered: {sk}")


def test_empty_multiselect_means_no_filter():
    """Empty MultiSelect ([] / None) must not become an empty-list filter."""
    with patch("src.components.backup_unique_jobs_panel.api") as api:
        api.get_dc_unique_jobs_table.return_value = {"items": [], "total": 0, "totals": {}}
        _fetch_table_payload(
            scope="dc",
            vendor="veeam",
            category=None,
            pathname="/dc/DC13",
            tr={"preset": "7d"},
            page=1,
            search="",
            statuses=[],
            types=[],
            platforms=[],
            active_tab="backup",
        )
        kwargs = api.get_dc_unique_jobs_table.call_args.kwargs
        assert kwargs["statuses"] is None
        assert kwargs["types"] is None
        assert kwargs["platforms"] is None

        api.get_dc_unique_jobs_table.reset_mock()
        _fetch_table_payload(
            scope="dc",
            vendor="netbackup",
            category="image",
            pathname="/dc/DC13",
            tr={"preset": "7d"},
            page=1,
            search="",
            statuses=[],
            types=[],
            platforms=None,
            active_tab="backup",
        )
        kwargs = api.get_dc_unique_jobs_table.call_args.kwargs
        assert kwargs["statuses"] is None
        assert kwargs["policy_types"] is None
        assert kwargs["types"] is None
