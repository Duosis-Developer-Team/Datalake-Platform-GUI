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
