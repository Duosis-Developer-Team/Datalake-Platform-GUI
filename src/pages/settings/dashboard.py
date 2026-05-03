"""Settings home — KPIs, section cards, recent audit, app status."""

from __future__ import annotations

import os

import dash_mantine_components as dmc
from dash import html
from dash_iconify import DashIconify

from src.services import admin_client as settings_crud
from src.utils.ui_tokens import (
    ON_DIM,
    ON_SURFACE,
    PRIMARY,
    kpi_card,
    section_header,
    section_nav_card,
    settings_page_shell,
)


def build_layout(search: str | None = None) -> html.Div:
    users = settings_crud.list_users_with_roles()
    active_u = sum(1 for u in users if u.get("is_active"))
    inactive_u = len(users) - active_u
    teams = settings_crud.list_teams()
    roles = settings_crud.list_roles()
    total_members = sum(int(t.get("member_count") or 0) for t in teams)

    ldap_cfgs = settings_crud.list_ldap_configs()
    ldap_ok = any(bool(c.get("is_active")) for c in ldap_cfgs) if ldap_cfgs else False
    aura_url = (os.environ.get("AURANOTIFY_BASE_URL") or "").strip()
    aura_key = (os.environ.get("AURANOTIFY_API_KEY") or os.environ.get("ANOTIFY_API_KEY") or "").strip()
    aura_ok = bool(aura_url and aura_key)

    audit = settings_crud.list_audit_log(5)
    auth_disabled = os.environ.get("AUTH_DISABLED", "").lower() in ("1", "true", "yes")
    build_id = (os.environ.get("APP_BUILD_ID") or "dev").strip()

    kpi_row = dmc.SimpleGrid(
        cols=4,
        spacing="md",
        children=[
            kpi_card("Active users", active_u, icon="solar:users-group-rounded-bold-duotone", color="green"),
            kpi_card("Inactive users", inactive_u, icon="solar:user-block-bold-duotone", color="gray"),
            kpi_card("Teams", len(teams), icon="solar:users-group-two-rounded-bold-duotone", color="indigo"),
            kpi_card("Roles", len(roles), icon="solar:shield-user-bold-duotone", color="violet"),
        ],
    )

    section_row = dmc.SimpleGrid(
        cols=2,
        spacing="lg",
        children=[
            section_nav_card(
                "Identity & Access Management",
                "Users, teams, roles, permissions, authentication and audit trail.",
                "/settings/iam/users",
                icon="solar:shield-user-bold-duotone",
                badges=[f"{len(users)} users", f"{len(roles)} roles"],
            ),
            section_nav_card(
                "Integrations",
                "LDAP directory and AuraNotify SLA connectivity.",
                "/settings/integrations",
                icon="solar:link-round-angle-bold-duotone",
                badges=[
                    "LDAP ● " + ("connected" if ldap_ok else "offline"),
                    "AuraNotify ● " + ("configured" if aura_ok else "not set"),
                ],
            ),
        ],
    )

    crm_row = dmc.SimpleGrid(
        cols=1,
        spacing="lg",
        children=[
            section_nav_card(
                "CRM Dynamics 365",
                "Operator-managed mappings, aliases, thresholds and pricing knobs (WebUI App DB).",
                "/settings/integrations/crm",
                icon="solar:case-round-bold-duotone",
                badges=["customer-api", "datacenter-api", "bulutwebui"],
            ),
        ],
    )

    audit_rows = []
    for x in audit:
        audit_rows.append(
            html.Tr(
                [
                    html.Td(str(x.get("created_at", ""))[:19], style={"fontSize": "12px"}),
                    html.Td(str(x.get("username") or x.get("user_id") or "")),
                    html.Td(
                        dmc.Badge(
                            str(x.get("action", ""))[:40],
                            size="xs",
                            variant="light",
                            color="indigo",
                        )
                    ),
                    html.Td(str(x.get("detail") or "")[:80], style={"fontSize": "12px", "color": ON_DIM}),
                    html.Td(str(x.get("ip_address") or ""), style={"fontSize": "12px"}),
                ]
            )
        )

    audit_table = dmc.Paper(
        p="md",
        radius="md",
        withBorder=True,
        children=[
            dmc.Group(
                justify="space-between",
                mb="sm",
                children=[
                    section_header(
                        "Recent activity",
                        "Latest audit events (authentication & admin).",
                        icon="solar:history-bold-duotone",
                    ),
                    dmc.Anchor(
                        "View all",
                        href="/settings/iam/audit",
                        size="sm",
                        c="indigo",
                        underline=False,
                    ),
                ],
            ),
            html.Div(
                style={"overflowX": "auto"},
                children=[
                    html.Table(
                        [
                            html.Tr(
                                [
                                    html.Th("Time", style={"textAlign": "left", "padding": "8px", "color": ON_SURFACE}),
                                    html.Th("User", style={"textAlign": "left", "padding": "8px"}),
                                    html.Th("Action", style={"textAlign": "left", "padding": "8px"}),
                                    html.Th("Detail", style={"textAlign": "left", "padding": "8px"}),
                                    html.Th("IP", style={"textAlign": "left", "padding": "8px"}),
                                ]
                            ),
                            *audit_rows,
                        ],
                        style={"width": "100%", "fontSize": "13px", "borderCollapse": "collapse"},
                    )
                ],
            ),
        ],
    )

    status_row = dmc.SimpleGrid(
        cols=2,
        spacing="md",
        children=[
            dmc.Paper(
                p="md",
                radius="md",
                withBorder=True,
                children=[
                    dmc.Text("Authentication mode", fw=700, mb="xs", c=ON_SURFACE),
                    dmc.Alert(
                        "AUTH_DISABLED is ON — RBAC bypassed. Do not use in production."
                        if auth_disabled
                        else "RBAC enforced — session and permissions active.",
                        color="red" if auth_disabled else "green",
                        variant="light",
                    ),
                ],
            ),
            dmc.Paper(
                p="md",
                radius="md",
                withBorder=True,
                children=[
                    dmc.Text("Deployment", fw=700, mb="xs", c=ON_SURFACE),
                    dmc.Text(f"APP_BUILD_ID: {build_id}", size="sm", c=ON_DIM),
                    dmc.Text(f"Total members across teams: {total_members}", size="sm", c=ON_DIM, mt="xs"),
                ],
            ),
        ],
    )

    hero = dmc.Paper(
        p="xl",
        radius="md",
        mb="lg",
        style={
            "background": "linear-gradient(135deg, #f6f2ff 0%, #ede8ff 55%, #ffffff 100%)",
            "border": "1px solid rgba(85, 44, 248, 0.12)",
        },
        children=[
            dmc.Group(
                align="flex-start",
                children=[
                    dmc.ThemeIcon(
                        DashIconify(icon="solar:settings-bold-duotone", width=28, color="#fff"),
                        size="xl",
                        radius="md",
                        variant="filled",
                        color="indigo",
                        style={"background": f"linear-gradient(135deg, {PRIMARY} 0%, #a092ff 100%)"},
                    ),
                    dmc.Stack(
                        gap=6,
                        children=[
                            dmc.Title("Settings overview", order=2, c=ON_SURFACE),
                            dmc.Text(
                                "Monitor identity health, integrations, and recent administrative activity.",
                                size="sm",
                                c=ON_DIM,
                            ),
                        ],
                    ),
                ],
            )
        ],
    )

    return html.Div(
        settings_page_shell(
            [
                hero,
                kpi_row,
                dmc.Space(h="lg"),
                section_row,
                dmc.Space(h="lg"),
                crm_row,
                dmc.Space(h="lg"),
                audit_table,
                dmc.Space(h="lg"),
                status_row,
            ]
        )
    )
