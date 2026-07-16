"""Unit tests for shared.backup.unique_jobs (pure, no DB)."""
from __future__ import annotations

from shared.backup.unique_jobs import (
    aggregate_unique_jobs,
    filter_unique_job_rows,
    normalize_unique_job_row,
    normalize_unique_job_rows,
    paginate_rows,
)


# ---------------------------------------------------------------------------
# Fixtures — one small row set per vendor, shaped like the *_UNIQUE_*_LATEST
# SQL queries mapped to dicts (see services/datacenter-api/app/db/queries/backup.py).
# ---------------------------------------------------------------------------

def _veeam_rows():
    return [
        {"id": "j1", "name": "Bayraktar_6Hours_DR2", "type": "VSphereReplica",
         "status": "Success", "last_result": "Success", "workload": "vm",
         "source_ip": "10.34.2.104"},
        {"id": "j2", "name": "KaleKilit_FortiAnalyzer", "type": "Backup",
         "status": "Failed", "last_result": "Failed", "workload": "vm",
         "source_ip": "10.34.2.104"},
        {"id": "j3", "name": "Marubeni-TIMSAPPRD01new", "type": "Backup",
         "status": "Warning", "last_result": "Warning", "workload": "vm",
         "source_ip": "10.34.2.105"},
        {"id": "j4", "name": "Marubeni-Extra", "type": "Backup",
         "status": None, "last_result": None, "workload": "vm",
         "source_ip": "10.34.2.105"},
    ]


def _zerto_rows():
    return [
        {"id": "v1", "name": "Cs_Smart_Message-App1", "status": 1, "vmscount": 2,
         "source_site": "DC14-Site02-V10", "target_site": "TurksatDC_ZVM",
         "zerto_host": "10.50.9.18"},
        {"id": "v2", "name": "Cs_Smart_Message-App2", "status": 2, "vmscount": 1,
         "source_site": "DC14-Site02-V10", "target_site": "TurksatDC_ZVM",
         "zerto_host": "10.50.9.18"},
        {"id": "v3", "name": "Alisan-App1", "status": 1, "vmscount": 3,
         "source_site": "DC13-Site01", "target_site": "DC14-Site02",
         "zerto_host": "10.50.9.19"},
    ]


def _netbackup_rows():
    return [
        {"jobid": "1", "policyname": "abc-dete-bw-dev-catalog", "policytype": "SAP",
         "jobtype": "BACKUP", "status": 0, "workloaddisplayname": "abc-dete-bw-dev",
         "clientname": "abc-dete-bw-dev", "destinationmediaservername": "nbmediadc14.blt.vc"},
        {"jobid": "2", "policyname": "vmware-daily", "policytype": "VMWARE",
         "jobtype": "BACKUP", "status": 1, "workloaddisplayname": "vm-web-01",
         "clientname": "vm-web-01", "destinationmediaservername": "nbmediadc13.blt.vc"},
        {"jobid": "3", "policyname": "vmware-daily", "policytype": "VMWARE",
         "jobtype": "BACKUP", "status": 6, "workloaddisplayname": "vm-web-02",
         "clientname": "vm-web-02", "destinationmediaservername": "nbmediadc13.blt.vc"},
        {"jobid": "4", "policyname": "sql-backup", "policytype": None,
         "jobtype": "BACKUP", "status": 0, "workloaddisplayname": "sql-01",
         "clientname": "sql-01", "destinationmediaservername": "nbmediadc14.blt.vc"},
    ]


# ---------------------------------------------------------------------------
# normalize_unique_job_row(s)
# ---------------------------------------------------------------------------

def test_normalize_lowercases_status_and_preserves_other_fields():
    row = {"id": "j1", "name": "Foo", "status": "Success"}
    out = normalize_unique_job_row(row)
    assert out["status"] == "success"
    assert out["name"] == "Foo"
    assert row["status"] == "Success"  # original untouched


def test_normalize_missing_status_becomes_unknown():
    assert normalize_unique_job_row({"id": "j1"})["status"] == "unknown"


def test_normalize_rows_bulk():
    rows = [{"status": "FAILED"}, {"status": None}]
    out = normalize_unique_job_rows(rows)
    assert [r["status"] for r in out] == ["failed", "unknown"]


def test_normalize_rows_empty_list():
    assert normalize_unique_job_rows([]) == []
    assert normalize_unique_job_rows(None) == []


# ---------------------------------------------------------------------------
# aggregate_unique_jobs
# ---------------------------------------------------------------------------

def test_aggregate_veeam_by_status_and_type():
    agg = aggregate_unique_jobs(_veeam_rows(), "veeam")
    assert agg["total_jobs"] == 4
    assert agg["by_status"] == {"success": 1, "failed": 1, "warning": 1, "unknown": 1}
    assert agg["by_type"] == {"VSphereReplica": 1, "Backup": 3}
    assert "by_category" not in agg
    assert "by_policy_type" not in agg


def test_aggregate_zerto_collapses_type_to_vpg_bucket():
    agg = aggregate_unique_jobs(_zerto_rows(), "zerto")
    assert agg["total_jobs"] == 3
    assert agg["by_type"] == {"vpg": 3}
    # Zerto status is a raw int enum in this generic aggregator (vendor-specific
    # normalization to success/failed happens upstream in dc_service); we only
    # lowercase whatever is present.
    assert agg["by_status"] == {"1": 2, "2": 1}


def test_aggregate_netbackup_includes_category_and_policy_type():
    agg = aggregate_unique_jobs(_netbackup_rows(), "netbackup")
    assert agg["total_jobs"] == 4
    assert agg["by_policy_type"] == {"SAP": 1, "VMWARE": 2, "Unknown": 1}
    assert agg["by_category"] == {"application": 2, "image": 2}
    # jobtype is constant 'BACKUP' post-filter — degenerate but shape-consistent.
    # (by_type preserves original casing; only `status` is lowercased.)
    assert agg["by_type"] == {"BACKUP": 4}


def test_aggregate_empty_rows():
    for vendor in ("veeam", "zerto", "netbackup"):
        agg = aggregate_unique_jobs([], vendor)
        assert agg["total_jobs"] == 0
        assert agg["by_status"] == {}
        assert agg["by_type"] == {}


def test_aggregate_unknown_vendor_falls_back_gracefully():
    agg = aggregate_unique_jobs([{"status": "ok"}], "unknown-vendor")
    assert agg["total_jobs"] == 1
    assert agg["by_type"] == {"unknown": 1}
    assert "by_category" not in agg


def test_aggregate_none_rows_treated_as_empty():
    agg = aggregate_unique_jobs(None, "veeam")
    assert agg["total_jobs"] == 0


# ---------------------------------------------------------------------------
# filter_unique_job_rows
# ---------------------------------------------------------------------------

def test_filter_no_filters_returns_all():
    rows = _veeam_rows()
    assert filter_unique_job_rows(rows) == rows


def test_filter_search_matches_name_case_insensitive():
    out = filter_unique_job_rows(_veeam_rows(), search="marubeni")
    assert {r["id"] for r in out} == {"j3", "j4"}


def test_filter_search_no_match_returns_empty():
    assert filter_unique_job_rows(_veeam_rows(), search="nonexistent-xyz") == []


def test_filter_by_statuses_multi_value():
    out = filter_unique_job_rows(_veeam_rows(), statuses=["success", "warning"])
    assert {r["id"] for r in out} == {"j1", "j3"}


def test_filter_by_statuses_is_case_insensitive():
    out = filter_unique_job_rows(_veeam_rows(), statuses=["SUCCESS"])
    assert {r["id"] for r in out} == {"j1"}


def test_filter_by_types():
    out = filter_unique_job_rows(_veeam_rows(), types=["VSphereReplica"])
    assert {r["id"] for r in out} == {"j1"}


def test_filter_by_policy_types_netbackup():
    out = filter_unique_job_rows(_netbackup_rows(), policy_types=["VMWARE"])
    assert {r["jobid"] for r in out} == {"2", "3"}


def test_filter_by_categories_netbackup():
    out = filter_unique_job_rows(_netbackup_rows(), categories=["image"])
    assert {r["jobid"] for r in out} == {"2", "3"}

    out_app = filter_unique_job_rows(_netbackup_rows(), categories=["application"])
    assert {r["jobid"] for r in out_app} == {"1", "4"}


def test_filter_by_platforms_veeam_uses_workload_or_ip():
    out = filter_unique_job_rows(_veeam_rows(), platforms=["10.34.2.105"])
    assert {r["id"] for r in out} == {"j3", "j4"}


def test_filter_combines_dimensions_with_and_semantics():
    out = filter_unique_job_rows(
        _netbackup_rows(),
        statuses=["running"],  # no row has this status -> should exclude all
        policy_types=["VMWARE"],
    )
    assert out == []


def test_filter_empty_rows_returns_empty():
    assert filter_unique_job_rows([]) == []
    assert filter_unique_job_rows(None) == []


def test_filter_does_not_mutate_input():
    rows = _veeam_rows()
    original = [dict(r) for r in rows]
    filter_unique_job_rows(rows, search="marubeni", statuses=["warning"])
    assert rows == original


# ---------------------------------------------------------------------------
# paginate_rows
# ---------------------------------------------------------------------------

def test_paginate_basic_slice():
    items = list(range(1, 11))  # 1..10
    out = paginate_rows(items, page=2, page_size=3)
    assert out == {"items": [4, 5, 6], "total": 10, "page": 2, "page_size": 3}


def test_paginate_first_page_default_like_behavior():
    items = list(range(5))
    out = paginate_rows(items, page=1, page_size=2)
    assert out["items"] == [0, 1]
    assert out["total"] == 5


def test_paginate_page_beyond_range_returns_empty_items():
    items = list(range(5))
    out = paginate_rows(items, page=10, page_size=2)
    assert out["items"] == []
    assert out["total"] == 5
    assert out["page"] == 10


def test_paginate_page_size_capped_at_200():
    items = list(range(500))
    out = paginate_rows(items, page=1, page_size=1000)
    assert out["page_size"] == 200
    assert len(out["items"]) == 200


def test_paginate_page_size_zero_falls_back_to_default_50():
    """0 is falsy, so it takes the ``page_size or 50`` default branch — matches
    the existing ``DatabaseService._nsnap_paginate`` convention."""
    items = list(range(5))
    out = paginate_rows(items, page=1, page_size=0)
    assert out["page_size"] == 50


def test_paginate_page_size_negative_floored_at_1():
    items = list(range(5))
    out = paginate_rows(items, page=1, page_size=-7)
    assert out["page_size"] == 1
    assert out["items"] == [0]


def test_paginate_page_floored_at_1():
    items = list(range(5))
    out = paginate_rows(items, page=0, page_size=2)
    assert out["page"] == 1
    assert out["items"] == [0, 1]

    out_neg = paginate_rows(items, page=-3, page_size=2)
    assert out_neg["page"] == 1


def test_paginate_invalid_page_and_page_size_fall_back_to_defaults():
    items = list(range(5))
    out = paginate_rows(items, page=None, page_size=None)
    assert out["page"] == 1
    assert out["page_size"] == 50
    assert out["items"] == items


def test_paginate_empty_items():
    out = paginate_rows([], page=1, page_size=50)
    assert out == {"items": [], "total": 0, "page": 1, "page_size": 50}

    out_none = paginate_rows(None, page=1, page_size=50)
    assert out_none == {"items": [], "total": 0, "page": 1, "page_size": 50}
