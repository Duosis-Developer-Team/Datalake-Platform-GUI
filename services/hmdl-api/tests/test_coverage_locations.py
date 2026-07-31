"""Tests for coverage locations merged with Loki root locations."""

from unittest.mock import patch

from app.db.queries import coverage as cov_q


@patch("app.db.queries.coverage._fetch_backup_endpoints", return_value=[])
@patch("app.db.queries.coverage._fetch_vcenters", return_value=[])
@patch("app.db.queries.coverage._fetch_target_issues", return_value=[])
@patch("app.db.queries.coverage._fetch_ibm_hosts", return_value=[])
@patch(
    "app.db.queries.coverage._fetch_clusters",
    return_value=[
        {
            "source": "vmware",
            "cluster_name": "DC13-G3-CLS",
            "dc_code": "DC13",
            "parent_name": "vc1dc13.blt.vc",
            "expected_source": "loki",
            "collected": True,
            "expected": True,
            "is_live": True,
            "last_collected": None,
            "checked_at": None,
        }
    ],
)
@patch(
    "app.db.queries.collectors.list_root_locations",
    return_value=[
        {"dc_code": "DC13"},
        {"dc_code": "DC16"},
        {"dc_code": "AZ11"},
    ],
)
def test_build_coverage_locations_include_loki_roots(
    _loki, _clusters, _hosts, _issues, _vcenters, _backups
):
    result = cov_q.build_coverage()
    assert "DC13" in result["locations"]
    assert "DC16" in result["locations"]
    assert "AZ11" in result["locations"]
    assert result["clusters"][0]["expected_source"] == "loki"
    assert result["clusters"][0]["parent_name"] == "vc1dc13.blt.vc"
    assert "vcenters" in result
    assert "backup_endpoints" in result


@patch("app.db.queries.coverage._fetch_backup_endpoints", return_value=[])
@patch(
    "app.db.queries.coverage._fetch_vcenters",
    return_value=[
        {
            "source": "vmware",
            "parent_name": "vc2dc16.blt.vc",
            "dc_code": "DC16",
            "expected_clusters": 4,
            "collected_clusters": 3,
            "live_clusters": 3,
            "status": "partial",
            "checked_at": None,
        }
    ],
)
@patch("app.db.queries.coverage._fetch_target_issues", return_value=[])
@patch("app.db.queries.coverage._fetch_ibm_hosts", return_value=[])
@patch("app.db.queries.coverage._fetch_clusters", return_value=[])
@patch("app.db.queries.collectors.list_root_locations", return_value=[{"dc_code": "DC16"}])
def test_build_coverage_vcenter_rollup(_loki, _c, _h, _i, _v, _b):
    result = cov_q.build_coverage(dc="DC16")
    assert len(result["vcenters"]) == 1
    assert result["vcenters"][0]["status"] == "partial"
    assert result["summary"]["vcenter"]["partial"] == 1
