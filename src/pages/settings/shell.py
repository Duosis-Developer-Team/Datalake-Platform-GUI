"""Administration area: IAM / Integrations navigation and permission-aware layout."""

from __future__ import annotations

from collections.abc import Callable

import dash_mantine_components as dmc
from dash import html
from dash_iconify import DashIconify

from src.components.access_denied import build_access_denied
from src.pages.settings import dashboard as dashboard_page
from src.pages.settings.admin_routes import ADMIN_PREFIX, to_administration_path
from src.pages.settings.iam import audit as audit_page
from src.pages.settings.iam import auth_settings as auth_settings_page
from src.pages.settings.iam import permissions as permissions_page
from src.pages.settings.iam import roles as roles_page
from src.pages.settings.iam import teams as teams_page
from src.pages.settings.iam import users as users_page
from src.pages.settings.integrations import auranotify as auranotify_page
from src.pages.settings.integrations import ldap as ldap_page
from src.pages.settings.integrations import overview as integrations_overview_page
from src.pages.settings.integrations import crm_overview as crm_overview_page
from src.pages.settings.integrations import crm_aliases as crm_aliases_page
from src.pages.settings.integrations import crm_internal_aliases as crm_internal_aliases_page
from src.pages.settings.integrations import crm_thresholds as crm_thresholds_page
from src.pages.settings.integrations import crm_price_overrides as crm_price_overrides_page
from src.pages.settings.integrations import crm_calc_config as crm_calc_config_page
from src.pages.settings.integrations import crm_panels as crm_panels_page
from src.pages.settings.integrations import crm_infra_sources as crm_infra_sources_page
from src.pages.settings.integrations import crm_resource_ratios as crm_resource_ratios_page
from src.pages.settings.integrations import crm_unit_conversions as crm_unit_conversions_page
from src.pages.settings.integrations import crm_backup as crm_backup_page
from src.pages.settings.integrations import netbox_visualization as netbox_visualization_page
from src.pages.settings.integrations import hmdl_overview as hmdl_overview_page
from src.pages.settings.integrations import hmdl_sync_health as hmdl_sync_health_page
from src.pages.settings.integrations import hmdl_coverage as hmdl_coverage_page
from src.pages.settings.integrations import chatbot_logs as chatbot_logs_page
from src.pages.settings import crm_service_mapping as crm_service_mapping_page
from src.pages.settings.platform import versions as platform_versions_page

_A = ADMIN_PREFIX

# (href, label, permission code)
IAM_TABS: list[tuple[str, str, str]] = [
    (f"{_A}/iam/users", "Users", "page:settings_users"),
    (f"{_A}/iam/teams", "Teams", "page:settings_teams"),
    (f"{_A}/iam/roles", "Roles", "page:settings_roles"),
    (f"{_A}/iam/permissions", "Permissions", "page:settings_permissions"),
    (f"{_A}/iam/auth", "Auth", "page:settings_auth"),
    (f"{_A}/iam/audit", "Audit Log", "page:settings_audit"),
]

INT_TABS: list[tuple[str, str, str]] = [
    (f"{_A}/integrations", "Overview", "page:settings_integrations"),
    (f"{_A}/integrations/hmdl", "HMDL", "page:settings_hmdl_overview"),
    (f"{_A}/integrations/crm", "CRM Dynamics 365", "page:settings_crm_overview"),
    (f"{_A}/integrations/netbox/visualization", "NetBox / Loki", "page:settings_netbox_visualization"),
    (f"{_A}/integrations/ldap", "LDAP", "page:settings_ldap"),
    (f"{_A}/integrations/auranotify", "AuraNotify", "page:settings_auranotify"),
    (f"{_A}/integrations/chatbot/logs", "AI Assistant", "page:settings_chatbot_logs"),
]

PLATFORM_TABS: list[tuple[str, str, str]] = [
    (f"{_A}/platform/versions", "Versions", "page:settings_platform_versions"),
]

HMDL_TABS: list[tuple[str, str, str]] = [
    (f"{_A}/integrations/hmdl", "Overview", "page:settings_hmdl_overview"),
    (f"{_A}/integrations/hmdl/sync-health", "Datalake Sync Health", "page:settings_hmdl_sync_health"),
    (f"{_A}/integrations/hmdl/coverage", "Datalake Coverage", "page:settings_hmdl_coverage"),
]

CRM_INT_TABS: list[tuple[str, str, str]] = [
    (f"{_A}/integrations/crm", "Overview", "page:settings_crm_overview"),
    (f"{_A}/integrations/crm/service-mapping", "Service mapping", "page:settings_service_mapping"),
    (f"{_A}/integrations/crm/panels", "Panels", "page:settings_crm_panels"),
    (f"{_A}/integrations/crm/infra-sources", "Infra sources", "page:settings_crm_infra_sources"),
    (f"{_A}/integrations/crm/resource-ratios", "Resource ratios", "page:settings_crm_resource_ratios"),
    (f"{_A}/integrations/crm/unit-conversions", "Unit conversions", "page:settings_crm_unit_conversions"),
    (f"{_A}/integrations/crm/aliases", "Customer aliases", "page:settings_crm_aliases"),
    (f"{_A}/integrations/crm/internal-aliases", "Internal aliases", "page:settings_crm_internal_aliases"),
    (f"{_A}/integrations/crm/thresholds", "Thresholds", "page:settings_crm_thresholds"),
    (f"{_A}/integrations/crm/price-overrides", "Price overrides", "page:settings_crm_price_overrides"),
    (f"{_A}/integrations/crm/calc-config", "Calc variables", "page:settings_crm_calc_config"),
    (f"{_A}/integrations/crm/backup", "Backup", "page:settings_crm_backup"),
]

LEGACY_REDIRECTS: dict[str, str] = {
    f"{_A}/users": f"{_A}/iam/users",
    f"{_A}/roles": f"{_A}/iam/roles",
    f"{_A}/permissions": f"{_A}/iam/permissions",
    f"{_A}/teams": f"{_A}/iam/teams",
    f"{_A}/auth": f"{_A}/iam/auth",
    f"{_A}/audit": f"{_A}/iam/audit",
    f"{_A}/ldap": f"{_A}/integrations/ldap",
    f"{_A}/crm": f"{_A}/integrations/crm",
    f"{_A}/crm/service-mapping": f"{_A}/integrations/crm/service-mapping",
    f"{_A}/customer-alias": f"{_A}/integrations/crm/aliases",
    f"{_A}/crm/product-categories": f"{_A}/integrations/crm/service-mapping",
}

LEGACY_PREFIX_REDIRECTS: list[tuple[str, str]] = [
    (f"{_A}/crm/service-mapping", f"{_A}/integrations/crm/service-mapping"),
    (f"{_A}/crm", f"{_A}/integrations/crm"),
]


def _call_page_builder(builder: Callable[..., html.Div], search: str | None) -> html.Div:
    return builder(search=search)


_PAGE_BUILDERS: dict[str, tuple[str, Callable[..., html.Div]]] = {
    _A: ("grp:settings", dashboard_page.build_layout),
    f"{_A}/iam/users": ("page:settings_users", users_page.build_layout),
    f"{_A}/iam/teams": ("page:settings_teams", teams_page.build_layout),
    f"{_A}/iam/roles": ("page:settings_roles", roles_page.build_layout),
    f"{_A}/iam/permissions": ("page:settings_permissions", permissions_page.build_layout),
    f"{_A}/iam/auth": ("page:settings_auth", auth_settings_page.build_layout),
    f"{_A}/iam/audit": ("page:settings_audit", audit_page.build_layout),
    f"{_A}/integrations": ("page:settings_integrations", integrations_overview_page.build_layout),
    f"{_A}/integrations/hmdl": ("page:settings_hmdl_overview", hmdl_overview_page.build_layout),
    f"{_A}/integrations/hmdl/sync-health": ("page:settings_hmdl_sync_health", hmdl_sync_health_page.build_layout),
    f"{_A}/integrations/hmdl/coverage": ("page:settings_hmdl_coverage", hmdl_coverage_page.build_layout),
    f"{_A}/integrations/crm": ("page:settings_crm_overview", crm_overview_page.build_layout),
    f"{_A}/integrations/crm/service-mapping": ("page:settings_service_mapping", crm_service_mapping_page.build_layout),
    f"{_A}/integrations/crm/aliases": ("page:settings_crm_aliases", crm_aliases_page.build_layout),
    f"{_A}/integrations/crm/internal-aliases": (
        "page:settings_crm_internal_aliases",
        crm_internal_aliases_page.build_layout,
    ),
    f"{_A}/integrations/crm/thresholds": ("page:settings_crm_thresholds", crm_thresholds_page.build_layout),
    f"{_A}/integrations/crm/price-overrides": ("page:settings_crm_price_overrides", crm_price_overrides_page.build_layout),
    f"{_A}/integrations/crm/calc-config": ("page:settings_crm_calc_config", crm_calc_config_page.build_layout),
    f"{_A}/integrations/crm/panels": ("page:settings_crm_panels", crm_panels_page.build_layout),
    f"{_A}/integrations/crm/infra-sources": ("page:settings_crm_infra_sources", crm_infra_sources_page.build_layout),
    f"{_A}/integrations/crm/resource-ratios": ("page:settings_crm_resource_ratios", crm_resource_ratios_page.build_layout),
    f"{_A}/integrations/crm/unit-conversions": ("page:settings_crm_unit_conversions", crm_unit_conversions_page.build_layout),
    f"{_A}/integrations/crm/backup": ("page:settings_crm_backup", crm_backup_page.build_layout),
    f"{_A}/integrations/ldap": ("page:settings_ldap", ldap_page.build_layout),
    f"{_A}/integrations/auranotify": ("page:settings_auranotify", auranotify_page.build_layout),
    f"{_A}/integrations/netbox/visualization": (
        "page:settings_netbox_visualization",
        netbox_visualization_page.build_layout,
    ),
    f"{_A}/integrations/chatbot/logs": ("page:settings_chatbot_logs", chatbot_logs_page.build_layout),
    f"{_A}/platform/versions": ("page:settings_platform_versions", platform_versions_page.build_layout),
}


def _normalize_path(pathname: str) -> str:
    p = to_administration_path(pathname or _A)
    p = p.rstrip("/") or _A
    p = LEGACY_REDIRECTS.get(p, p)
    for old_prefix, new_prefix in LEGACY_PREFIX_REDIRECTS:
        if p == old_prefix or p.startswith(old_prefix + "/"):
            rest = p[len(old_prefix) :].lstrip("/")
            return new_prefix if not rest else f"{new_prefix}/{rest}"
    return p


def has_any_settings_access(user_id: int) -> bool:
    from src.auth.permission_service import can_view

    codes = (
        [c for _, _, c in IAM_TABS]
        + [c for _, _, c in INT_TABS]
        + [c for _, _, c in CRM_INT_TABS]
        + [c for _, _, c in HMDL_TABS]
        + [c for _, _, c in PLATFORM_TABS]
    )
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


def first_allowed_platform_path(user_id: int) -> str | None:
    from src.auth.permission_service import can_view

    for href, _label, code in PLATFORM_TABS:
        if can_view(user_id, code):
            return href
    return None


def first_allowed_settings_path(user_id: int) -> str | None:
    from src.auth.permission_service import can_view

    if can_view(user_id, "grp:settings") or has_any_settings_access(user_id):
        return _A
    return None


def _section_for_path(p: str) -> str:
    if p == _A or p == f"{_A}/":
        return "overview"
    if p.startswith(f"{_A}/iam"):
        return "iam"
    if p.startswith(f"{_A}/integrations"):
        return "integrations"
    if p.startswith(f"{_A}/platform"):
        return "platform"
    return "overview"


def _nav_btn_props(*, active: bool) -> dict:
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
    active_o = current_path.rstrip("/") in (_A, "")
    if can_view(user_id, "grp:settings") or has_any_settings_access(user_id):
        items.append(
            dmc.Anchor(
                dmc.Button(
                    "Overview",
                    leftSection=DashIconify(icon="solar:widget-2-bold-duotone", width=16),
                    radius="md",
                    **_nav_btn_props(active=active_o),
                ),
                href=_A,
                underline=False,
            )
        )
    iam_href = first_allowed_iam_path(user_id)
    if iam_href:
        active_i = _section_for_path(current_path) == "iam"
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
    int_href = first_allowed_integrations_path(user_id)
    if int_href:
        active_g = current_path.startswith(f"{_A}/integrations")
        items.append(
            dmc.Anchor(
                dmc.Button(
                    "Integration and Configuration",
                    leftSection=DashIconify(icon="solar:link-round-angle-bold-duotone", width=16),
                    radius="md",
                    **_nav_btn_props(active=active_g),
                ),
                href=int_href,
                underline=False,
            )
        )
    plat_href = first_allowed_platform_path(user_id)
    if plat_href:
        active_p = _section_for_path(current_path) == "platform"
        items.append(
            dmc.Anchor(
                dmc.Button(
                    "Platform",
                    leftSection=DashIconify(icon="solar:box-bold-duotone", width=16),
                    radius="md",
                    **_nav_btn_props(active=active_p),
                ),
                href=plat_href,
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
    if sec == "platform":
        links = []
        for href, label, code in PLATFORM_TABS:
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
        blocks = [
            html.Div(
                style={"borderBottom": "1px solid #eef1f4", "paddingBottom": "8px", "marginBottom": "12px"},
                children=[dmc.Group(gap="xs", children=links)],
            )
        ]

        if current_path.startswith(f"{_A}/integrations/crm"):
            crm_links = []
            for href, label, code in CRM_INT_TABS:
                if not can_view(user_id, code):
                    continue
                active = current_path.rstrip("/") == href.rstrip("/")
                crm_links.append(
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
            if crm_links:
                blocks.append(
                    html.Div(
                        style={"borderBottom": "1px solid #eef1f4", "paddingBottom": "8px", "marginBottom": "12px"},
                        children=[dmc.Group(gap="xs", children=crm_links)],
                    )
                )

        if current_path.startswith(f"{_A}/integrations/hmdl"):
            hmdl_links = []
            for href, label, code in HMDL_TABS:
                if not can_view(user_id, code):
                    continue
                active = current_path.rstrip("/") == href.rstrip("/")
                hmdl_links.append(
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
            if hmdl_links:
                blocks.append(
                    html.Div(
                        style={"borderBottom": "1px solid #eef1f4", "paddingBottom": "8px", "marginBottom": "16px"},
                        children=[dmc.Group(gap="xs", children=hmdl_links)],
                    )
                )

        return html.Div(children=blocks)
    return None


def _breadcrumb(current_path: str) -> str:
    sec = _section_for_path(current_path)
    if sec == "overview":
        return "Administration › Overview"
    if sec == "iam":
        return "Administration › Identity & Access Management"
    if sec == "integrations":
        if current_path.startswith(f"{_A}/integrations/crm"):
            return "Administration › Integrations › CRM Dynamics 365"
        if current_path.startswith(f"{_A}/integrations/hmdl"):
            return "Administration › Integrations › HMDL"
        return "Administration › Integrations"
    if sec == "platform":
        return "Administration › Platform › Versions"
    return "Administration"


def build_settings_page(pathname: str, user_id: int, search: str | None = None) -> html.Div:
    from src.auth.permission_service import can_view

    p = _normalize_path(pathname or _A)
    if p == f"{_A}/iam":
        p = first_allowed_iam_path(user_id) or _A

    if not has_any_settings_access(user_id):
        return build_access_denied("You have no access to Administration.")

    if p not in _PAGE_BUILDERS:
        p = _A

    code, builder = _PAGE_BUILDERS[p]

    if p == _A:
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
                            dmc.Title("Administration", order=3, c="#2B3674"),
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
