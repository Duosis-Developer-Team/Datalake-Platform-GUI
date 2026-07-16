"""Unit tests for Zerto license parsing / NetBackup category totals."""
from __future__ import annotations

import json

from app.services.dc_service import DatabaseService


def test_parse_zerto_sites_usage_list():
    raw = [
        {"SiteName": "DC13-SiteKM", "SiteIdentifier": "abc", "ProtectedVmsCount": 93},
        {"SiteName": "ANDAR", "ProtectedVmsCount": 10},
    ]
    out = DatabaseService._parse_zerto_sites_usage(raw)
    assert len(out) == 2
    assert out[0]["site_name"] == "DC13-SiteKM"
    assert out[0]["protected_vms_count"] == 93


def test_parse_zerto_sites_usage_json_string():
    raw = json.dumps([{"SiteName": "DC14-Site02", "ProtectedVmsCount": 5}])
    out = DatabaseService._parse_zerto_sites_usage(raw)
    assert len(out) == 1
    assert out[0]["protected_vms_count"] == 5


def test_parse_zerto_sites_usage_invalid():
    assert DatabaseService._parse_zerto_sites_usage(None) == []
    assert DatabaseService._parse_zerto_sites_usage("not-json") == []
    assert DatabaseService._parse_zerto_sites_usage({"x": 1}) == []


def test_finalize_job_stats_adds_category_totals_for_netbackup():
    series = [
        {
            "period": "2026-01-01",
            "status": "success",
            "job_type": "BACKUP",
            "policy_type": "VMWARE",
            "category": "image",
            "count": 4,
        },
        {
            "period": "2026-01-01",
            "status": "success",
            "job_type": "BACKUP",
            "policy_type": "SAP",
            "category": "application",
            "count": 6,
        },
    ]
    payload = DatabaseService._finalize_job_stats(
        series, "netbackup", "day", {"start": "2026-01-01", "end": "2026-01-31"}
    )
    assert payload["totals"]["total"] == 10
    assert payload["totals_by_category"]["image"]["total"] == 4
    assert payload["totals_by_category"]["application"]["total"] == 6
    assert payload["policy_types"]["image"] == ["VMWARE"]
    assert "SAP" in payload["policy_types"]["application"]


def test_empty_job_stats_includes_category_buckets_for_netbackup():
    empty = DatabaseService._empty_job_stats(
        "netbackup", "day", {"start": "a", "end": "b"}
    )
    assert empty["totals_by_category"]["image"]["total"] == 0
    assert empty["policy_types"] == {"image": [], "application": []}
