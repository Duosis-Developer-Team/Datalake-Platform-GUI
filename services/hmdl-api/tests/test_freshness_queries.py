"""Discover collected data tables + compute their freshness, grouped by family."""
from unittest.mock import patch

from app.db.queries import freshness as fq


def test_discover_specs_filters_excluded_and_resolves():
    info_rows = [
        {"table_name": "cluster_metrics", "cols": ["collection_time"]},
        {"table_name": "loki_devices", "cols": ["collection_time"]},   # excluded
        {"table_name": "some_lookup", "cols": ["id", "name"]},          # no freshness col
    ]
    with patch.object(fq.pool, "fetch_all", return_value=info_rows):
        specs = fq.discover_specs()
    assert {s["table"] for s in specs} == {"cluster_metrics"}


def test_compute_freshness_groups_by_family_and_counts():
    specs = [
        {"table": "cluster_metrics", "column": "collection_time", "label": "VMware Clusters",
         "family": "VMware", "warn_hours": 26, "dead_hours": 50},
        {"table": "raw_vmware_datastore_metrics_agg", "column": "collection_timestamp",
         "label": "VMware Datastore Metrics", "family": "VMware", "warn_hours": 26, "dead_hours": 50},
        {"table": "nutanix_cluster_metrics", "column": "collection_time", "label": "Nutanix Clusters",
         "family": "Nutanix", "warn_hours": 26, "dead_hours": 50},
    ]
    ages = [{"age_hours": 1.0}, {"age_hours": 240.0}, {"age_hours": 0.5}]  # fresh, dead, fresh
    with patch.object(fq, "discover_specs", return_value=specs), \
         patch.object(fq.pool, "fetch_one", side_effect=ages):
        out = fq.compute_freshness()
    fams = {f["family"]: f for f in out["families"]}
    assert set(fams) == {"VMware", "Nutanix"}
    assert fams["VMware"]["counts"]["dead"] == 1
    assert fams["VMware"]["counts"]["fresh"] == 1
    assert fams["Nutanix"]["counts"]["fresh"] == 1
    assert out["counts"]["dead"] == 1
    assert out["counts"]["alert"] == 1


def test_compute_freshness_clamps_negative_age():
    specs = [{"table": "cluster_metrics", "column": "collection_time", "label": "L",
              "family": "VMware", "warn_hours": 26, "dead_hours": 50}]
    with patch.object(fq, "discover_specs", return_value=specs), \
         patch.object(fq.pool, "fetch_one", return_value={"age_hours": -3.0}):
        out = fq.compute_freshness()
    src = out["families"][0]["sources"][0]
    assert src["age_hours"] == 0.0
    assert src["status"] == "fresh"


def test_compute_freshness_splits_monitored_from_unmonitored(monkeypatch):
    from app.db.queries import freshness as fq

    monkeypatch.setattr(fq, "discover_specs", lambda: [
        {"table": "raw_vmware_datastore_metrics_agg", "column": "collection_timestamp",
         "label": "VMware Datastore Metrics", "family": "VMware", "monitored": True,
         "warn_hours": 26.0, "dead_hours": 50.0},
        {"table": "raw_panduit_pdu_inventory", "column": "collection_time",
         "label": "Raw Panduit Pdu Inventory", "family": "Panduit", "monitored": False,
         "warn_hours": 26.0, "dead_hours": 50.0},
    ])
    monkeypatch.setattr(fq, "_age_hours", lambda table, col: 1600.0)

    result = fq.compute_freshness()

    assert [u["key"] for u in result["unmonitored"]] == ["raw_panduit_pdu_inventory"]
    # The unmonitored dead table raises no alert.
    assert result["counts"]["alert"] == 1


def test_compute_freshness_counts_flows_not_tables(monkeypatch):
    from app.db.queries import freshness as fq

    perf = [
        "vmware_host_performance_metrics", "vmware_vm_performance_metrics",
        "nutanix_host_performance_metrics", "nutanix_vm_performance_metrics",
        "ibm_lpar_performance_metrics",
    ]
    monkeypatch.setattr(fq, "discover_specs", lambda: [
        {"table": t, "column": "collection_time", "label": t, "family": "VMware",
         "monitored": True, "warn_hours": 26.0, "dead_hours": 50.0}
        for t in perf
    ])
    monkeypatch.setattr(fq, "_age_hours", lambda table, col: 1500.0)

    result = fq.compute_freshness()

    assert len(result["flows"]) == 1
    assert result["flows"][0]["key"] == "hypervisor_performance"
    assert result["counts"]["alert"] == 1  # not 5


def test_compute_freshness_still_emits_families(monkeypatch):
    from app.db.queries import freshness as fq

    monkeypatch.setattr(fq, "discover_specs", lambda: [
        {"table": "cluster_metrics", "column": "collection_time", "label": "VMware Clusters",
         "family": "VMware", "monitored": True, "warn_hours": 26.0, "dead_hours": 50.0},
    ])
    monkeypatch.setattr(fq, "_age_hours", lambda table, col: 0.5)

    result = fq.compute_freshness()

    assert [f["family"] for f in result["families"]] == ["VMware"]


def test_unmonitored_table_that_is_fresh_still_appears(monkeypatch):
    from app.db.queries import freshness as fq

    monkeypatch.setattr(fq, "discover_specs", lambda: [
        {"table": "raw_brocade_fabric_devices", "column": "collection_time",
         "label": "Raw Brocade Fabric Devices", "family": "Other", "monitored": False,
         "warn_hours": 26.0, "dead_hours": 50.0},
    ])
    monkeypatch.setattr(fq, "_age_hours", lambda table, col: 0.1)

    result = fq.compute_freshness()

    assert len(result["unmonitored"]) == 1
    assert result["counts"]["alert"] == 0


def test_monitored_table_missing_from_discovery_surfaces_as_unknown(monkeypatch):
    """A stale MONITORED entry (table renamed or dropped) must be visible.

    Silently vanishing is how curation rots: the set would keep naming a table
    nobody can find and nobody would ever learn.
    """
    from app.db.queries import freshness as fq

    monkeypatch.setattr(fq, "discover_specs", lambda: [
        {"table": "cluster_metrics", "column": "collection_time", "label": "VMware Clusters",
         "family": "VMware", "monitored": True, "warn_hours": 26.0, "dead_hours": 50.0},
    ])
    monkeypatch.setattr(fq, "_age_hours", lambda table, col: 0.5)

    result = fq.compute_freshness()

    missing = result["missing"]
    # Everything in MONITORED except the one table discovery returned.
    assert "raw_vmware_datastore_metrics_agg" in missing
    assert "cluster_metrics" not in missing
