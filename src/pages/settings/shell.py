"""Settings area: tab navigation and permission-aware layout."""

from __future__ import annotations

from collections.abc import Callable

import dash_mantine_components as dmc
from dash import html
from dash_iconify import DashIconify

from src.components.access_denied import build_access_denied
from src.pages.settings import (
    audit as audit_page,
    auth_settings as auth_settings_page,
    ldap as ldap_page,
    permissions as permissions_page,
    roles as roles_page,
    teams as teams_page,
    users as users_page,
)

# (href, label, permission code)
SETTINGS_TABS: list[tuple[str, str, str]] = [
    ("/settings/users", "Users", "page:settings_users"),
    ("/settings/roles", "Roles", "page:settings_roles"),
    ("/settings/permissions", "Permissions", "page:settings_permissions"),
    ("/settings/ldap", "LDAP", "page:settings_ldap"),
    ("/settings/teams", "Teams", "page:settings_teams"),
    ("/settings/auth", "Auth", "page:settings_auth"),
    ("/settings/audit", "Audit Log", "page:settings_audit"),
]

_PAGE_BUILDERS: dict[str, tuple[str, Callable[[], html.Div]]] = {
    "/settings/users": ("page:settings_users", users_page.build_layout),
    "/settings/roles": ("page:settings_roles", roles_page.build_layout),
    "/settings/permissions": ("page:settings_permissions", permissions_page.build_layout),
    "/settings/ldap": ("page:settings_ldap", ldap_page.build_layout),
    "/settings/teams": ("page:settings_teams", teams_page.build_layout),
    "/settings/auth": ("page:settings_auth", auth_settings_page.build_layout),
    "/settings/audit": ("page:settings_audit", audit_page.build_layout),
}


def first_allowed_settings_path(user_id: int) -> str | None:
    from src.auth.permission_service import can_view

    for href, _label, code in SETTINGS_TABS:
        if can_view(user_id, code):
            return href
    return None


def build_settings_page(pathname: str, user_id: int) -> html.Div:
    from src.auth.permission_service import can_view

    p = (pathname or "/settings").rstrip("/") or "/settings"
    if p == "/settings":
        first = first_allowed_settings_path(user_id)
        if not first:
            return build_access_denied("You have no access to Settings.")
        p = first

    if p not in _PAGE_BUILDERS:
        return build_access_denied()

    code, builder = _PAGE_BUILDERS[p]
    if not can_view(user_id, code):
        return build_access_denied()

    visible = [(h, lab, c) for h, lab, c in SETTINGS_TABS if can_view(user_id, c)]
    tab_links = []
    for href, label, _c in visible:
        active = p == href
        tab_links.append(
            dmc.Anchor(
                dmc.Button(
                    label,
                    variant="filled" if active else "light",
                    color="indigo",
                    size="sm",
                    radius="md",
                ),
                href=href,
                underline=False,
            )
        )

    return html.Div(
        style={"maxWidth": "1200px"},
        children=[
            dmc.Group(
                gap="sm",
                mb="md",
                children=[
                    DashIconify(icon="solar:settings-bold-duotone", width=32, color="#4318FF"),
                    dmc.Stack(
                        gap=2,
                        children=[
                            dmc.Title("Settings", order=2, c="#2B3674"),
                            dmc.Text("User, role, and integration management.", size="sm", c="dimmed"),
                        ],
                    ),
                ],
            ),
            dmc.Group(gap="xs", mb="lg", wrap="wrap", children=tab_links),
            html.Div(children=builder()),
        ],
    )
