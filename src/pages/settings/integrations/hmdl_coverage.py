"""Integrations — HMDL Datalake Coverage (Virtualization + Backup hub-spoke)."""

from __future__ import annotations

from urllib.parse import parse_qs

import dash_mantine_components as dmc
from dash import dcc, html

from src.pages.settings.admin_routes import ADMIN_PREFIX
from src.services import api_client as api
from src.utils.hmdl_probe_ui import build_probe_section
from src.utils.hmdl_sync_ui import (
    build_coverage_backup_section,
    build_coverage_virtualization_section,
)
from src.utils.ui_tokens import section_header, settings_page_shell


def _parse_dc(search: str | None) -> str:
    """Empty means "All locations" — the page must not fall back to a single DC."""
    params = parse_qs((search or "").lstrip("?"))
    return (params.get("dc", [""])[0] or "").strip().upper()


def _parse_product(search: str | None) -> str:
    params = parse_qs((search or "").lstrip("?"))
    raw = (params.get("product", ["vmware"])[0] or "vmware").strip().lower()
    return raw if raw in ("vmware", "nutanix", "ibm") else "vmware"


def _parse_backup_product(search: str | None) -> str:
    params = parse_qs((search or "").lstrip("?"))
    raw = (params.get("bp", ["netbackup"])[0] or "netbackup").strip().lower()
    return raw if raw in ("netbackup", "veeam", "zerto", "nutanix_snapshot") else "netbackup"


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
    selected_dc = _parse_dc(search)
    product = _parse_product(search)
    backup_product = _parse_backup_product(search)
    dc_options = _dc_options(locations)

    coverage = api.get_hmdl_coverage(dc=selected_dc or None, source=product)
    backup_coverage = api.get_hmdl_coverage(dc=selected_dc or None, source=backup_product)

    sync_health_href = f"{ADMIN_PREFIX}/integrations/hmdl/sync-health"
    if selected_dc:
        sync_health_href = f"{sync_health_href}?dc={selected_dc}"

    virt_panel = dmc.Paper(
        p="lg",
        withBorder=True,
        radius="md",
        children=[
            dmc.Group(
                justify="space-between",
                align="flex-end",
                mb="md",
                children=[
                    dmc.SegmentedControl(
                        id="hmdl-coverage-product",
                        value=product,
                        size="md",
                        radius="md",
                        color="indigo",
                        data=[
                            {"label": "VMware", "value": "vmware"},
                            {"label": "Nutanix", "value": "nutanix"},
                            {"label": "IBM", "value": "ibm"},
                        ],
                    ),
                    dmc.Select(
                        id="hmdl-coverage-dc",
                        label="Location",
                        data=dc_options,
                        value=selected_dc,
                        clearable=True,
                        searchable=True,
                        size="sm",
                        w=260,
                    ),
                ],
            ),
            html.Div(
                id="hmdl-coverage-content",
                children=build_coverage_virtualization_section(
                    coverage,
                    product=product,
                    selected_dc=selected_dc or None,
                ),
            ),
        ],
    )

    backup_panel = dmc.Paper(
        p="lg",
        withBorder=True,
        radius="md",
        children=[
            dmc.Group(
                justify="space-between",
                align="flex-end",
                mb="md",
                children=[
                    dmc.SegmentedControl(
                        id="hmdl-backup-product",
                        value=backup_product,
                        size="md",
                        radius="md",
                        color="blue",
                        data=[
                            {"label": "NetBackup", "value": "netbackup"},
                            {"label": "Veeam", "value": "veeam"},
                            {"label": "Zerto", "value": "zerto"},
                            {"label": "Nutanix Snapshot", "value": "nutanix_snapshot"},
                        ],
                    ),
                    dmc.Select(
                        id="hmdl-backup-dc",
                        label="Location",
                        data=dc_options,
                        value=selected_dc,
                        clearable=True,
                        searchable=True,
                        size="sm",
                        w=260,
                    ),
                ],
            ),
            html.Div(
                id="hmdl-backup-content",
                children=build_coverage_backup_section(
                    backup_coverage,
                    product=backup_product,
                    selected_dc=selected_dc or None,
                ),
            ),
        ],
    )

    probe_panel = dmc.Paper(
        p="lg",
        withBorder=True,
        radius="md",
        children=[
            section_header(
                "Collector script healthcheck",
                "Collector script'lerinin endpoint bazında çalıştırma sonucunu izler. "
                "Coverage metrik varlığını; bu ekran script yürütmesinin başarısını gösterir.",
                icon="solar:test-tube-bold-duotone",
            ),
            dmc.Group(
                justify="flex-end",
                mb="md",
                children=[
                    dmc.Select(
                        id="hmdl-probe-dc",
                        label="Location",
                        data=dc_options,
                        value=selected_dc,
                        clearable=True,
                        searchable=True,
                        size="sm",
                        w=260,
                    )
                ],
            ),
            dcc.Store(id="hmdl-probe-selected-cell", data=None),
            html.Div(
                id="hmdl-probe-content",
                children=build_probe_section(
                    api.get_hmdl_probe_health(selected_dc or None),
                ),
            ),
        ],
    )

    return html.Div(
        settings_page_shell(
            [
                dmc.Tabs(
                    id="hmdl-coverage-domain",
                    value="virtualization",
                    variant="pills",
                    radius="md",
                    color="indigo",
                    children=[
                        dmc.TabsList(
                            mb="md",
                            children=[
                                dmc.TabsTab("Virtualization", value="virtualization"),
                                dmc.TabsTab("Backup", value="backup"),
                                dmc.TabsTab("Script Healthcheck", value="probe"),
                            ],
                        ),
                        dmc.Title("Datalake Coverage", order=3, mb="md"),
                        dmc.Alert(
                            children=[
                                "Location listesi ",
                                dmc.Anchor(
                                    "Loki target inventory", href=sync_health_href, underline="always"
                                ),
                                " ile aynı. Kırmızı düğüm = eksik/kısmi veri.",
                            ],
                            color="blue",
                            variant="light",
                            mb="md",
                        ),
                        dmc.TabsPanel(virt_panel, value="virtualization"),
                        dmc.TabsPanel(backup_panel, value="backup"),
                        dmc.TabsPanel(probe_panel, value="probe"),
                    ],
                ),
                dcc.Location(id="hmdl-coverage-url-sync", refresh=False),
            ]
        )
    )
