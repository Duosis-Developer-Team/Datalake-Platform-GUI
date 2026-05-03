"""Integrations overview — health KPIs and connector shortcuts."""

from __future__ import annotations

import os

import dash_mantine_components as dmc
from dash import html
from dash_iconify import DashIconify

from src.services import admin_client as settings_crud
from src.utils.ui_tokens import ON_SURFACE, kpi_card, section_header, settings_page_shell


def _connector_card(
    title: str,
    description: str,
    status: str,
    href: str,
    action: str,
    *,
    border_color: str | None = None,
    icon: str = "solar:link-bold-duotone",
) -> dmc.Paper:
    st = status.lower()
    if st == "connected":
        badge = dmc.Badge("Connected", color="green", variant="light", size="sm")
    elif st == "degraded":
        badge = dmc.Badge("Degraded", color="orange", variant="light", size="sm")
    else:
        badge = dmc.Badge("Disconnected", color="gray", variant="light", size="sm")

    style = {"border": "1px solid rgba(171,173,176,0.2)", "height": "100%"}
    if border_color:
        style["borderTop"] = f"4px solid {border_color}"

    return dmc.Paper(
        p="lg",
        radius="md",
        withBorder=True,
        style=style,
        children=[
            dmc.Group(
                justify="space-between",
                mb="sm",
                children=[
                    dmc.ThemeIcon(DashIconify(icon=icon, width=22), variant="light", color="indigo", radius="md"),
                    badge,
                ],
            ),
            dmc.Text(title, fw=800, size="lg", c=ON_SURFACE),
            dmc.Text(description, size="sm", c="dimmed", mb="md"),
            dmc.Anchor(
                dmc.Button(action, variant="light", color="indigo", size="xs", radius="md"),
                href=href,
                underline=False,
            ),
        ],
    )


def build_layout(search: str | None = None) -> html.Div:
    ldap_cfgs = settings_crud.list_ldap_configs()
    ldap_active = any(bool(c.get("is_active")) for c in ldap_cfgs) if ldap_cfgs else False
    ldap_status = "connected" if ldap_active else "disconnected"

    aura_url = (os.environ.get("AURANOTIFY_BASE_URL") or "").strip()
    aura_key = (os.environ.get("AURANOTIFY_API_KEY") or os.environ.get("ANOTIFY_API_KEY") or "").strip()
    if aura_url and aura_key:
        aura_status = "connected"
    elif aura_url or aura_key:
        aura_status = "degraded"
    else:
        aura_status = "disconnected"

    crm_status = "connected"

    connected = sum([crm_status == "connected", ldap_status == "connected", aura_status == "connected"])
    degraded = (1 if aura_status == "degraded" else 0)
    disconnected = 3 - connected - degraded

    kpis = dmc.SimpleGrid(
        cols=3,
        spacing="md",
        children=[
            kpi_card("Connected", connected, icon="solar:check-circle-bold-duotone", color="green"),
            kpi_card("Needs attention", degraded, icon="solar:danger-triangle-bold-duotone", color="orange"),
            kpi_card("Not configured", disconnected, icon="solar:close-circle-bold-duotone", color="gray"),
        ],
    )

    grid = dmc.SimpleGrid(
        cols={"base": 1, "sm": 2, "lg": 3},
        spacing="lg",
        children=[
            _connector_card(
                "CRM Dynamics 365",
                "Mappings, aliases, thresholds and manual catalog pricing (WebUI App DB).",
                "connected",
                "/settings/integrations/crm",
                "Open",
                border_color="#552cf8",
                icon="solar:case-round-bold-duotone",
            ),
            _connector_card(
                "LDAP Directory",
                "Centralized authentication and group → role mapping.",
                ldap_status,
                "/settings/integrations/ldap",
                "Configure",
                border_color="#552cf8" if ldap_active else None,
                icon="solar:key-minimalistic-bold-duotone",
            ),
            _connector_card(
                "AuraNotify",
                "SLA / downtime and customer availability APIs.",
                aura_status,
                "/settings/integrations/auranotify",
                "Open",
                border_color="#552cf8" if aura_status == "connected" else None,
                icon="solar:graph-new-up-bold-duotone",
            ),
        ],
    )

    logs = settings_crud.list_audit_log(8)
    rows = []
    for x in logs:
        rows.append(
            html.Tr(
                style={"borderBottom": "1px solid #eef1f4"},
                children=[
                    html.Td(str(x.get("created_at", ""))[:19], style={"fontSize": "12px"}),
                    html.Td(str(x.get("username") or "")),
                    html.Td(str(x.get("action", ""))[:40]),
                    html.Td(str(x.get("detail") or "")[:80], style={"fontSize": "12px", "color": "#6c757d"}),
                ],
            )
        )

    activity = dmc.Paper(
        p=0,
        radius="md",
        withBorder=True,
        children=[
            html.Div(
                style={"padding": "16px 20px", "borderBottom": "1px solid #eef1f4"},
                children=dmc.Text("Recent administrative activity", fw=700, c=ON_SURFACE),
            ),
            html.Div(
                style={"overflowX": "auto"},
                children=[
                    html.Table(
                        [
                            html.Tr(
                                [
                                    html.Th("Time", style=_th()),
                                    html.Th("User", style=_th()),
                                    html.Th("Action", style=_th()),
                                    html.Th("Detail", style=_th()),
                                ]
                            ),
                            *rows,
                        ],
                        style={"width": "100%", "fontSize": "13px"},
                    )
                ],
            ),
        ],
    )

    return html.Div(
        settings_page_shell(
            [
                section_header(
                    "Integrations",
                    "Connect CRM mappings, identity sources and external SLA services.",
                    icon="solar:link-round-angle-bold-duotone",
                ),
                kpis,
                dmc.Space(h="lg"),
                grid,
                dmc.Space(h="lg"),
                activity,
            ]
        )
    )


def _th():
    return {"textAlign": "left", "padding": "8px 12px", "fontSize": "11px", "textTransform": "uppercase", "color": "#6c757d"}
