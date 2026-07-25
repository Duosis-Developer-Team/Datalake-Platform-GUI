"""Hybrid freshness registry: discovery columns, exclude, family map, overrides."""
from app.services import freshness_registry as fr


def test_is_excluded_drops_legacy_loki():
    assert fr.is_excluded("loki_devices")
    assert fr.is_excluded("loki_platforms")
    assert fr.is_excluded("nutanix_snapshot_schedule")
    assert not fr.is_excluded("cluster_metrics")
    assert not fr.is_excluded("discovery_loki_rack")  # discovery_* is live, not legacy


def test_family_of_maps_by_prefix():
    assert fr.family_of("raw_vmware_datastore_metrics_agg") == "VMware"
    assert fr.family_of("nutanix_cluster_metrics") == "Nutanix"
    assert fr.family_of("ibm_lpar_general") == "IBM"
    assert fr.family_of("zabbix_storage_pool_metrics") == "Zabbix"
    assert fr.family_of("discovery_netbox_inventory_device") == "NetBox"
    assert fr.family_of("raw_panduit_pdu_inventory") == "Panduit"
    assert fr.family_of("something_else") == "Other"


def test_resolve_picks_preferred_column_and_defaults():
    spec = fr.resolve("cluster_metrics", ["id", "collection_time", "timestamp"],
                      default_warn=26, default_dead=50)
    assert spec["column"] == "collection_time"      # preferred over timestamp
    assert spec["family"] == "VMware"
    assert spec["warn_hours"] == 26 and spec["dead_hours"] == 50
    assert spec["label"]                             # some human label


def test_resolve_none_when_excluded_or_no_column():
    assert fr.resolve("loki_devices", ["collection_time"], default_warn=26, default_dead=50) is None
    assert fr.resolve("t", ["id", "name"], default_warn=26, default_dead=50) is None


def test_resolve_applies_override():
    spec = fr.resolve("raw_vmware_datastore_metrics_agg",
                      ["collection_timestamp"], default_warn=26, default_dead=50)
    assert spec["label"] == "VMware Datastore Metrics"   # from OVERRIDES
