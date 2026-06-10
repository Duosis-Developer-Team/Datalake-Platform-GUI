"""Integrations — HMDL collector topology overview."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import dcc, html
from dash_iconify import DashIconify

from src.components.hmdl_topology import build_topology_graph
from src.services import api_client as api
from src.utils.hmdl_sync_ui import sync_status_badge
from src.utils.ui_tokens import kpi_card, section_header, settings_page_shell


def build_layout(search: str | None = None) -> html.Div:
    topology = api.get_hmdl_topology()
    summary = api.get_hmdl_sync_summary()

    synced = int(summary.get("synced_dc_count") or topology.get("synced_dc_count") or 0)
    total = int(summary.get("total_dc_count") or topology.get("total_dc_count") or 0)
    last_run = summary.get("last_prod_run_id") or topology.get("last_prod_run_id") or "—"

    kpis = dmc.SimpleGrid(
        cols=3,
        spacing="md",
        children=[
            kpi_card(
                "DCs synced",
                f"{synced}/{total}",
                icon="solar:server-path-bold-duotone",
                color="green" if synced == total and total else "orange",
            ),
            kpi_card(
                "Proxies synced",
                f"{summary.get('synced_proxy_count', 0)}/{summary.get('total_proxy_count', 0)}",
                icon="solar:transfer-horizontal-bold-duotone",
                color="indigo",
            ),
            kpi_card(
                "Last prod run",
                str(last_run)[:24],
                icon="solar:history-bold-duotone",
                color="violet",
            ),
        ],
    )

    topo_card = dmc.Paper(
        p="lg",
        radius="md",
        withBorder=True,
        children=[
            section_header(
                "NiFi hub-spoke topology",
                f"Central hub {topology.get('hub_dc', 'DC13')} — remote datacenter proxy nodes.",
                icon="solar:diagram-up-bold-duotone",
            ),
            dcc.Loading(build_topology_graph(topology), type="circle"),
        ],
    )

    proxy_rows = []
    for node in topology.get("nodes") or []:
        for p in node.get("proxies") or []:
            proxy_rows.append(
                html.Tr(
                    children=[
                        html.Td(str(node.get("dc_code") or "")),
                        html.Td(str(p.get("proxy_id") or "")),
                        html.Td(str(p.get("proxy_nifi_host") or "")),
                        html.Td(sync_status_badge(str(p.get("loki_sync_status") or "not_synced"))),
                        html.Td(str(p.get("target_count") or 0)),
                    ]
                )
            )

    table = dmc.Paper(
        p="lg",
        radius="md",
        withBorder=True,
        mt="lg",
        children=[
            section_header("Proxy inventory", "Per NiFi node sync status and target counts.", icon="solar:list-bold-duotone"),
            html.Div(
                style={"overflowX": "auto"},
                children=[
                    html.Table(
                        [
                            html.Tr(
                                [
                                    html.Th("DC"),
                                    html.Th("Proxy"),
                                    html.Th("Host"),
                                    html.Th("Loki"),
                                    html.Th("Targets"),
                                ]
                            ),
                            *proxy_rows,
                        ],
                        style={"width": "100%", "fontSize": "13px", "borderCollapse": "collapse"},
                    )
                ],
            ),
        ],
    )

    return html.Div(
        settings_page_shell(
            [
                dmc.Group(
                    mb="md",
                    children=[
                        dmc.ThemeIcon(
                            DashIconify(icon="solar:server-path-bold-duotone", width=24),
                            size="lg",
                            radius="md",
                            variant="light",
                            color="indigo",
                        ),
                        dmc.Stack(
                            gap=2,
                            children=[
                                dmc.Title("HMDL collector sync", order=3),
                                dmc.Text(
                                    "Read-only view of AWX collector sync state across datacenter NiFi proxies.",
                                    size="sm",
                                    c="dimmed",
                                ),
                            ],
                        ),
                    ],
                ),
                kpis,
                dmc.Space(h="lg"),
                topo_card,
                table,
                dcc.Store(id="hmdl-topology-store", data=topology),
            ]
        )
    )
