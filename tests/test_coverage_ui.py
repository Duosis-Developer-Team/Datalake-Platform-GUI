"""Datalake coverage UI builders + empty-state contract."""

from src.components.hmdl_coverage_flow import build_backup_coverage_graph, build_coverage_graph
from src.services.api_client import _EMPTY_HMDL_COVERAGE
from src.utils.hmdl_sync_ui import (
    build_coverage_backup_section,
    build_coverage_section,
    build_coverage_summary,
    build_coverage_table,
    build_coverage_virtualization_section,
    build_hmc_expand_table,
    build_vcenter_expand_table,
    coverage_status_badge,
)

_SAMPLE = {
    "summary": {
        "cluster": {
            "all": {"total": 2, "collected": 1, "missing": 1, "live": 1},
            "vmware": {"total": 2, "collected": 1, "missing": 1, "live": 1},
        },
        "ibm_host": {"total": 1, "collected": 1, "missing": 0, "live": 1},
        "vcenter": {"total": 1, "live": 0, "partial": 1, "missing": 0, "stale": 0, "extra": 0},
        "ibm_hmc": {"total": 1, "live": 1, "partial": 0, "missing": 0, "stale": 0, "extra": 0},
        "backup_endpoint": {
            "netbackup": {"total": 2, "collected": 1, "missing": 1, "live": 1, "extra": 0, "stale": 0},
            "veeam": {"total": 1, "collected": 1, "missing": 0, "live": 1, "extra": 0, "stale": 0},
        },
    },
    "clusters": [
        {
            "source": "vmware",
            "cluster_name": "DC13-G3-CLS",
            "dc": "DC13",
            "parent_name": "vc1dc13.blt.vc",
            "parent_key": "10.34.2.10",
            "parent_display": "Equinix IL2-Vmware-IST-Equinix_vc1",
            "parent_ip": "10.34.2.10",
            "status": "missing",
            "reason": "Toplanmıyor",
            "expected_source": "loki",
        },
        {
            "source": "vmware",
            "cluster_name": "DC16-G2-CLS-HYBRID",
            "dc": "DC16",
            "parent_name": None,
            "parent_key": None,
            "status": "live",
            "reason": "Canlı",
        },
        {
            "source": "nutanix",
            "cluster_name": "DC18-G3-AHV-NVME",
            "dc": "DC18",
            "parent_name": None,
            "parent_key": "10.135.2.121",
            "parent_display": "DC18-G3-AHV-NVME",
            "parent_ip": "10.135.2.121",
            "status": "live",
            "reason": "Canlı",
        },
    ],
    "ibm_hosts": [
        {
            "servername": "G2HV12DC13",
            "dc": "DC13",
            "parent_name": "HMC_DC13",
            "parent_ip": "10.34.2.110",
            "status": "live",
            "reason": "Canlı",
        },
    ],
    "ibm_hmcs": [
        {
            "hmc_name": "HMC_DC13",
            "endpoint_ip": "10.34.2.110",
            "dc": "DC13",
            "expected_hosts": 1,
            "collected_hosts": 1,
            "live_hosts": 1,
            "status": "live",
            "collector_check_status": "ok",
        }
    ],
    "vcenters": [
        {
            "source": "vmware",
            "parent_name": "vc1dc13.blt.vc",
            "parent_key": "10.34.2.10",
            "origin": "rollup",
            "endpoint_ip": "10.34.2.10",
            "endpoint_name": "Equinix IL2-Vmware-IST-Equinix_vc1",
            "dc": "DC13",
            "expected_clusters": 3,
            "collected_clusters": 2,
            "live_clusters": 2,
            "status": "partial",
            "collector_check_status": "ok",
            "collector_network_ok": True,
        },
        {
            "source": "nutanix",
            "parent_name": "DC18-G3-AHV-NVME",
            "parent_key": "10.135.2.121",
            "origin": "endpoint",
            "endpoint_ip": "10.135.2.121",
            "endpoint_name": "DC18-G3-AHV-NVME",
            "dc": "DC18",
            "expected_clusters": 1,
            "collected_clusters": 1,
            "live_clusters": 1,
            "status": "live",
            "collector_check_status": "ok",
            "collector_network_ok": True,
        },
    ],
    "backup_endpoints": [
        {
            "source": "netbackup",
            "endpoint_ip": "10.132.1.137",
            "endpoint_name": "Equinix IL2-Netbackup-DC13_3",
            "dc": "DC13",
            "collected": True,
            "expected": True,
            "network_ok": True,
            "is_live": True,
            "status": "live",
            "reason": "Canlı",
            "collector_check_status": "ok",
        },
        {
            "source": "netbackup",
            "endpoint_ip": "10.50.1.126",
            "endpoint_name": "ANK.KKB-Netbackup-DC14",
            "dc": "DC14",
            "collected": False,
            "expected": True,
            "network_ok": True,
            "is_live": False,
            "status": "missing",
            "reason": "Toplanmıyor",
            "collector_check_status": "ok",
        },
        {
            "source": "veeam",
            "endpoint_ip": "10.34.2.104",
            "endpoint_name": "Equinix IL2-VeeamBR-DC13",
            "dc": "DC13",
            "collected": True,
            "expected": True,
            "network_ok": True,
            "is_live": True,
            "status": "live",
            "reason": "Canlı",
        },
    ],
}


def test_empty_coverage_contract():
    assert _EMPTY_HMDL_COVERAGE["clusters"] == []
    assert _EMPTY_HMDL_COVERAGE["ibm_hosts"] == []
    assert _EMPTY_HMDL_COVERAGE["ibm_hmcs"] == []
    assert "summary" in _EMPTY_HMDL_COVERAGE
    assert "locations" in _EMPTY_HMDL_COVERAGE


def test_coverage_status_badge_renders():
    for status in ("live", "stale", "missing", "extra", "unknown"):
        assert coverage_status_badge(status) is not None


def test_build_coverage_summary_renders():
    assert build_coverage_summary(_SAMPLE["summary"]) is not None


def test_build_coverage_table_renders_with_rows():
    assert build_coverage_table(_SAMPLE["clusters"], _SAMPLE["ibm_hosts"]) is not None


def test_build_coverage_table_empty_state():
    # No rows → an alert component, not a crash.
    assert build_coverage_table([], []) is not None


def test_build_coverage_section_composes():
    assert build_coverage_section(_SAMPLE) is not None


def test_build_virtualization_all_locations():
    assert build_coverage_virtualization_section(_SAMPLE, product="vmware", selected_dc=None) is not None


def test_build_virtualization_dc_drill():
    assert build_coverage_virtualization_section(_SAMPLE, product="vmware", selected_dc="DC13") is not None


def test_build_virtualization_ibm_uses_hmc_parents():
    text = str(build_coverage_virtualization_section(_SAMPLE, product="ibm", selected_dc=None))
    assert "HMC_DC13" in text
    assert "G2HV12DC13" in text


def test_vcenter_row_shows_entity_name_without_inline_ip():
    text = str(build_vcenter_expand_table(_SAMPLE["vcenters"], _SAMPLE["clusters"]))
    assert "Equinix IL2-Vmware-IST-Equinix_vc1" in text
    assert "10.34.2.10" in text
    assert "Equinix IL2-Vmware-IST-Equinix_vc1 · 10.34.2.10" not in text


def test_hmc_expand_table_lists_hosts():
    text = str(build_hmc_expand_table(_SAMPLE["ibm_hmcs"], _SAMPLE["ibm_hosts"]))
    assert "HMC_DC13" in text
    assert "G2HV12DC13" in text


def test_hmc_expand_table_lists_unmatched_hosts_below():
    """Unmatched hosts belong in the bottom inventory panel, not as HMC cards."""
    hmcs = [
        {
            "hmc_name": "HMC_DC13",
            "endpoint_ip": "10.34.2.110",
            "dc": "DC13",
            "expected_hosts": 1,
            "collected_hosts": 1,
            "live_hosts": 1,
            "status": "live",
        },
    ]
    hosts = [
        {
            "servername": "G2HV12DC13",
            "dc": "DC13",
            "parent_name": "HMC_DC13",
            "status": "live",
            "reason": "OK",
        },
        {
            "servername": "G2HV1DC18",
            "dc": "DC18",
            "parent_name": "HMC eşleşmedi",
            "status": "missing",
            "reason": "Toplanmıyor",
        },
        {
            "servername": "KAPALI",
            "dc": "UNKNOWN",
            "parent_name": "HMC eşleşmedi",
            "status": "offline",
            "is_offline": True,
            "reason": "Offline",
        },
    ]
    text = str(build_hmc_expand_table(hmcs, hosts))
    assert "HMC_DC13" in text
    assert "HMC eşleşmeyen host" in text
    assert text.count("G2HV1DC18") == 1
    assert text.count("KAPALI") == 1
    assert "HMC eşleşmedi" not in text or text.count("HMC eşleşmedi") == 0


def test_coverage_graph_hub_and_dc_nodes():
    graph = build_coverage_graph(_SAMPLE, product="vmware", product_label="VMware")
    assert graph["hub"]["label"] == "VMware"
    assert {n["label"] for n in graph["nodes"]} == {"DC13", "DC16"}
    dc13 = next(n for n in graph["nodes"] if n["label"] == "DC13")
    assert dc13["selectValue"] == "DC13"
    assert dc13["children"][0]["label"] == "Equinix IL2-Vmware-IST-Equinix_vc1"
    assert dc13["children"][0]["children"][0]["label"] == "DC13-G3-CLS"


def test_coverage_graph_omits_unmatched_clusters():
    """Parentless clusters stay in the expand table — not as UNKNOWN / synthetic spokes."""
    graph = build_coverage_graph(_SAMPLE, product="vmware", product_label="VMware")
    assert {n["label"] for n in graph["nodes"]} == {"DC13"}
    assert all(n["label"] != "UNKNOWN" for n in graph["nodes"])
    for dc in graph["nodes"]:
        assert all(p["label"] != "Parent eşleşmedi" for p in dc["children"])


def test_coverage_graph_groups_by_resolved_parent_key():
    """Nutanix parents come from collector targets, so grouping cannot use parent_name."""
    graph = build_coverage_graph(_SAMPLE, product="nutanix", product_label="Nutanix")
    dc18 = next(n for n in graph["nodes"] if n["label"] == "DC18")
    prism = dc18["children"][0]
    assert prism["label"] == "DC18-G3-AHV-NVME"
    assert prism["sublabel"] == "10.135.2.121"
    assert [c["label"] for c in prism["children"]] == ["DC18-G3-AHV-NVME"]


def test_coverage_graph_selected_dc_hub():
    graph = build_coverage_graph(
        _SAMPLE, product="vmware", product_label="VMware", selected_dc="DC13"
    )
    assert graph["hub"]["label"] == "DC13"
    assert graph["nodes"][0]["kind"] == "parent"


def test_coverage_graph_ibm_hmc_layer():
    graph = build_coverage_graph(_SAMPLE, product="ibm", product_label="IBM Power")
    dc13 = next(n for n in graph["nodes"] if n["label"] == "DC13")
    hmc = dc13["children"][0]
    assert hmc["label"] == "HMC_DC13"
    assert hmc["children"][0]["label"] == "G2HV12DC13"


def test_backup_coverage_graph_hub_to_endpoint():
    graph = build_backup_coverage_graph(
        _SAMPLE, product="netbackup", product_label="NetBackup"
    )
    assert graph["hub"]["label"] == "NetBackup"
    dcs = {n["label"] for n in graph["nodes"]}
    assert dcs == {"DC13", "DC14"}
    dc13 = next(n for n in graph["nodes"] if n["label"] == "DC13")
    assert dc13["children"][0]["label"] == "Equinix IL2-Netbackup-DC13_3"
    assert dc13["children"][0]["sublabel"] == "10.132.1.137"


def test_backup_coverage_graph_selected_dc():
    graph = build_backup_coverage_graph(
        _SAMPLE, product="netbackup", product_label="NetBackup", selected_dc="DC14"
    )
    assert graph["hub"]["label"] == "DC14"
    assert graph["nodes"][0]["label"] == "ANK.KKB-Netbackup-DC14"


def test_backup_coverage_graph_dc_partial_when_mixed():
    data = {
        "backup_endpoints": [
            {
                "source": "nutanix_snapshot",
                "endpoint_name": "A",
                "endpoint_ip": "10.1.1.1",
                "dc": "DC14",
                "status": "live",
            },
            {
                "source": "nutanix_snapshot",
                "endpoint_name": "B",
                "endpoint_ip": "10.1.1.2",
                "dc": "DC14",
                "status": "missing",
            },
        ]
    }
    from src.components.hmdl_coverage_flow import build_backup_coverage_graph

    graph = build_backup_coverage_graph(
        data, product="nutanix_snapshot", product_label="Nutanix Snapshot"
    )
    dc14 = next(n for n in graph["nodes"] if n["label"] == "DC14")
    assert dc14["status"] == "partial"


def test_backup_stub():
    # Kept for import stability; section is the real Backup tab.
    from src.utils.hmdl_sync_ui import build_coverage_backup_stub

    assert build_coverage_backup_stub() is not None
