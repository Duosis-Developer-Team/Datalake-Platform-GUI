"""Interactive hub-spoke HMDL collector topology (DC13 center)."""

from __future__ import annotations

import math

import dash_mantine_components as dmc
from dash import html

from src.pages.settings.admin_routes import ADMIN_PREFIX
from src.utils.hmdl_sync_ui import sync_status_badge

HUB_SIZE = 96
SPOKE_SIZE = 72
CANVAS = 520


def _node_style(*, left: float, top: float) -> dict:
    return {
        "position": "absolute",
        "left": f"{left}px",
        "top": f"{top}px",
        "textAlign": "center",
    }


def _positions(count: int, *, hub_x: float, hub_y: float, radius: float) -> list[tuple[float, float]]:
    if count <= 0:
        return []
    out = []
    for i in range(count):
        angle = (2 * math.pi * i / count) - math.pi / 2
        out.append((hub_x + radius * math.cos(angle), hub_y + radius * math.sin(angle)))
    return out


def build_topology_graph(topology: dict) -> html.Div:
    nodes = topology.get("nodes") or []
    hub_dc = str(topology.get("hub_dc") or "DC13").upper()
    hub = next((n for n in nodes if str(n.get("dc_code", "")).upper() == hub_dc), None)
    spokes = [n for n in nodes if str(n.get("dc_code", "")).upper() != hub_dc]

    cx, cy = CANVAS / 2, CANVAS / 2
    spoke_positions = _positions(len(spokes), hub_x=cx, hub_y=cy, radius=190)

    inner: list = []
    canvas = html.Div(
        style={"position": "relative", "width": f"{CANVAS}px", "height": f"{CANVAS}px", "margin": "0 auto"},
        children=inner,
    )

    if hub:
        inner.append(
            html.Div(
                style=_node_style(left=cx - HUB_SIZE / 2, top=cy - HUB_SIZE / 2),
                children=[
                    dmc.Anchor(
                        dmc.Paper(
                            p="sm",
                            radius="md",
                            withBorder=True,
                            style={
                                "borderColor": "#552cf8",
                                "background": "linear-gradient(135deg,#f6f2ff,#ffffff)",
                            },
                            children=[
                                dmc.Text(hub_dc, fw=800, size="sm"),
                                sync_status_badge(str(hub.get("loki_sync_status") or "not_synced")),
                                dmc.Text(f"{len(hub.get('proxies') or [])} proxy", size="xs", c="dimmed"),
                            ],
                        ),
                        href=f"{ADMIN_PREFIX}/integrations/hmdl/sync-health?dc={hub_dc}",
                        underline=False,
                    )
                ],
            )
        )

    for i, spoke in enumerate(spokes):
        if i >= len(spoke_positions):
            break
        sx, sy = spoke_positions[i]
        dc = str(spoke.get("dc_code") or "")
        inner.append(
            html.Div(
                style=_node_style(left=sx - SPOKE_SIZE / 2, top=sy - SPOKE_SIZE / 2),
                children=[
                    dmc.Anchor(
                        dmc.Paper(
                            p="xs",
                            radius="md",
                            withBorder=True,
                            children=[
                                dmc.Text(dc, fw=700, size="xs"),
                                sync_status_badge(str(spoke.get("loki_sync_status") or "not_synced")),
                            ],
                        ),
                        href=f"{ADMIN_PREFIX}/integrations/hmdl/sync-health?dc={dc}",
                        underline=False,
                    )
                ],
            )
        )

    legend = dmc.Group(
        justify="center",
        mt="md",
        children=[
            sync_status_badge("loki_synced"),
            sync_status_badge("not_synced"),
            dmc.Text("Click a node for Sync Health detail", size="xs", c="dimmed"),
        ],
    )

    return html.Div([canvas, legend])
