"""Settings area: IAM / Integrations navigation and permission-aware layout."""

from __future__ import annotations

from collections.abc import Callable

import dash_mantine_components as dmc
from dash import html
from dash_iconify import DashIconify

from src.components.access_denied import build_access_denied
from src.pages.settings import dashboard as dashboard_page
from src.pages.settings.iam import audit as audit_page
from src.pages.settings.iam import auth_settings as auth_settings_page
from src.pages.settings.iam import permissions as permissions_page
from src.pages.settings.iam import roles as roles_page
from src.pages.settings.iam import teams as teams_page
from src.pages.settings.iam import users as users_page
from src.pages.settings.integrations import auranotify as auranotify_page
from src.pages.settings.integrations import ldap as ldap_page
from src.pages.settings.integrations import overview as integrations_overview_page

# (href, label, permission code)
IAM_TABS: list[tuple[str, str, str]] = [
    ("/settings/iam/users", "Users", "page:settings_users"),
    ("/settings/iam/teams", "Teams", "page:settings_teams"),
    ("/settings/iam/roles", "Roles", "page:settings_roles"),
    ("/settings/iam/permissions", "Permissions", "page:settings_permissions"),
    ("/settings/iam/auth", "Auth", "page:settings_auth"),
    ("/settings/iam/audit", "Audit Log", "page:settings_audit"),
]

INT_TABS: list[tuple[str, str, str]] = [
    ("/settings/integrations", "Overview", "page:settings_integrations"),
    ("/settings/integrations/ldap", "LDAP", "page:settings_ldap"),
    ("/settings/integrations/auranotify", "AuraNotify", "page:settings_auranotify"),
]

LEGACY_REDIRECTS: dict[str, str] = {
    "/settings/users": "/settings/iam/users",
    "/settings/roles": "/settings/iam/roles",
    "/settings/permissions": "/settings/iam/permissions",
    "/settings/teams": "/settings/iam/teams",
    "/settings/auth": "/settings/iam/auth",
    "/settings/audit": "/settings/iam/audit",
    "/settings/ldap": "/settings/integrations/ldap",
}

def _call_page_builder(builder: Callable[..., html.Div], search: str | None) -> html.Div:
    return builder(search=search)


_PAGE_BUILDERS: dict[str, tuple[str, Callable[..., html.Div]]] = {
    "/settings": ("grp:settings", dashboard_page.build_layout),
    "/settings/iam/users": ("page:settings_users", users_page.build_layout),
    "/settings/iam/teams": ("page:settings_teams", teams_page.build_layout),
    "/settings/iam/roles": ("page:settings_roles", roles_page.build_layout),
    "/settings/iam/permissions": ("page:settings_permissions", permissions_page.build_layout),
    "/settings/iam/auth": ("page:settings_auth", auth_settings_page.build_layout),
    "/settings/iam/audit": ("page:settings_audit", audit_page.build_layout),
    "/settings/integrations": ("page:settings_integrations", integrations_overview_page.build_layout),
    "/settings/integrations/ldap": ("page:settings_ldap", ldap_page.build_layout),
    "/settings/integrations/auranotify": ("page:settings_auranotify", auranotify_page.build_layout),
}


def _normalize_path(pathname: str) -> str:
    p = (pathname or "/settings").rstrip("/") or "/settings"
    return LEGACY_REDIRECTS.get(p, p)


def has_any_settings_access(user_id: int) -> bool:
    from src.auth.permission_service import can_view

    codes = [c for _, _, c in IAM_TABS] + [c for _, _, c in INT_TABS]
    if any(can_view(user_id, c) for c in codes):
        return True
    return can_view(user_id, "grp:settings")


def first_allowed_iam_path(user_id: int) -> str | None:
    from src.auth.permission_service import can_view

    for href, _label, code in IAM_TABS:
        if can_view(user_id, code):
            return href
    return None


def first_allowed_integrations_path(user_id: int) -> str | None:
    from src.auth.permission_service import can_view

    for href, _label, code in INT_TABS:
        if can_view(user_id, code):
            return href
    return None


def first_allowed_settings_path(user_id: int) -> str | None:
    """First page user may open (prefers overview dashboard)."""
    from src.auth.permission_service import can_view

    if can_view(user_id, "grp:settings") or has_any_settings_access(user_id):
        return "/settings"
    return None


def _section_for_path(p: str) -> str:
    if p == "/settings" or p == "/settings/":
        return "overview"
    if p.startswith("/settings/iam"):
        return "iam"
    if p.startswith("/settings/integrations"):
        return "integrations"
    return "overview"


def _nav_btn_props(*, active: bool) -> dict:
    """Primary nav: gradient fill when active (brand), light when inactive."""
    if active:
        return {
            "variant": "filled",
            "color": "indigo",
            "styles": {
                "root": {
                    "background": "linear-gradient(135deg, #552cf8 0%, #a092ff 100%)",
                    "border": "none",
                    "color": "#ffffff",
                }
            },
        }
    return {"variant": "light", "color": "indigo"}


def _top_nav(user_id: int, current_path: str) -> dmc.Group:
    from src.auth.permission_service import can_view

    items = []
    # Overview
    active_o = current_path.rstrip("/") in ("/settings", "")
    if can_view(user_id, "grp:settings") or has_any_settings_access(user_id):
        items.append(
            dmc.Anchor(
                dmc.Button(
                    "Overview",
                    leftSection=DashIconify(icon="solar:widget-2-bold-duotone", width=16),
                    radius="md",
                    **_nav_btn_props(active=active_o),
                ),
                href="/settings",
                underline=False,
            )
        )
    # IAM
    iam_href = first_allowed_iam_path(user_id)
    if iam_href:
        sec = _section_for_path(current_path)
        active_i = sec == "iam"
        items.append(
            dmc.Anchor(
                dmc.Button(
                    "Identity & Access",
                    leftSection=DashIconify(icon="solar:shield-user-bold-duotone", width=16),
                    radius="md",
                    **_nav_btn_props(active=active_i),
                ),
                href=iam_href,
                underline=False,
            )
        )
    # Integrations
    int_href = first_allowed_integrations_path(user_id)
    if int_href:
        active_g = _section_for_path(current_path) == "integrations"
        items.append(
            dmc.Anchor(
                dmc.Button(
                    "Integrations",
                    leftSection=DashIconify(icon="solar:link-round-angle-bold-duotone", width=16),
                    radius="md",
                    **_nav_btn_props(active=active_g),
                ),
                href=int_href,
                underline=False,
            )
        )

    return dmc.Group(gap="sm", children=items)


def _sub_nav(user_id: int, current_path: str) -> html.Div | None:
    from src.auth.permission_service import can_view

    sec = _section_for_path(current_path)
    if sec == "iam":
        links = []
        for href, label, code in IAM_TABS:
            if not can_view(user_id, code):
                continue
            active = current_path.rstrip("/") == href.rstrip("/")
            links.append(
                dmc.Anchor(
                    dmc.Button(
                        label,
                        variant="subtle" if not active else "light",
                        color="indigo",
                        size="xs",
                        style={
                            "borderBottom": "2px solid #552cf8" if active else "2px solid transparent",
                            "borderRadius": 0,
                        },
                    ),
                    href=href,
                    underline=False,
                )
            )
        if not links:
            return None
        return html.Div(
            style={"borderBottom": "1px solid #eef1f4", "paddingBottom": "8px", "marginBottom": "16px"},
            children=[dmc.Group(gap="xs", children=links)],
        )
    if sec == "integrations":
        links = []
        for href, label, code in INT_TABS:
            if not can_view(user_id, code):
                continue
            active = current_path.rstrip("/") == href.rstrip("/")
            links.append(
                dmc.Anchor(
                    dmc.Button(
                        label,
                        variant="subtle" if not active else "light",
                        color="indigo",
                        size="xs",
                        style={
                            "borderBottom": "2px solid #552cf8" if active else "2px solid transparent",
                            "borderRadius": 0,
                        },
                    ),
                    href=href,
                    underline=False,
                )
            )
        if not links:
            return None
        return html.Div(
            style={"borderBottom": "1px solid #eef1f4", "paddingBottom": "8px", "marginBottom": "16px"},
            children=[dmc.Group(gap="xs", children=links)],
        )
    return None


def _breadcrumb(current_path: str) -> str:
    sec = _section_for_path(current_path)
    if sec == "overview":
        return "Settings › Overview"
    if sec == "iam":
        return "Settings › Identity & Access Management"
    if sec == "integrations":
        return "Settings › Integrations"
    return "Settings"


def build_settings_page(pathname: str, user_id: int, search: str | None = None) -> html.Div:
    from src.auth.permission_service import can_view

    p = _normalize_path(pathname or "/settings")
    if p == "/settings/iam":
        p = first_allowed_iam_path(user_id) or "/settings"

    if not has_any_settings_access(user_id):
        return build_access_denied("You have no access to Settings.")

    if p not in _PAGE_BUILDERS:
        p = "/settings"

    code, builder = _PAGE_BUILDERS[p]

    if p == "/settings":
        if not (can_view(user_id, "grp:settings") or has_any_settings_access(user_id)):
            return build_access_denied()
    elif not can_view(user_id, code):
        return build_access_denied()

    body = _call_page_builder(builder, search)

    sub = _sub_nav(user_id, p)
    header = dmc.Paper(
        p="md",
        radius="md",
        mb="md",
        withBorder=True,
        style={
            "position": "sticky",
            "top": 0,
            "zIndex": 20,
            "background": "rgba(255,255,255,0.92)",
            "backdropFilter": "blur(10px)",
        },
        children=[
            dmc.Group(
                justify="space-between",
                mb="sm",
                children=[
                    dmc.Stack(
                        gap=2,
                        children=[
                            dmc.Text(_breadcrumb(p), size="xs", c="dimmed", fw=600),
                            dmc.Title("Settings", order=3, c="#2B3674"),
                        ],
                    ),
                    _top_nav(user_id, p),
                ],
            ),
            sub if sub else html.Div(),
        ],
    )

    return html.Div(
        style={"maxWidth": "1280px", "margin": "0 auto", "padding": "0 8px 48px"},
        children=[header, body],
    )
