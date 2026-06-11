"""Integrations — HMDL collector topology overview."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import dcc, html
from dash_iconify import DashIconify

from src.components.hmdl_topology import build_topology_graph
from src.services import api_client as api
from src.utils.hmdl_sync_ui import (
    build_coverage_summary,
    node_status_badge,
    proxy_config_badge,
    sync_status_badge,
)
from src.utils.ui_tokens import kpi_card, section_header, settings_page_shell


def build_layout(search: str | None = None) -> html.Div:
    topology = api.get_hmdl_topology()
    summary = api.get_hmdl_sync_summary()

    synced = int(summary.get("synced_dc_count") or topology.get("synced_dc_count") or 0)
    total = int(summary.get("total_dc_count") or topology.get("total_dc_count") or 0)
    configured = int(summary.get("configured_location_count") or topology.get("configured_location_count") or 0)
    no_proxy = int(summary.get("no_configured_proxy_count") or topology.get("no_configured_proxy_count") or 0)
    last_run = summary.get("last_prod_run_id") or topology.get("last_prod_run_id") or "—"

    kpis = dmc.SimpleGrid(
        cols=4,
        spacing="md",
        children=[
            kpi_card(
                "Locations synced",
                f"{synced}/{total}",
                icon="solar:server-path-bold-duotone",
                color="green" if synced == total and total else "orange",
            ),
            kpi_card(
                "With proxy",
                str(configured),
                icon="solar:transfer-horizontal-bold-duotone",
                color="indigo",
            ),
            kpi_card(
                "No configured proxy",
                str(no_proxy),
                icon="solar:plug-circle-bold-duotone",
                color="gray" if no_proxy == 0 else "orange",
            ),
            kpi_card(
                "Last prod run",
                str(last_run)[:24],
                icon="solar:history-bold-duotone",
                color="violet",
            ),
        ],
    )

    coverage = api.get_hmdl_coverage()
    coverage_card = dmc.Paper(
        p="lg",
        radius="md",
        withBorder=True,
        mt="lg",
        children=[
            section_header(
                "Datalake Coverage",
                "Cluster (VMware/Nutanix) ve IBM host bazında veri çekme kapsamı — detay için Datalake Sync Health sekmesi.",
                icon="solar:checklist-minimalistic-bold-duotone",
            ),
            build_coverage_summary(coverage.get("summary") or {}),
        ],
    )

    topo_card = dmc.Paper(
        p="lg",
        radius="md",
        withBorder=True,
        children=[
            section_header(
                "DC13 ETL hub — remote proxy ingestion",
                f"Remote NiFi proxies ingest toward central hub {topology.get('hub_dc', 'DC13')}. Click a location to expand NiFi nodes.",
                icon="solar:diagram-up-bold-duotone",
            ),
            dcc.Loading(build_topology_graph(topology), type="circle"),
        ],
    )

    proxy_rows = []
    unconfigured_rows = []
    for node in topology.get("nodes") or []:
        dc_label = str(node.get("dc_code") or node.get("location_name") or "")
        if node.get("proxy_config_status") == "no_configured_proxy":
            unconfigured_rows.append(
                html.Tr(
                    children=[
                        html.Td(dc_label),
                        html.Td(str(node.get("location_name") or "")),
                        html.Td(str(node.get("site_name") or "—")),
                        html.Td(proxy_config_badge()),
                    ]
                )
            )
            continue
        for p in node.get("proxies") or []:
            proxy_rows.append(
                html.Tr(
                    children=[
                        html.Td(dc_label),
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

    unconfigured_table = dmc.Paper(
        p="lg",
        radius="md",
        withBorder=True,
        mt="lg",
        children=[
            section_header(
                "Locations without proxy",
                "Root Loki locations with no proxy_assignment.yml entry (AWX inventory unknown).",
                icon="solar:map-point-wave-bold-duotone",
            ),
            html.Div(
                style={"overflowX": "auto"},
                children=[
                    html.Table(
                        [
                            html.Tr(
                                [
                                    html.Th("DC code"),
                                    html.Th("Location"),
                                    html.Th("Site"),
                                    html.Th("Status"),
                                ]
                            ),
                            *unconfigured_rows,
                        ],
                        style={"width": "100%", "fontSize": "13px", "borderCollapse": "collapse"},
                    )
                    if unconfigured_rows
                    else dmc.Text("All root locations have a configured proxy.", size="sm", c="dimmed"),
                ],
            ),
        ],
    ) if unconfigured_rows else html.Div()

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
                                    "Loki root locations mapped to NiFi proxy nodes — read-only AWX sync state.",
                                    size="sm",
                                    c="dimmed",
                                ),
                            ],
                        ),
                    ],
                ),
                kpis,
                coverage_card,
                dmc.Space(h="lg"),
                topo_card,
                table,
                unconfigured_table,
                dcc.Store(id="hmdl-topology-store", data=topology),
            ]
        )
    )
