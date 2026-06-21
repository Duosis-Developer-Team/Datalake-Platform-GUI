"""Integrations — HMDL Datalake Sync Health detail."""

from __future__ import annotations

from urllib.parse import parse_qs

import dash_mantine_components as dmc
from dash import dcc, html

from src.pages.settings.admin_routes import ADMIN_PREFIX
from src.services import api_client as api
from src.utils.hmdl_sync_ui import (
    CATEGORY_LABELS,
    build_diff_panel,
    build_environment_health_grid,
    build_targets_table,
    category_chip,
    environment_status_badge,
    proxy_config_badge,
)
from src.utils.ui_tokens import kpi_card, section_header, settings_page_shell


def _parse_dc(search: str | None, locations: list[dict]) -> str:
    params = parse_qs((search or "").lstrip("?"))
    dc = (params.get("dc", [""])[0] or "").strip().upper()
    if dc:
        return dc
    for loc in locations:
        code = str(loc.get("dc_code") or "").strip().upper()
        if code:
            return code
    return "DC13"


def _dc_options(locations: list[dict]) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    for loc in locations:
        dc_code = str(loc.get("dc_code") or "").strip().upper()
        if not dc_code:
            continue
        env = str(loc.get("environment_status") or "")
        suffix = ""
        if env == "connectivity_issue":
            suffix = " · connectivity issue"
        elif env == "no_configured_proxy":
            suffix = " · no proxy"
        options.append({"label": f"{dc_code}{suffix}", "value": dc_code})
    return options


def build_layout(search: str | None = None) -> html.Div:
    locations_data = api.get_hmdl_locations()
    locations = locations_data.get("items") or []
    summary = api.get_hmdl_sync_summary()

    connected = int(summary.get("connected_environment_count") or 0)
    connectivity = int(summary.get("connectivity_issue_environment_count") or 0)
    no_proxy = int(summary.get("no_configured_proxy_count") or 0)

    selected_dc = _parse_dc(search, locations)
    dc_options = _dc_options(locations)
    selected_loc = next(
        (loc for loc in locations if str(loc.get("dc_code") or "").upper() == selected_dc),
        None,
    )
    no_proxy_dc = selected_loc and selected_loc.get("proxy_config_status") == "no_configured_proxy"
    env_status = str(selected_loc.get("environment_status") or "") if selected_loc else ""

    dc_summary = api.get_hmdl_dc_summary(selected_dc) if selected_dc else {}
    targets = api.get_hmdl_dc_targets(selected_dc) if selected_dc and not no_proxy_dc else {"items": []}

    cat_counts = dc_summary.get("category_counts") or {}

    env_kpis = dmc.SimpleGrid(
        cols=3,
        spacing="md",
        mb="lg",
        children=[
            kpi_card("Connected", str(connected), color="green"),
            kpi_card("Connectivity issue", str(connectivity), color="orange" if connectivity else "gray"),
            kpi_card("No configured proxy", str(no_proxy), color="gray" if no_proxy == 0 else "orange"),
        ],
    )

    env_overview = dmc.Paper(
        p="lg",
        withBorder=True,
        radius="md",
        mb="lg",
        children=[
            section_header(
                "Environment overview",
                "All Loki root locations — click a card to inspect targets below.",
                icon="solar:server-path-bold-duotone",
            ),
            build_environment_health_grid(locations, selected_dc),
        ],
    )

    detail_kpis = dmc.SimpleGrid(
        cols=4,
        spacing="md",
        children=[
            kpi_card(
                "Environment",
                "No proxy"
                if no_proxy_dc
                else ("Connected" if env_status == "connected" else "Connectivity issue" if env_status == "connectivity_issue" else "—"),
                color="gray"
                if no_proxy_dc
                else ("green" if env_status == "connected" else "orange" if env_status == "connectivity_issue" else "red"),
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
        or [dmc.Text("No target category breakdown for this environment.", size="sm", c="dimmed")],
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
                            disabled=no_proxy_dc,
                        ),
                    ),
                    dmc.GridCol(
                        span={"base": 12, "md": 4},
                        children=dmc.TextInput(
                            id="hmdl-entity-filter",
                            label="Entity name contains",
                            placeholder="Filter by Loki entity_name…",
                            size="sm",
                            disabled=no_proxy_dc,
                        ),
                    ),
                ],
            ),
        ],
    )

    status_badge = (
        proxy_config_badge()
        if no_proxy_dc
        else environment_status_badge(
            env_status,
            issue_count=int(selected_loc.get("connectivity_issue_count") or 0) if selected_loc else 0,
        )
    )

    inventory_section = dmc.Paper(
        p="lg",
        withBorder=True,
        radius="md",
        mb="lg",
        children=[
            section_header(
                "Loki target inventory",
                "Per-target inclusion category from last prod sync checks.",
                icon="solar:database-bold-duotone",
            ),
            dmc.Alert(
                "This location exists in Loki but has no configured NiFi proxy in proxy_assignment.yml.",
                color="gray",
                variant="light",
                title="No configured proxy",
            )
            if no_proxy_dc
            else html.Div(id="hmdl-targets-table", children=build_targets_table(targets.get("items") or [])),
        ],
    )

    coverage_link = dmc.Paper(
        p="md",
        withBorder=True,
        radius="md",
        mb="lg",
        children=[
            dmc.Group(
                justify="space-between",
                children=[
                    dmc.Text(
                        "Cluster and IBM host coverage is on the dedicated Datalake Coverage page.",
                        size="sm",
                    ),
                    dmc.Anchor(
                        dmc.Button("Open Datalake Coverage", variant="light", size="sm"),
                        href=f"{ADMIN_PREFIX}/integrations/hmdl/coverage?dc={selected_dc}",
                        underline=False,
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
                        dmc.Title("Datalake Sync Health", order=3),
                        dmc.Text("Environment connectivity across all Loki root locations.", size="sm", c="dimmed"),
                    ],
                ),
                env_kpis,
                env_overview,
                dmc.Divider(my="md", label=f"Detail — {selected_dc}"),
                dmc.Group(
                    mb="md",
                    children=[
                        status_badge,
                        dmc.Title(f"{selected_dc}", order=4),
                    ],
                ),
                detail_kpis,
                dmc.Space(h="md"),
                category_chips if not no_proxy_dc else html.Div(),
                filters,
                inventory_section,
                build_diff_panel(dc_summary.get("recent_diffs") or []) if not no_proxy_dc else html.Div(),
                coverage_link,
                dcc.Store(id="hmdl-sync-dc-store", data=selected_dc),
            ]
        )
    )
