"""Tests for coverage locations merged with Loki root locations."""

from unittest.mock import patch

from app.db.queries import coverage as cov_q


@patch("app.db.queries.coverage._fetch_hmc_host_map", return_value={})
@patch("app.db.queries.coverage._fetch_platform_endpoints", return_value=[])
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
    _loki, _clusters, _hosts, _issues, _vcenters, _backups, _endpoints, _hmc_map
):
    result = cov_q.build_coverage()
    assert "DC13" in result["locations"]
    assert "DC16" in result["locations"]
    assert "AZ11" in result["locations"]
    assert result["clusters"][0]["expected_source"] == "loki"
    assert result["clusters"][0]["parent_name"] == "vc1dc13.blt.vc"
    assert "vcenters" in result
    assert "ibm_hmcs" in result
    assert "backup_endpoints" in result


@patch("app.db.queries.coverage._fetch_hmc_host_map", return_value={})
@patch(
    "app.db.queries.coverage._fetch_platform_endpoints",
    return_value=[
        {
            "entity_name": "Turksat-Vmware-ANK-Turksat",
            "ip": "10.60.2.125",
            "dc_code": "DC16",
            "platform_key": "vmware",
            "last_check_status": "ok",
        }
    ],
)
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
@patch(
    "app.db.queries.coverage._fetch_clusters",
    return_value=[
        {
            "source": "vmware",
            "cluster_name": "DC16-G2-CLS-HYBRID",
            "dc_code": "DC16",
            "parent_name": "vc2dc16.blt.vc",
            "expected_source": "both",
            "collected": True,
            "expected": True,
            "is_live": True,
            "last_collected": None,
            "checked_at": None,
        }
    ],
)
@patch("app.db.queries.collectors.list_root_locations", return_value=[{"dc_code": "DC16"}])
def test_build_coverage_vcenter_rollup(_loki, _c, _h, _i, _v, _b, _endpoints, _hmc_map):
    result = cov_q.build_coverage(dc="DC16")
    assert len(result["vcenters"]) == 1
    row = result["vcenters"][0]
    assert row["status"] == "partial"
    assert row["endpoint_name"] == "Turksat-Vmware-ANK-Turksat"
    assert row["endpoint_ip"] == "10.60.2.125"
    assert result["summary"]["vcenter"]["partial"] == 1


@patch(
    "app.db.queries.coverage._fetch_hmc_host_map",
    return_value={"RHV1DC13": "10.34.10.110"},
)
@patch(
    "app.db.queries.coverage._fetch_platform_endpoints",
    side_effect=lambda patterns: (
        [
            {
                "entity_name": "HMC_DC13",
                "ip": "10.34.2.110",
                "dc_code": "DC13",
                "platform_key": "ibm-hmc",
                "last_check_status": "ok",
            },
            {
                "entity_name": "Retail_HMC_DC13",
                "ip": "10.34.10.110",
                "dc_code": "DC13",
                "platform_key": "ibm-hmc",
                "last_check_status": "ok",
            },
        ]
        if patterns == ("%hmc%",)
        else []
    ),
)
@patch("app.db.queries.coverage._fetch_backup_endpoints", return_value=[])
@patch("app.db.queries.coverage._fetch_vcenters", return_value=[])
@patch("app.db.queries.coverage._fetch_target_issues", return_value=[])
@patch(
    "app.db.queries.coverage._fetch_ibm_hosts",
    return_value=[
        {
            "servername": "RHV1DC13",
            "dc_code": "DC13",
            "expected_source": "loki",
            "collected": True,
            "expected": True,
            "is_live": True,
            "last_collected": None,
            "checked_at": None,
        },
        {
            "servername": "G2HV12DC13",
            "dc_code": "DC13",
            "expected_source": "loki",
            "collected": True,
            "expected": True,
            "is_live": True,
            "last_collected": None,
            "checked_at": None,
        },
    ],
)
@patch("app.db.queries.coverage._fetch_clusters", return_value=[])
@patch("app.db.queries.collectors.list_root_locations", return_value=[{"dc_code": "DC13"}])
def test_build_coverage_groups_ibm_hosts_under_hmc(
    _loki, _c, _h, _i, _v, _b, _endpoints, _hmc_map
):
    result = cov_q.build_coverage(source="ibm")
    parents = {h["servername"]: h["parent_name"] for h in result["ibm_hosts"]}
    assert parents["RHV1DC13"] == "Retail_HMC_DC13"
    assert parents["G2HV12DC13"] == "HMC_DC13"
    assert {m["hmc_name"] for m in result["ibm_hmcs"]} == {"HMC_DC13", "Retail_HMC_DC13"}
    assert result["summary"]["ibm_hmc"]["live"] == 2
