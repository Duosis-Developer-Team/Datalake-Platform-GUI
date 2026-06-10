"""Integrations — HMDL Datalake Sync Health detail."""

from __future__ import annotations

from urllib.parse import parse_qs

import dash_mantine_components as dmc
from dash import dcc, html

from src.services import api_client as api
from src.utils.hmdl_sync_ui import (
    CATEGORY_LABELS,
    build_diff_panel,
    build_targets_table,
    category_chip,
    sync_status_badge,
)
from src.utils.ui_tokens import kpi_card, section_header, settings_page_shell
from src.utils.hmdl_sync_ui import (
    CATEGORY_LABELS,
    build_diff_panel,
    build_targets_table,
    category_chip,
    sync_status_badge,
)
from src.utils.ui_tokens import kpi_card, section_header, settings_page_shell


def _parse_dc(search: str | None, topology: dict) -> str:
    params = parse_qs((search or "").lstrip("?"))
    dc = (params.get("dc", [""])[0] or "").strip().upper()
    if dc:
        return dc
    nodes = topology.get("nodes") or []
    if nodes:
        return str(nodes[0].get("dc_code") or "DC13").upper()
    return "DC13"


def build_layout(search: str | None = None) -> html.Div:
    topology = api.get_hmdl_topology()
    dc_options = [
        {"label": str(n.get("dc_code") or ""), "value": str(n.get("dc_code") or "")}
        for n in (topology.get("nodes") or [])
    ]
    selected_dc = _parse_dc(search, topology)

    dc_summary = api.get_hmdl_dc_summary(selected_dc)
    targets = api.get_hmdl_dc_targets(selected_dc)

    status = str(dc_summary.get("loki_sync_status") or "not_synced")
    cat_counts = dc_summary.get("category_counts") or {}

    kpis = dmc.SimpleGrid(
        cols=4,
        spacing="md",
        children=[
            kpi_card("Sync status", "Synced" if status == "loki_synced" else "Not synced", color="green" if status == "loki_synced" else "red"),
            kpi_card("Proxies", dc_summary.get("proxy_count", 0), color="indigo"),
            kpi_card("Active targets", dc_summary.get("target_count", 0), color="violet"),
            kpi_card("Last run", str(dc_summary.get("last_prod_run_id") or "—")[:20], color="gray"),
        ],
    )

    category_chips = dmc.Group(
        gap="xs",
        mb="md",
        children=[
            category_chip(cat, active=False)
            for cat in CATEGORY_LABELS
            if cat_counts.get(cat, 0) > 0
        ]
        or [dmc.Text("No category breakdown available.", size="sm", c="dimmed")],
    )

    filters = dmc.Paper(
        p="md",
        withBorder=True,
        radius="md",
        mb="md",
        children=[
            dmc.Grid(
                gutter="md",
                children=[
                    dmc.GridCol(
                        span={"base": 12, "md": 4},
                        children=dmc.Select(
                            id="hmdl-dc-select",
                            label="Datacenter",
                            data=dc_options,
                            value=selected_dc,
                            searchable=True,
                            size="sm",
                        ),
                    ),
                    dmc.GridCol(
                        span={"base": 12, "md": 4},
                        children=dmc.Select(
                            id="hmdl-category-filter",
                            label="Inclusion category",
                            data=[{"label": "All", "value": ""}]
                            + [{"label": v, "value": k} for k, v in CATEGORY_LABELS.items()],
                            value="",
                            clearable=True,
                            size="sm",
                        ),
                    ),
                    dmc.GridCol(
                        span={"base": 12, "md": 4},
                        children=dmc.TextInput(
                            id="hmdl-entity-filter",
                            label="Entity name contains",
                            placeholder="Filter by Loki entity_name…",
                            size="sm",
                        ),
                    ),
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
                        sync_status_badge(status),
                        dmc.Title(f"Datalake Sync Health — {selected_dc}", order=3),
                    ],
                ),
                kpis,
                dmc.Space(h="md"),
                category_chips,
                filters,
                dmc.Paper(
                    p="lg",
                    withBorder=True,
                    radius="md",
                    mb="lg",
                    children=[
                        section_header(
                            "Loki target inventory",
                            "Collector targets with inclusion category (platform_status, connectivity, diffs).",
                            icon="solar:database-bold-duotone",
                        ),
                        html.Div(id="hmdl-targets-table", children=build_targets_table(targets.get("items") or [])),
                    ],
                ),
                build_diff_panel(dc_summary.get("recent_diffs") or []),
                dcc.Store(id="hmdl-sync-dc-store", data=selected_dc),
            ]
        )
    )
