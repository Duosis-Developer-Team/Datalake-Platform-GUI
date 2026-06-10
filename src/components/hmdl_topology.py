"""HMDL topology visualization — React Flow wrapper with legacy fallback."""

from __future__ import annotations

import dash_hmdl_flow
import dash_mantine_components as dmc
from dash import html

from src.utils.hmdl_sync_ui import node_status_badge, proxy_config_badge, sync_status_badge


def build_topology_graph(topology: dict) -> html.Div:
    nodes = topology.get("nodes") or []
    if not nodes:
        return dmc.Alert(
            "No root Loki locations available. Verify public.loki_locations is synced.",
            color="orange",
            variant="light",
        )

    return html.Div(
        [
            dash_hmdl_flow.HmdlFlow(
                id="hmdl-topology-flow",
                topologyData=topology,
                hubDc=str(topology.get("hub_dc") or "DC13"),
                height=640,
            ),
            html.Div(
                style={"marginTop": "12px"},
                children=dmc.Group(
                    justify="center",
                    gap="md",
                    children=[
                        sync_status_badge("loki_synced"),
                        sync_status_badge("not_synced"),
                        proxy_config_badge(),
                        dmc.Text(
                            "Click location to expand NiFi · Sync Health button for detail · Drag to rearrange",
                            size="xs",
                            c="dimmed",
                        ),
                    ],
                ),
            ),
        ]
    )


def build_topology_legend_only() -> html.Div:
    """Compact legend for tests and documentation."""
    return html.Div(
        children=[
            node_status_badge({"proxy_config_status": "configured", "loki_sync_status": "loki_synced"}),
            node_status_badge({"proxy_config_status": "configured", "loki_sync_status": "not_synced"}),
            node_status_badge({"proxy_config_status": "no_configured_proxy"}),
        ]
    )
