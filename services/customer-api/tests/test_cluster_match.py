"""Unit tests for cluster name normalization (VMware vs Nutanix)."""

from app.utils.cluster_match import build_cluster_arch_map, normalize_cluster_key


def test_normalize_cluster_key_strips_suffixes():
    assert normalize_cluster_key("DC11-G3-Cluster-SSD") == "DC11-G3"
    assert normalize_cluster_key("DC11-G3-SSD") == "DC11-G3"
    assert normalize_cluster_key("DC13-G5-CLS-HYBRID") == "DC13-G5"
    assert normalize_cluster_key("DC13-G5-HYBRID") == "DC13-G5"


def test_build_cluster_arch_map_managed_vs_pure():
    vmware_nonkm = ["DC11-G3-Cluster-SSD", "DC13-G5-CLS-HYBRID"]
    nutanix = ["DC11-G3-SSD", "DC13-G5-HYBRID", "DC13-FC1-HYBRID"]
    result = build_cluster_arch_map(vmware_nonkm, nutanix)
    assert "DC11-G3-SSD" in result["managed_nutanix"]
    assert "DC13-G5-HYBRID" in result["managed_nutanix"]
    assert "DC13-FC1-HYBRID" in result["pure_nutanix"]
