"""
Unit tests for the DC-scoped unique-job inventory (Backup & Replication table
view): row mappers, DC attribution, cached base set (SWR), paged/filtered
table, and the job-stats server-side filter helper.

No live DB required — `_get_connection`/`_run_rows` are stubbed per test.

Run:
    docker compose run --rm -v "$(pwd)/services/datacenter-api/tests:/app/tests" \
        datacenter-api pytest tests/test_unique_jobs_service.py -v
"""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from psycopg2 import OperationalError

from app.db.queries import backup as bq
from app.services import cache_service as cache
from app.services.dc_service import DatabaseService


def _make_service(dc_list=("DC13", "DC14")) -> DatabaseService:
    with patch("app.services.dc_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = DatabaseService()
    svc._dc_list = list(dc_list)

    @contextmanager
    def _fake_conn():
        yield MagicMock()

    svc._get_connection = _fake_conn
    return svc


# ---------------------------------------------------------------------------
# Row mappers
# ---------------------------------------------------------------------------


def test_map_veeam_unique_row_preserves_column_order():
    row = (
        "2026-05-01T00:00:00Z", "j1", "Bayraktar_6Hours_DR2", "VSphereReplica",
        "Success", "Success", "2026-05-01T00:00:00Z", 12, "s1", "vm", "10.34.2.104",
    )
    mapped = DatabaseService._map_veeam_unique_row(row)
    assert mapped == {
        "collection_time": "2026-05-01T00:00:00Z",
        "id": "j1",
        "name": "Bayraktar_6Hours_DR2",
        "type": "VSphereReplica",
        "status": "Success",
        "last_result": "Success",
        "last_run": "2026-05-01T00:00:00Z",
        "objects_count": 12,
        "session_id": "s1",
        "workload": "vm",
        "source_ip": "10.34.2.104",
    }


def test_map_zerto_unique_row_normalizes_status_enum():
    row = (
        "2026-05-01T00:00:00Z", "v1", "Cs_Smart_Message-App1", 1, 2,
        "DC14-Site02-V10", "TurksatDC_ZVM", 1000, 500, "10.50.9.18",
    )
    mapped = DatabaseService._map_zerto_unique_row(row)
    assert mapped["id"] == "v1"
    assert mapped["status"] == "success"  # 1 == MeetingSLA
    assert mapped["source_site"] == "DC14-Site02-V10"
    assert mapped["target_site"] == "TurksatDC_ZVM"
    assert mapped["zerto_host"] == "10.50.9.18"


@pytest.mark.parametrize("raw_status,expected", [(1, "success"), (2, "failed"), (0, "running"), (4, "warning")])
def test_map_zerto_unique_row_status_variants(raw_status, expected):
    row = ("t", "v1", "n", raw_status, 1, "s", "t", 0, 0, "h")
    assert DatabaseService._map_zerto_unique_row(row)["status"] == expected


def test_map_netbackup_unique_row_normalizes_status_and_adds_category():
    row = (
        "2026-05-01T00:00:00Z", "2026-05-01T01:00:00Z", "1", "vmware-daily", "VMWARE",
        "BACKUP", 0, "vm-web-01", "vm-web-01", "nbmediadc13.blt.vc", 1024, 2.5, 100,
    )
    mapped = DatabaseService._map_netbackup_unique_row(row)
    assert mapped["jobid"] == "1"
    assert mapped["status"] == "success"  # 0 == success
    assert mapped["policytype"] == "VMWARE"
    assert mapped["category"] == "image"  # VMWARE -> image
    assert mapped["destinationmediaservername"] == "nbmediadc13.blt.vc"


def test_map_netbackup_unique_row_application_category_and_warning_status():
    row = ("t1", "t2", "2", "sap-daily", "SAP", "BACKUP", 1, "wl", "c", "nbmediadc14.blt.vc", 10, 1.0, 100)
    mapped = DatabaseService._map_netbackup_unique_row(row)
    assert mapped["status"] == "warning"  # 1 == partial/warning
    assert mapped["category"] == "application"  # SAP -> application


# ---------------------------------------------------------------------------
# DC attribution — _fetch_dc_unique_jobs
# ---------------------------------------------------------------------------


def test_fetch_dc_unique_jobs_veeam_filters_by_source_ip_dc_map():
    svc = _make_service()
    veeam_rows = [
        ("t1", "j1", "Job1", "Backup", "Success", "Success", "t1", 1, "s1", "vm", "10.34.2.104"),
        ("t2", "j2", "Job2", "Backup", "Failed", "Failed", "t2", 1, "s2", "vm", "10.34.3.104"),
        ("t3", "j3", "Job3", "Backup", None, None, "t3", 1, "s3", "vm", "10.34.9.9"),  # no DC mapping
    ]
    seed_rows = [
        ("10.34.2.104", "Dc13-VeemConsule.blt.vc"),
        ("10.34.3.104", "Dc14-VeemConsule.blt.vc"),
    ]

    def fake_run_rows(cur, sql, params=None):
        if sql is bq.VEEAM_UNIQUE_JOBS_LATEST:
            return veeam_rows
        if sql is bq.VEEAM_IP_TO_DC_SEED:
            return seed_rows
        return []

    svc._run_rows = fake_run_rows
    out = svc._fetch_dc_unique_jobs("DC13", "veeam", "start", "end")
    assert [r["id"] for r in out["rows"]] == ["j1"]
    assert out["vendor"] == "veeam"
    assert out["totals"]["total_jobs"] == 1
    assert out["rows"][0]["status"] == "success"  # normalize_unique_job_rows lowercases


def test_fetch_dc_unique_jobs_zerto_prefers_source_site_falls_back_to_target_and_host():
    svc = _make_service()
    zerto_rows = [
        ("t1", "v1", "VPG1", 1, 2, "DC13-Site01", "DC14-Site02", 100, 50, "zh1"),
        # source_site has no DC code -> falls back to target_site (DC13)
        ("t2", "v2", "VPG2", 1, 1, "TurksatDC_ZVM", "DC13-Site01", 100, 50, "zh2"),
        ("t3", "v3", "VPG3", 1, 1, "DC14-Site02", "DC14-Site02", 100, 50, "zh3"),
    ]

    def fake_run_rows(cur, sql, params=None):
        if sql is bq.ZERTO_UNIQUE_VPGS_LATEST:
            return zerto_rows
        return []

    svc._run_rows = fake_run_rows
    out = svc._fetch_dc_unique_jobs("DC13", "zerto", "start", "end")
    assert {r["id"] for r in out["rows"]} == {"v1", "v2"}
    assert out["totals"]["by_type"] == {"vpg": 2}


def test_fetch_dc_unique_jobs_zerto_source_site_takes_priority_over_target():
    svc = _make_service()
    zerto_rows = [
        # source_site resolves to DC14 -> row belongs to DC14 even though target_site says DC13
        ("t1", "v1", "VPG1", 1, 1, "DC14-Site02", "DC13-Site01", 100, 50, "zh1"),
    ]

    def fake_run_rows(cur, sql, params=None):
        if sql is bq.ZERTO_UNIQUE_VPGS_LATEST:
            return zerto_rows
        return []

    svc._run_rows = fake_run_rows
    assert svc._fetch_dc_unique_jobs("DC13", "zerto", "start", "end")["rows"] == []
    assert [r["id"] for r in svc._fetch_dc_unique_jobs("DC14", "zerto", "start", "end")["rows"]] == ["v1"]


def test_fetch_dc_unique_jobs_netbackup_filters_by_media_server():
    svc = _make_service()
    nb_rows = [
        ("t1", "t2", "1", "pol1", "VMWARE", "BACKUP", 0, "wl1", "c1", "nbmediadc13.blt.vc", 100, 1.0, 100),
        ("t1", "t2", "2", "pol2", "SAP", "BACKUP", 1, "wl2", "c2", "nbmediadc14.blt.vc", 100, 1.0, 100),
    ]

    def fake_run_rows(cur, sql, params=None):
        if sql is bq.NETBACKUP_UNIQUE_JOBS_LATEST:
            return nb_rows
        return []

    svc._run_rows = fake_run_rows
    out = svc._fetch_dc_unique_jobs("DC13", "netbackup", "start", "end")
    assert [r["jobid"] for r in out["rows"]] == ["1"]
    assert out["rows"][0]["category"] == "image"
    assert out["totals"]["by_category"] == {"image": 1}


def test_fetch_dc_unique_jobs_unknown_vendor_returns_empty():
    svc = _make_service()
    svc._run_rows = lambda cur, sql, params=None: []
    out = svc._fetch_dc_unique_jobs("DC13", "bogus", "start", "end")
    assert out["rows"] == []
    assert out["vendor"] == "bogus"


# ---------------------------------------------------------------------------
# Cached base set (SWR) — get_dc_unique_jobs
# ---------------------------------------------------------------------------


def test_get_dc_unique_jobs_fresh_hit_skips_fetch():
    svc = _make_service()
    tr = {"start": "2026-04-01", "end": "2026-05-01", "preset": "custom"}
    key = "dc_veeam_unique_jobs:DC13:2026-04-01:2026-05-01"
    cache.delete(key)
    cache.delete(f"stale:{key}")
    fresh_payload = {"rows": [], "totals": {}, "as_of": "x", "vendor": "veeam"}
    cache.set_with_stale(key, fresh_payload, fresh_ttl=30, stale_ttl=600)

    with patch.object(svc, "_fetch_dc_unique_jobs") as p_fetch:
        out = svc.get_dc_unique_jobs("DC13", "veeam", tr)

    assert out == fresh_payload
    p_fetch.assert_not_called()


def test_get_dc_unique_jobs_stale_hit_triggers_async_refresh():
    svc = _make_service()
    tr = {"start": "2026-04-01", "end": "2026-05-01", "preset": "custom"}
    key = "dc_veeam_unique_jobs:DC13:2026-04-01:2026-05-01"
    cache.delete(key)
    cache.delete(f"stale:{key}")
    stale_payload = {"rows": [], "totals": {}, "as_of": "x", "vendor": "veeam"}
    cache.set_with_stale(key, stale_payload, fresh_ttl=30, stale_ttl=600)
    cache.delete(key)  # only stale remains

    with patch.object(svc, "_trigger_async_swr_refresh") as p_trigger:
        out = svc.get_dc_unique_jobs("DC13", "veeam", tr)

    assert out == stale_payload
    p_trigger.assert_called_once()
    _, kwargs = p_trigger.call_args
    assert kwargs["label"] == "dc_veeam_unique_jobs"


def test_get_dc_unique_jobs_total_miss_computes_synchronously():
    svc = _make_service()
    tr = {"start": "2026-04-01", "end": "2026-05-01", "preset": "custom"}
    key = "dc_veeam_unique_jobs:DC13:2026-04-01:2026-05-01"
    cache.delete(key)
    cache.delete(f"stale:{key}")
    computed = {"rows": [{"id": "j1"}], "totals": {"total_jobs": 1}, "as_of": "x", "vendor": "veeam"}

    with patch.object(svc, "_fetch_dc_unique_jobs", return_value=computed) as p_fetch:
        out = svc.get_dc_unique_jobs("DC13", "veeam", tr)

    assert out == computed
    p_fetch.assert_called_once()


# ---------------------------------------------------------------------------
# Paged/filtered table — get_dc_unique_jobs_table
# ---------------------------------------------------------------------------


def test_get_dc_unique_jobs_table_paginates_and_recomputes_filtered_totals():
    svc = _make_service()
    rows = [
        {"id": "j1", "name": "A", "type": "Backup", "status": "success"},
        {"id": "j2", "name": "B", "type": "Backup", "status": "failed"},
        {"id": "j3", "name": "C", "type": "Backup", "status": "success"},
    ]
    base = {"rows": rows, "totals": {"total_jobs": 3}, "as_of": "x", "vendor": "veeam"}

    with patch.object(svc, "get_dc_unique_jobs", return_value=base):
        out = svc.get_dc_unique_jobs_table(
            "DC13", "veeam", None, page=1, page_size=1, statuses=["success"],
        )

    assert out["vendor"] == "veeam"
    assert out["total"] == 2  # 2 success rows after filter, before pagination
    assert out["page_size"] == 1
    assert len(out["items"]) == 1
    assert out["totals"]["total_jobs"] == 2  # totals recomputed over the FILTERED set


def test_get_dc_unique_jobs_table_search_filters_by_name():
    svc = _make_service()
    rows = [
        {"id": "j1", "name": "Marubeni-App1", "type": "Backup", "status": "success"},
        {"id": "j2", "name": "KaleKilit-App1", "type": "Backup", "status": "success"},
    ]
    base = {"rows": rows, "totals": {}, "as_of": "x", "vendor": "veeam"}

    with patch.object(svc, "get_dc_unique_jobs", return_value=base):
        out = svc.get_dc_unique_jobs_table("DC13", "veeam", None, search="marubeni")

    assert [r["id"] for r in out["items"]] == ["j1"]
    assert out["total"] == 1


# ---------------------------------------------------------------------------
# Job-stats server-side filter — _filter_job_stats_payload
# ---------------------------------------------------------------------------


def _sample_veeam_job_stats_payload() -> dict:
    return {
        "vendor": "veeam",
        "granularity": "day",
        "range": {"start": "2026-04-01", "end": "2026-04-02"},
        "series": [
            {"period": "2026-04-01", "status": "success", "job_type": "Full", "policy_type": None, "count": 10},
            {"period": "2026-04-01", "status": "failed", "job_type": "Full", "policy_type": None, "count": 5},
            {"period": "2026-04-01", "status": "success", "job_type": "Incremental", "policy_type": None, "count": 8},
        ],
        "as_of": "x",
    }


def test_filter_job_stats_payload_noop_when_no_filters_given():
    payload = _sample_veeam_job_stats_payload()
    out = DatabaseService._filter_job_stats_payload(payload)
    assert out is payload


def test_filter_job_stats_payload_by_status_and_job_type():
    payload = _sample_veeam_job_stats_payload()
    out = DatabaseService._filter_job_stats_payload(payload, statuses=["success"], job_types=["Full"])
    assert len(out["series"]) == 1
    assert out["totals"]["total"] == 10
    assert out["vendor"] == "veeam"


def test_filter_job_stats_payload_status_is_case_insensitive():
    payload = _sample_veeam_job_stats_payload()
    out = DatabaseService._filter_job_stats_payload(payload, statuses=["SUCCESS"])
    assert out["totals"]["total"] == 18  # 10 + 8


def test_filter_job_stats_payload_category_is_noop_for_series_without_category_key():
    payload = _sample_veeam_job_stats_payload()  # veeam series has no "category" key
    out = DatabaseService._filter_job_stats_payload(payload, category="image")
    assert out["totals"]["total"] == 23  # unchanged: 10 + 5 + 8


def test_filter_job_stats_payload_category_filters_netbackup_series():
    payload = {
        "vendor": "netbackup",
        "granularity": "day",
        "range": {"start": "a", "end": "b"},
        "series": [
            {"period": "d1", "status": "success", "job_type": "BACKUP", "policy_type": "VMWARE",
             "category": "image", "count": 10},
            {"period": "d1", "status": "success", "job_type": "BACKUP", "policy_type": "SAP",
             "category": "application", "count": 4},
        ],
        "as_of": "x",
    }
    out = DatabaseService._filter_job_stats_payload(payload, category="image")
    assert out["totals"]["total"] == 10


def test_filter_job_stats_payload_by_policy_type():
    payload = {
        "vendor": "netbackup",
        "granularity": "day",
        "range": {},
        "series": [
            {"period": "d1", "status": "success", "job_type": "BACKUP", "policy_type": "VMWARE",
             "category": "image", "count": 10},
            {"period": "d1", "status": "success", "job_type": "BACKUP", "policy_type": "SAP",
             "category": "application", "count": 4},
        ],
        "as_of": "x",
    }
    out = DatabaseService._filter_job_stats_payload(payload, policy_types=["SAP"])
    assert out["totals"]["total"] == 4


# ---------------------------------------------------------------------------
# /jobs endpoints accept + apply the new filter kwargs (end-to-end via the
# public get_dc_*_jobs methods, cache pre-seeded so no DB access happens).
# ---------------------------------------------------------------------------


def test_get_dc_veeam_jobs_applies_status_filter_on_cache_hit():
    svc = _make_service()
    tr = {"start": "2026-04-01", "end": "2026-05-01", "preset": "custom"}
    key = "dc_veeam_jobs:DC13:2026-04-01:2026-05-01:day"
    cache.delete(key)
    cache.delete(f"stale:{key}")
    payload = _sample_veeam_job_stats_payload()
    payload["range"] = {"start": "2026-04-01", "end": "2026-05-01"}
    cache.set_with_stale(key, payload, fresh_ttl=30, stale_ttl=600)

    out = svc.get_dc_veeam_jobs("DC13", tr, "day", statuses=["failed"])
    assert out["totals"]["total"] == 5
