"""Integrations — HMDL Datalake Coverage (cluster / IBM host present-absent)."""

from __future__ import annotations

from urllib.parse import parse_qs

import dash_mantine_components as dmc
from dash import dcc, html

from src.pages.settings.admin_routes import ADMIN_PREFIX
from src.services import api_client as api
from src.utils.hmdl_sync_ui import build_coverage_section
from src.utils.ui_tokens import section_header, settings_page_shell


def _parse_dc(search: str | None, locations: list[dict]) -> str:
    params = parse_qs((search or "").lstrip("?"))
    dc = (params.get("dc", [""])[0] or "").strip().upper()
    if dc:
        return dc
    for loc in locations:
        code = str(loc.get("dc_code") or "").strip().upper()
        if code:
            return code
    return ""


def _dc_options(locations: list[dict]) -> list[dict[str, str]]:
    options: list[dict[str, str]] = [{"label": "All locations", "value": ""}]
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
    selected_dc = _parse_dc(search, locations)
    dc_options = _dc_options(locations)

    coverage = api.get_hmdl_coverage(dc=selected_dc or None)
    source_filter = ""

    sync_health_href = f"{ADMIN_PREFIX}/integrations/hmdl/sync-health"
    if selected_dc:
        sync_health_href = f"{sync_health_href}?dc={selected_dc}"

    return html.Div(
        settings_page_shell(
            [
                dmc.Group(
                    mb="md",
                    children=[
                        dmc.Title("Datalake Coverage", order=3),
                        dmc.Text(
                            "Cluster (VMware/Nutanix) and IBM host collection scope — aligned with Loki root locations.",
                            size="sm",
                            c="dimmed",
                        ),
                    ],
                ),
                dmc.Alert(
                    children=[
                        "Location list matches ",
                        dmc.Anchor("Loki target inventory", href=sync_health_href, underline="always"),
                        " (same Loki root locations). Compare per-target inclusion on Sync Health.",
                    ],
                    color="blue",
                    variant="light",
                    mb="md",
                ),
                dmc.Paper(
                    p="lg",
                    withBorder=True,
                    radius="md",
                    children=[
                        section_header(
                            "Coverage report",
                            "Whether virtualization inventory is collected (live/stale/missing) and why.",
                            icon="solar:checklist-minimalistic-bold-duotone",
                        ),
                        dmc.Grid(
                            gutter="md",
                            mb="md",
                            children=[
                                dmc.GridCol(
                                    span={"base": 12, "md": 4},
                                    children=dmc.Select(
                                        id="hmdl-coverage-dc",
                                        label="Location",
                                        data=dc_options,
                                        value=selected_dc,
                                        clearable=True,
                                        searchable=True,
                                        size="sm",
                                    ),
                                ),
                                dmc.GridCol(
                                    span={"base": 12, "md": 4},
                                    children=dmc.Select(
                                        id="hmdl-coverage-source",
                                        label="Source",
                                        data=[
                                            {"label": "All", "value": ""},
                                            {"label": "VMware cluster", "value": "vmware"},
                                            {"label": "Nutanix cluster", "value": "nutanix"},
                                            {"label": "IBM host", "value": "ibm"},
                                        ],
                                        value=source_filter,
                                        clearable=True,
                                        size="sm",
                                    ),
                                ),
                            ],
                        ),
                        html.Div(
                            id="hmdl-coverage-content",
                            children=build_coverage_section(coverage),
                        ),
                    ],
                ),
                dcc.Location(id="hmdl-coverage-url-sync", refresh=False),
            ]
        )
    )
