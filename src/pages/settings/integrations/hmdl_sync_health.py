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
    node_status_badge,
    proxy_config_badge,
)
from src.utils.ui_tokens import kpi_card, section_header, settings_page_shell


def _parse_dc(search: str | None, topology: dict) -> str:
    params = parse_qs((search or "").lstrip("?"))
    dc = (params.get("dc", [""])[0] or "").strip().upper()
    if dc:
        return dc
    for node in topology.get("nodes") or []:
        code = str(node.get("dc_code") or "").strip().upper()
        if code:
            return code
    return "DC13"


def _dc_options(topology: dict) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    for node in topology.get("nodes") or []:
        dc_code = str(node.get("dc_code") or "").strip().upper()
        if not dc_code:
            continue
        label = dc_code
        if node.get("proxy_config_status") == "no_configured_proxy":
            label = f"{dc_code} (no proxy)"
        options.append({"label": label, "value": dc_code})
    return options


def build_layout(search: str | None = None) -> html.Div:
    topology = api.get_hmdl_topology()
    dc_options = _dc_options(topology)
    selected_dc = _parse_dc(search, topology)
    selected_node = next(
        (n for n in (topology.get("nodes") or []) if str(n.get("dc_code") or "").upper() == selected_dc),
        None,
    )
    no_proxy = selected_node and selected_node.get("proxy_config_status") == "no_configured_proxy"

    dc_summary = api.get_hmdl_dc_summary(selected_dc) if selected_dc else {}
    targets = api.get_hmdl_dc_targets(selected_dc) if selected_dc and not no_proxy else {"items": []}

    status = str(dc_summary.get("loki_sync_status") or "not_synced")
    cat_counts = dc_summary.get("category_counts") or {}

    kpis = dmc.SimpleGrid(
        cols=4,
        spacing="md",
        children=[
            kpi_card(
                "Sync status",
                "No proxy" if no_proxy else ("Synced" if status == "loki_synced" else "Not synced"),
                color="gray" if no_proxy else ("green" if status == "loki_synced" else "red"),
            ),
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
                            value=selected_dc if dc_options else None,
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
                            disabled=no_proxy,
                        ),
                    ),
                    dmc.GridCol(
                        span={"base": 12, "md": 4},
                        children=dmc.TextInput(
                            id="hmdl-entity-filter",
                            label="Entity name contains",
                            placeholder="Filter by Loki entity_name…",
                            size="sm",
                            disabled=no_proxy,
                        ),
                    ),
                ],
            ),
        ],
    )

    status_badge = proxy_config_badge() if no_proxy else node_status_badge(selected_node or {"loki_sync_status": status})

    inventory_section = dmc.Paper(
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
            dmc.Alert(
                "This location exists in Loki but has no configured NiFi proxy in proxy_assignment.yml.",
                color="gray",
                variant="light",
                title="No configured proxy",
            )
            if no_proxy
            else html.Div(id="hmdl-targets-table", children=build_targets_table(targets.get("items") or [])),
        ],
    )

    return html.Div(
        settings_page_shell(
            [
                dmc.Group(
                    mb="md",
                    children=[
                        status_badge,
                        dmc.Title(f"Datalake Sync Health — {selected_dc}", order=3),
                    ],
                ),
                kpis,
                dmc.Space(h="md"),
                category_chips if not no_proxy else html.Div(),
                filters,
                inventory_section,
                build_diff_panel(dc_summary.get("recent_diffs") or []) if not no_proxy else html.Div(),
                dcc.Store(id="hmdl-sync-dc-store", data=selected_dc),
            ]
        )
    )
