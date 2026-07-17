"""Tests for NetBackup job-stats category / policy-type client filters."""
from __future__ import annotations

from src.components.backup_jobs_section import (
    apply_job_filters,
    available_policy_types,
    filter_series_by_category,
    filter_series_by_policy_types,
)


def _sample_payload():
    return {
        "vendor": "netbackup",
        "series": [
            {"period": "2026-01-01", "status": "success", "policy_type": "VMWARE", "category": "image", "count": 10},
            {"period": "2026-01-01", "status": "failed", "policy_type": "VMWARE", "category": "image", "count": 2},
            {"period": "2026-01-01", "status": "success", "policy_type": "SAP", "category": "application", "count": 5},
            {"period": "2026-01-01", "status": "success", "policy_type": "SQL_SERVER", "category": "application", "count": 3},
        ],
        "totals": {"total": 20},
        "policy_types": {"image": ["VMWARE"], "application": ["SAP", "SQL_SERVER"]},
    }


def test_filter_series_by_category():
    series = _sample_payload()["series"]
    image = filter_series_by_category(series, "image")
    assert len(image) == 2
    assert all(p["category"] == "image" for p in image)
    app = filter_series_by_category(series, "application")
    assert len(app) == 2


def test_filter_series_by_category_classifies_missing_category():
    """Stale cache points omit category — classify from policy_type."""
    series = [
        {"period": "2026-07-11", "status": "success", "policy_type": "VMWARE", "count": 10},
        {"period": "2026-07-11", "status": "failed", "policy_type": "VMWARE", "count": 1},
        {"period": "2026-07-11", "status": "success", "policy_type": "SAP", "count": 5},
        {"period": "2026-07-11", "status": "success", "policy_type": "SQL_SERVER", "count": 3},
    ]
    image = filter_series_by_category(series, "image")
    assert len(image) == 2
    assert all(p["policy_type"] == "VMWARE" for p in image)
    app = filter_series_by_category(series, "application")
    assert len(app) == 2
    assert {p["policy_type"] for p in app} == {"SAP", "SQL_SERVER"}


def test_apply_job_filters_stale_payload_without_category():
    payload = {
        "vendor": "netbackup",
        "series": [
            {"period": "2026-07-11", "status": "success", "policy_type": "VMWARE", "count": 10},
            {"period": "2026-07-11", "status": "failed", "policy_type": "VMWARE", "count": 2},
            {"period": "2026-07-11", "status": "success", "policy_type": "SAP", "count": 5},
        ],
        "totals": {"total": 17},
    }
    filtered = apply_job_filters(payload, category="image", policy_types=["VMWARE"])
    assert filtered["totals"]["total"] == 12
    assert filtered["totals"]["success"] == 10
    assert filtered["totals"]["failed"] == 2
    assert len(filtered["series"]) == 2


def test_filter_series_by_policy_types():
    series = _sample_payload()["series"]
    only_sap = filter_series_by_policy_types(series, ["SAP"])
    assert len(only_sap) == 1
    assert only_sap[0]["policy_type"] == "SAP"


def test_apply_job_filters_recomputes_totals():
    filtered = apply_job_filters(_sample_payload(), category="image")
    assert filtered["totals"]["total"] == 12
    assert filtered["totals"]["success"] == 10
    assert filtered["totals"]["failed"] == 2


def test_apply_job_filters_policy_and_category():
    filtered = apply_job_filters(
        _sample_payload(),
        category="application",
        policy_types=["SQL_SERVER"],
    )
    assert filtered["totals"]["total"] == 3
    assert len(filtered["series"]) == 1


def test_available_policy_types_from_payload():
    pts = available_policy_types(_sample_payload(), category="application")
    assert pts == ["SAP", "SQL_SERVER"]
