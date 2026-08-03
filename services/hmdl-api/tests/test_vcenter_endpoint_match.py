"""Parent (vCenter / Prism / HMC) ↔ collector endpoint matching."""

from app.db.queries import coverage as cov_q
from app.db.queries.coverage import (
    _assign_parent_endpoints,
    _attach_hmc_parents,
    _build_vcenter_row,
    _drop_childless_rollups,
    _resolve_cluster_parents,
)


def _endpoint(name, ip, dc, platform="vmware", check="ok"):
    return {
        "entity_name": name,
        "ip": ip,
        "dc_code": dc,
        "platform_key": platform,
        "last_check_status": check,
    }


def test_parent_matched_by_ip():
    matches = _assign_parent_endpoints(
        [{"source": "vmware", "parent_name": "10.50.2.210", "dc_code": "DC14"}],
        [],
        [_endpoint("KKB-Vmware-ANK-KKB_vc3", "10.50.2.210", "DC14")],
    )
    hit = matches[("vmware", "DC14", "10.50.2.210")]
    assert hit["entity_name"] == "KKB-Vmware-ANK-KKB_vc3"


def test_parent_matched_by_vc_token():
    matches = _assign_parent_endpoints(
        [{"source": "vmware", "parent_name": "vc1dc13.blt.vc", "dc_code": "DC13"}],
        [],
        [_endpoint("Equinix IL2-Vmware-IST-Equinix_vc1", "10.34.2.10", "DC13")],
    )
    hit = matches[("vmware", "DC13", "vc1dc13.blt.vc")]
    assert hit["ip"] == "10.34.2.10"


def test_cluster_named_endpoint_is_not_a_parent():
    """DC16: vc2dc16 is Turksat — MoneyGramDr-CLS is a cluster collector, not a parent.

    The cluster row sits in the UNKNOWN bucket, so the exclusion must not be per-DC.
    """
    matches = _assign_parent_endpoints(
        [{"source": "vmware", "parent_name": "vc2dc16.blt.vc", "dc_code": "DC16"}],
        [{"source": "vmware", "cluster_name": "MoneyGramDr-CLS", "dc": "UNKNOWN"}],
        [
            _endpoint("MoneyGramDr-CLS", "10.200.0.200", "DC16"),
            _endpoint("Turksat-Vmware-ANK-Turksat", "10.60.2.125", "DC16"),
        ],
    )
    hit = matches[("vmware", "DC16", "vc2dc16.blt.vc")]
    assert hit["entity_name"] == "Turksat-Vmware-ANK-Turksat"
    assert hit["ip"] == "10.60.2.125"


def test_prism_endpoint_named_after_its_cluster_still_matches():
    matches = _assign_parent_endpoints(
        [{"source": "nutanix", "parent_name": "10.34.1.192", "dc_code": "DC13"}],
        [{"source": "nutanix", "cluster_name": "DC13-G3-AHV-SSD", "dc": "DC13"}],
        [_endpoint("DC13-G3-AHV-SSD", "10.34.1.192", "DC13", platform="nutanix")],
    )
    assert matches[("nutanix", "DC13", "10.34.1.192")]["entity_name"] == "DC13-G3-AHV-SSD"


def test_single_reachable_endpoint_wins_over_dead_stub():
    """MoneyGramDr-CLS has no cluster row, but it is unreachable — Turksat is the parent."""
    matches = _assign_parent_endpoints(
        [{"source": "vmware", "parent_name": "vc2dc16.blt.vc", "dc_code": "DC16"}],
        [],
        [
            _endpoint("MoneyGramDr-CLS", "10.200.0.200", "DC16", check="telnet_fail"),
            _endpoint("Turksat-Vmware-ANK-Turksat", "10.60.2.125", "DC16"),
        ],
    )
    assert matches[("vmware", "DC16", "vc2dc16.blt.vc")]["ip"] == "10.60.2.125"


def test_ambiguous_parents_stay_unmatched():
    matches = _assign_parent_endpoints(
        [
            {"source": "vmware", "parent_name": "vcadc99.blt.vc", "dc_code": "DC99"},
            {"source": "vmware", "parent_name": "vcbdc99.blt.vc", "dc_code": "DC99"},
        ],
        [],
        [
            _endpoint("Alpha-Vmware", "10.1.1.1", "DC99"),
            _endpoint("Beta-Vmware", "10.1.1.2", "DC99"),
        ],
    )
    assert ("vmware", "DC99", "vcadc99.blt.vc") not in matches
    assert ("vmware", "DC99", "vcbdc99.blt.vc") not in matches


def test_build_vcenter_row_carries_endpoint():
    row = _build_vcenter_row(
        {
            "source": "vmware",
            "parent_name": "vc2dc13.blt.vc",
            "dc_code": "DC13",
            "expected_clusters": 3,
            "collected_clusters": 0,
            "live_clusters": 0,
            "status": "missing",
            "checked_at": None,
        },
        _endpoint("Equinix IL2-Vmware-IST-Equinix_vc2", "10.34.17.20", "DC13", check="telnet_fail"),
    )
    assert row["endpoint_ip"] == "10.34.17.20"
    assert row["endpoint_name"] == "Equinix IL2-Vmware-IST-Equinix_vc2"
    assert row["collector_check_status"] == "telnet_fail"
    assert row["collector_network_ok"] is False


def test_ip_parent_missing_from_collector_is_identified_by_its_clusters():
    """DC13-G9: inventory keeps the Prism VIP, the collector reaches another address."""
    matches = _assign_parent_endpoints(
        [{"source": "nutanix", "parent_name": "10.34.2.226", "dc_code": "DC13"}],
        [{"source": "nutanix", "cluster_name": "DC13-G9-HYBRID", "dc": "DC13", "parent_name": "10.34.2.226"}],
        [_endpoint("Equinix IL2-Nutanix-DC13-G9", "10.34.2.108", "DC13", platform="nutanix")],
    )
    assert matches[("nutanix", "DC13", "10.34.2.226")]["ip"] == "10.34.2.108"


def _cluster(name, dc, source, collected=True, live=True, parent=None):
    return {
        "source": source,
        "cluster_name": name,
        "dc": dc,
        "parent_name": parent,
        "parent_key": None,
        "parent_display": None,
        "parent_ip": None,
        "expected_source": "loki",
        "collected": collected,
        "expected": True,
        "is_live": live,
        "last_collected": None,
        "status": "live" if collected else "missing",
        "reason": "",
        "target_issues": [],
    }


def test_acropolis_cluster_written_as_vmware_moves_to_nutanix():
    """DC18: AWX emits the same AHV cluster under both sources; only Nutanix is real."""
    nutanix_row = _cluster("DC18-G3-AHV-NVME", "DC18", "nutanix")
    vmware_row = _cluster("DC18-G3-AHV-NVME", "DC18", "vmware", collected=False, live=False)
    clusters, parents = _resolve_cluster_parents(
        [nutanix_row, vmware_row],
        [],
        [_endpoint("DC18-G3-AHV-NVME", "10.135.2.121", "DC18", platform="acropolis")],
    )
    assert clusters == [nutanix_row]
    assert nutanix_row["parent_key"] == "10.135.2.121"
    assert nutanix_row["parent_display"] == "DC18-G3-AHV-NVME"
    assert [(p["source"], p["parent_key"], p["origin"]) for p in parents] == [
        ("nutanix", "10.135.2.121", "endpoint")
    ]


def test_prism_matched_through_identity_tokens():
    cluster = _cluster("DC11-G3-SSD", "DC11", "nutanix")
    _resolve_cluster_parents(
        [cluster],
        [],
        [
            _endpoint("PremierDC-Nutanix-DC11-G3", "10.6.2.80", "DC11", platform="nutanix"),
            _endpoint("PremierDC-Nutanix-DC11-G4", "10.6.2.97", "DC11", platform="nutanix"),
        ],
    )
    assert cluster["parent_ip"] == "10.6.2.80"


def test_cluster_fqdn_parent_matches_endpoint_without_rollup():
    """cluster_metrics.datacenter / NetBox description FQDN → collector entity token."""
    cluster = _cluster("DC18-KM-CLS-NVME", "DC18", "vmware")
    cluster["parent_name"] = "vc2dc18.blt.vc"
    clusters, parents = _resolve_cluster_parents(
        [cluster],
        [],
        [
            _endpoint("Equinix IL4-Vmware-IST-Equinix_vc1dc18", "10.135.2.148", "DC18"),
            _endpoint("Equinix IL4-Vmware-IST-Equinix_vc2dc18", "10.34.17.181", "DC18"),
        ],
    )
    assert cluster["parent_key"] == "10.34.17.181"
    assert cluster["parent_display"] == "Equinix IL4-Vmware-IST-Equinix_vc2dc18"
    assert parents[0]["parent_key"] == "10.34.17.181"


def test_nutanix_strips_vmware_fqdn_parent_before_match():
    """NetBox VM alias description must not leave a vCenter FQDN on the Nutanix tab."""
    from app.db.queries.coverage import _build_cluster_row

    row = _build_cluster_row(
        {
            "source": "nutanix",
            "cluster_name": "DC14-G1-HYBRID",
            "dc_code": "DC14",
            "parent_name": "vc1dc14.blt.vc",
            "collected": True,
            "expected": True,
            "is_live": True,
        },
        {},
    )
    assert row["parent_name"] is None


def test_prism_is_claimed_by_one_cluster_only():
    """One Prism, two inventory clusters: the collected one owns it, the other is a gap."""
    collected = _cluster("DC11-G3-SSD", "DC11", "nutanix")
    phantom = _cluster("DC11-G3-OTHER", "DC11", "nutanix", collected=False, live=False)
    _resolve_cluster_parents(
        [phantom, collected],
        [],
        [_endpoint("PremierDC-Nutanix-DC11-G3", "10.6.2.80", "DC11", platform="nutanix")],
    )
    assert collected["parent_ip"] == "10.6.2.80"
    assert phantom["parent_key"] is None


def test_single_site_token_never_moves_a_cluster_across_platforms():
    """`AZ11-CLS` shares its only token with every endpoint in the DC — too weak."""
    cluster = _cluster("AZ11-CLS", "AZ11", "nutanix")
    _resolve_cluster_parents(
        [cluster],
        [],
        [_endpoint("Azin Telecom-Vmware-AZ11", "10.81.2.21", "AZ11", platform="vmware")],
    )
    assert cluster["source"] == "nutanix"
    assert cluster["parent_key"] is None


def test_collected_orphan_falls_back_to_the_only_vcenter():
    """It is collected in a DC with one vCenter, so that vCenter is where it came from."""
    cluster = _cluster("UZ11-KM-CLS-NVME", "UZ11", "vmware")
    _resolve_cluster_parents(
        [cluster],
        [],
        [_endpoint("Uzbekistan-Vmware-UZ11", "10.85.2.50", "UZ11")],
    )
    assert cluster["parent_ip"] == "10.85.2.50"


def test_inventory_only_orphan_is_never_guessed_onto_a_vcenter():
    """No metrics means no evidence: `DC11-G3-CLS-IBM` under PremierDC was invented."""
    cluster = _cluster("DC11-G3-CLS-IBM", "DC11", "vmware", collected=False, live=False)
    _resolve_cluster_parents(
        [cluster],
        [],
        [_endpoint("PremierDC-Vmware-IST-Premier", "10.6.2.146", "DC11")],
    )
    assert cluster["parent_key"] is None
    assert cluster["unmatched_reason"] == "no_hint"


def test_ibm_inventory_gap_stays_unmatched_with_no_collector_reason():
    """source=ibm rows are the IBM surface gap — never matched to a vCenter."""
    gap = _cluster("DC11-G3-CLS-IBM", "DC11", "ibm", collected=False, live=False)
    _resolve_cluster_parents(
        [gap],
        [],
        [_endpoint("PremierDC-Vmware-IST-Premier", "10.6.2.146", "DC11")],
    )
    assert gap["parent_key"] is None
    assert gap["unmatched_reason"] == "no_collector"


def test_ambiguous_collected_orphan_gets_ambiguous_reason():
    cluster = _cluster("DC18-KM-CLS-NVME", "DC18", "vmware")
    _resolve_cluster_parents(
        [cluster],
        [],
        [
            _endpoint("Equinix-vc1", "10.1.1.1", "DC18"),
            _endpoint("Equinix-vc2", "10.1.1.2", "DC18"),
        ],
    )
    assert cluster["parent_key"] is None
    assert cluster["unmatched_reason"] == "ambiguous"


def test_endpoint_named_after_the_cluster_matches_it():
    cluster = _cluster("AZ11-CLS", "AZ11", "nutanix")
    _resolve_cluster_parents(
        [cluster],
        [],
        [_endpoint("Azin Telecom-Nutanix-AZ11-CLS", "10.81.2.35", "AZ11", platform="nutanix")],
    )
    assert cluster["parent_ip"] == "10.81.2.35"


def test_platform_named_alias_folds_into_the_cluster_holding_the_endpoint():
    """NetBox lists one Nutanix cluster twice: as a platform and under its own name."""
    real = _cluster("PRISM-AZ11-SSD", "AZ11", "nutanix")
    alias = _cluster("AZ11-CLS", "AZ11", "nutanix", collected=False, live=False)
    clusters, _ = _resolve_cluster_parents(
        [real, alias],
        [],
        [_endpoint("Azin Telecom-Nutanix-AZ11-CLS", "10.81.2.35", "AZ11", platform="nutanix")],
    )
    assert clusters == [real]
    assert real["parent_ip"] == "10.81.2.35"


def test_vcenter_rollup_parent_wins_over_name_matching():
    """An ESXi cluster on Nutanix hardware keeps its vCenter parent and its platform."""
    cluster = _cluster("DC13-G11-CLS-HYBRID-NW", "DC13", "vmware", parent="vc1dc13.blt.vc")
    _resolve_cluster_parents(
        [cluster],
        [
            {
                "source": "vmware",
                "dc": "DC13",
                "parent_name": "vc1dc13.blt.vc",
                "parent_key": "10.34.2.10",
                "endpoint_ip": "10.34.2.10",
                "endpoint_name": "Equinix IL2-Vmware-IST-Equinix_vc1",
            }
        ],
        [_endpoint("Equinix IL2-Nutanix-DC13-G11-HYBRID-NW", "10.34.1.95", "DC13", platform="nutanix")],
    )
    assert cluster["source"] == "vmware"
    assert cluster["parent_key"] == "10.34.2.10"


def test_rollup_without_surviving_clusters_is_dropped():
    """A retired Prism keeps advertising "1 cluster" after that cluster left inventory."""
    kept = {"parent_key": "10.34.1.250", "expected_clusters": 1}
    empty = {"parent_key": "10.34.1.98", "expected_clusters": 1}
    survivors = _drop_childless_rollups(
        [kept, empty], [_cluster("DC13-G7-SSD-NEW", "DC13", "nutanix") | {"parent_key": "10.34.1.250"}]
    )
    assert survivors == [kept]


def test_coverage_queries_only_serve_entities_the_last_run_still_saw(monkeypatch):
    """AWX never deletes; it retires. A retired row is history, not a coverage gap."""
    seen: list[str] = []
    monkeypatch.setattr(cov_q.pool, "fetch_all", lambda sql, *a, **k: seen.append(sql) or [])
    cov_q._fetch_clusters()
    cov_q._fetch_ibm_hosts()
    cov_q._fetch_vcenters()
    assert all("absent_since IS NULL" in sql for sql in seen)
    # Backstop for a pass that died before sweeping this table.
    assert all("max(checked_at)" in sql for sql in seen)


def _host(name, dc, collected=True, live=True, offline=False):
    return {
        "servername": name,
        "dc": dc,
        "parent_name": None,
        "parent_ip": None,
        "collected": collected,
        "expected": True,
        "is_live": live,
        "is_offline": offline,
    }


def test_hmc_rollup_uses_metrics_map_then_leftover():
    hosts = [_host("RHV1DC13", "DC13"), _host("G2HV12DC13", "DC13")]
    hmcs = _attach_hmc_parents(
        hosts,
        [
            _endpoint("HMC_DC13", "10.34.2.110", "DC13", platform="ibm-hmc"),
            _endpoint("Retail_HMC_DC13", "10.34.10.110", "DC13", platform="ibm-hmc"),
        ],
        {"RHV1DC13": "10.34.10.110"},
    )
    by_host = {h["servername"]: h["parent_name"] for h in hosts}
    assert by_host["RHV1DC13"] == "Retail_HMC_DC13"
    assert by_host["G2HV12DC13"] == "HMC_DC13"
    assert {m["hmc_name"] for m in hmcs} == {"HMC_DC13", "Retail_HMC_DC13"}
    assert all(m["status"] == "live" for m in hmcs)


def test_hmc_single_endpoint_per_dc_takes_all_hosts():
    hosts = [_host("G3HV1DC11", "DC11"), _host("G3HV2DC11", "DC11", collected=False, live=False)]
    hmcs = _attach_hmc_parents(
        hosts,
        [_endpoint("HMC_DC11", "10.6.2.153", "DC11", platform="ibm-hmc")],
        {},
    )
    assert all(h["parent_name"] == "HMC_DC11" for h in hosts)
    assert hmcs[0]["expected_hosts"] == 2
    assert hmcs[0]["collected_hosts"] == 1
    assert hmcs[0]["status"] == "partial"


def test_hosts_without_hmc_fall_into_unassigned_bucket():
    hosts = [_host("G2HV1DC18", "DC18", collected=False, live=False)]
    hmcs = _attach_hmc_parents(hosts, [], {})
    assert hosts[0]["parent_name"] == "HMC eşleşmedi"
    # Unmatched hosts stay on the host row only — not as fake HMC KPI cards.
    assert hmcs == []


def test_offline_only_unassigned_host_is_not_rolled_into_hmc():
    """Offline inventory-only hosts must not inflate the HMC summary."""
    hosts = [_host("KAPALI", "UNKNOWN", collected=False, live=False, offline=True)]
    hmcs = _attach_hmc_parents(hosts, [], {})
    assert hmcs == []
    assert hosts[0]["parent_name"] == "HMC eşleşmedi"


def test_unassigned_hosts_do_not_create_hmc_rows():
    hosts = [
        _host("G2HV1DC18", "DC18", collected=False, live=False),
        _host("KAPALI", "UNKNOWN", collected=False, live=False, offline=True),
    ]
    hmcs = _attach_hmc_parents(hosts, [], {})
    assert hmcs == []
    assert {h["parent_name"] for h in hosts} == {"HMC eşleşmedi"}


def test_hmc_family_sibling_beats_leftover():
    """RHV* without metrics follows other RHV hosts, not the leftover HMC."""
    hosts = [
        _host("RHV1DC13", "DC13"),
        _host("RHV13DC13", "DC13", collected=False, live=False),
        _host("G2HV12DC13", "DC13"),
    ]
    hmcs = _attach_hmc_parents(
        hosts,
        [
            _endpoint("HMC_DC13", "10.34.2.110", "DC13", platform="ibm-hmc"),
            _endpoint("Retail_HMC_DC13", "10.34.10.110", "DC13", platform="ibm-hmc"),
        ],
        {"RHV1DC13": "10.34.10.110"},
    )
    by_host = {h["servername"]: h["parent_name"] for h in hosts}
    assert by_host["RHV13DC13"] == "Retail_HMC_DC13"
    assert by_host["G2HV12DC13"] == "HMC_DC13"
    retail = next(m for m in hmcs if m["hmc_name"] == "Retail_HMC_DC13")
    assert retail["expected_hosts"] == 2
    assert retail["status"] == "partial"
