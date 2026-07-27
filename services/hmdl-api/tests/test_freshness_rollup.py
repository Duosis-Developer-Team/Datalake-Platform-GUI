"""Rolling per-table freshness rows up into per-collection-flow rows."""
from app.services import freshness_rollup as roll


def _row(key: str, status: str, age: float | None) -> dict:
    return {
        "key": key, "label": key, "cadence": f"public.{key}",
        "last_run_at": None, "age_hours": age, "status": status,
        "warn_hours": 26.0, "dead_hours": 50.0, "extra": {},
    }


def test_worst_status_prefers_dead_over_everything():
    assert roll.worst_status(["fresh", "stale", "dead"]) == "dead"


def test_worst_status_prefers_stale_over_fresh():
    assert roll.worst_status(["fresh", "stale", "fresh"]) == "stale"


def test_worst_status_all_unknown_is_unknown_not_fresh():
    # Absence of data is not health.
    assert roll.worst_status(["unknown", "unknown"]) == "unknown"


def test_worst_status_mixed_fresh_and_unknown_is_fresh():
    assert roll.worst_status(["fresh", "unknown"]) == "fresh"


def test_worst_status_of_nothing_is_unknown():
    assert roll.worst_status([]) == "unknown"


def test_five_dead_tables_in_one_flow_yield_one_row():
    rows = roll.build_flow_rows({
        "hypervisor_performance": [
            _row("vmware_host_performance_metrics", "dead", 1517.0),
            _row("vmware_vm_performance_metrics", "dead", 1517.0),
            _row("nutanix_host_performance_metrics", "dead", 1485.0),
            _row("nutanix_vm_performance_metrics", "dead", 1485.0),
            _row("ibm_lpar_performance_metrics", "dead", 1490.0),
        ],
    })
    assert len(rows) == 1
    assert rows[0]["status"] == "dead"
    assert rows[0]["counts"]["alert"] == 1


def test_flow_age_is_the_oldest_alerting_member():
    rows = roll.build_flow_rows({
        "vmware_datastore": [
            _row("raw_vmware_datastore_metrics_agg", "dead", 269.0),
            _row("raw_vmware_datastore_host_mount", "dead", 268.0),
        ],
    })
    assert rows[0]["age_hours"] == 269.0


def test_a_fresh_member_does_not_clear_a_dead_sibling():
    rows = roll.build_flow_rows({
        "vmware_datastore": [
            _row("raw_vmware_datastore_metrics_agg", "dead", 269.0),
            _row("raw_vmware_datastore_host_mount", "fresh", 0.4),
        ],
    })
    assert rows[0]["status"] == "dead"
    assert rows[0]["age_hours"] == 269.0


def test_healthy_flow_reports_no_age():
    rows = roll.build_flow_rows({
        "vmware_datastore": [_row("raw_vmware_datastore_metrics_agg", "fresh", 0.4)],
    })
    assert rows[0]["status"] == "fresh"
    assert rows[0]["age_hours"] is None


def test_declared_flow_uses_its_registry_label():
    rows = roll.build_flow_rows({
        "vmware_datastore": [_row("raw_vmware_datastore_metrics_agg", "dead", 269.0)],
    })
    assert rows[0]["label"] == "Depolama kullanım verisi"


def test_family_fallback_key_uses_the_family_name_as_label():
    rows = roll.build_flow_rows({
        "family:NetBox": [_row("discovery_netbox_inventory_device", "fresh", 3.0)],
    })
    assert rows[0]["label"] == "NetBox"


def test_rows_are_sorted_alerting_first():
    rows = roll.build_flow_rows({
        "family:NetBox": [_row("discovery_netbox_inventory_device", "fresh", 3.0)],
        "vmware_datastore": [_row("raw_vmware_datastore_metrics_agg", "dead", 269.0)],
    })
    assert [r["key"] for r in rows] == ["vmware_datastore", "family:NetBox"]


def test_member_rows_are_carried_through_for_the_detail_disclosure():
    rows = roll.build_flow_rows({
        "vmware_datastore": [
            _row("raw_vmware_datastore_metrics_agg", "dead", 269.0),
            _row("raw_vmware_datastore_host_mount", "dead", 268.0),
        ],
    })
    assert [s["key"] for s in rows[0]["sources"]] == [
        "raw_vmware_datastore_metrics_agg", "raw_vmware_datastore_host_mount",
    ]


def test_flow_key_for_uses_the_declared_flow():
    assert roll.flow_key_for("raw_vmware_datastore_metrics_agg", "VMware") == "vmware_datastore"


def test_flow_key_for_falls_back_to_family():
    assert roll.flow_key_for("cluster_metrics", "VMware") == "family:VMware"


def test_flow_counts_tallies_across_flows():
    rows = roll.build_flow_rows({
        "vmware_datastore": [_row("raw_vmware_datastore_metrics_agg", "dead", 269.0)],
        "family:NetBox": [_row("discovery_netbox_inventory_device", "fresh", 3.0)],
    })
    counts = roll.flow_counts(rows)
    assert counts["alert"] == 1
    assert counts["dead"] == 1
    assert counts["fresh"] == 1
