"""Unit tests for Loki-driven topology builder."""

from unittest.mock import patch

from app.services import topology_builder


ROOT_LOCATIONS = [
    {"id": 10, "name": "DC13", "description": "Hub", "site_name": "IST", "status_value": "active"},
    {"id": 20, "name": "DC20", "description": "New site", "site_name": "ANK", "status_value": "active"},
]

CATALOG = {
    "DC13": {
        "dc_code": "DC13",
        "proxies": [
            {
                "id": "DC13-NIFI1",
                "proxy_nifi_host": "10.134.16.10",
                "ssh_user": "root",
                "conf_path": "/Datalake_Project/configuration_file.json",
                "gitea_audit_path": "proxies/dc13/nifi1/configuration_file.json",
            }
        ],
    }
}


@patch("app.services.topology_builder.loki_q.fetch_root_locations", return_value=ROOT_LOCATIONS)
@patch("app.services.topology_builder.load_proxy_catalog", return_value=CATALOG)
@patch("app.services.topology_builder.proxies_for_dc")
def test_build_location_nodes_marks_missing_proxy(mock_proxies, mock_catalog, mock_roots):
    def _proxies(dc_code: str):
        return CATALOG.get(dc_code, {}).get("proxies", [])

    mock_proxies.side_effect = _proxies
    logs = {
        "DC13-NIFI1": {
            "dry_run": False,
            "status": "completed",
            "finished_at": None,
            "run_id": "run-1",
        }
    }
    stats = {"DC13-NIFI1": {"total": 4, "distributed": 4}}

    nodes = topology_builder.build_location_nodes(hub_dc="DC13", logs=logs, stats=stats)
    assert len(nodes) == 2

    dc13 = next(n for n in nodes if n["location_name"] == "DC13")
    assert dc13["proxy_config_status"] == "configured"
    assert dc13["loki_sync_status"] == "loki_synced"
    assert dc13["role"] == "hub"

    dc20 = next(n for n in nodes if n["location_name"] == "DC20")
    assert dc20["proxy_config_status"] == "no_configured_proxy"
    assert dc20["loki_sync_status"] is None
    assert dc20["proxies"] == []


@patch("app.services.topology_builder.loki_q.fetch_root_locations", return_value=ROOT_LOCATIONS)
@patch("app.services.topology_builder.load_proxy_catalog", return_value=CATALOG)
@patch("app.services.topology_builder.proxies_for_dc")
def test_build_topology_payload_counts_and_edges(mock_proxies, mock_catalog, mock_roots):
    mock_proxies.side_effect = lambda dc: CATALOG.get(dc, {}).get("proxies", [])
    payload = topology_builder.build_topology_payload(
        "DC13",
        last_run={"run_id": "run-1", "finished_at": None},
        logs={
            "DC13-NIFI1": {
                "dry_run": False,
                "status": "completed",
                "finished_at": None,
                "run_id": "run-1",
            }
        },
        stats={"DC13-NIFI1": {"total": 2, "distributed": 2}},
    )

    assert payload["total_dc_count"] == 2
    assert payload["synced_dc_count"] == 1
    assert payload["no_configured_proxy_count"] == 1
    assert payload["source_node"]["id"] == "LOKI"

    collection_edges = [e for e in payload["edges"] if e["edge_type"] == "collection"]
    assert len(collection_edges) == 2
    assert any(e["to_dc"] == "DC20" for e in collection_edges)

    distribution_edges = [e for e in payload["edges"] if e["edge_type"] == "distribution"]
    assert len(distribution_edges) == 1
    assert distribution_edges[0]["to_dc"] == "DC13-NIFI1"
