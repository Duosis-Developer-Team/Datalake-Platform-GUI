"""Tests for coverage locations merged with Loki root locations."""

from unittest.mock import patch

from app.db.queries import coverage as cov_q


@patch("app.db.queries.coverage._fetch_target_issues", return_value=[])
@patch("app.db.queries.coverage._fetch_ibm_hosts", return_value=[])
@patch(
    "app.db.queries.coverage._fetch_clusters",
    return_value=[
        {
            "source": "vmware",
            "cluster_name": "DC13-G3-CLS",
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
def test_build_coverage_locations_include_loki_roots(_loki, _clusters, _hosts, _issues):
    result = cov_q.build_coverage()
    assert "DC13" in result["locations"]
    assert "DC16" in result["locations"]
    assert "AZ11" in result["locations"]
