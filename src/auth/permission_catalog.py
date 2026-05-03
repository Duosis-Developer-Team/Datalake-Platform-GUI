"""
Default hierarchical permission tree (code registry).
Synced to DB on startup; admins may add dynamic nodes (is_dynamic=True) via UI.
"""

from __future__ import annotations

from src.auth.models import PermissionNode


def _n(
    code: str,
    name: str,
    resource_type: str,
    *,
    route_pattern: str | None = None,
    component_id: str | None = None,
    icon: str | None = None,
    sort_order: int = 0,
    children: list[PermissionNode] | None = None,
) -> PermissionNode:
    return PermissionNode(
        code=code,
        name=name,
        resource_type=resource_type,
        route_pattern=route_pattern,
        component_id=component_id,
        icon=icon,
        sort_order=sort_order,
        children=children or [],
    )


def build_default_permission_roots() -> list[PermissionNode]:
    """Return top-level page_group nodes with full nested tree."""
    dashboard = _n(
        "grp:dashboard",
        "Dashboard",
        "page_group",
        icon="solar:home-smile-bold-duotone",
        sort_order=10,
        children=[
            _n(
                "page:overview",
                "Overview",
                "page",
                route_pattern="/",
                icon="solar:home-smile-bold-duotone",
                sort_order=10,
                children=[
                    _n("sec:overview:kpi", "KPI Strip", "section", sort_order=10),
                    _n("sec:overview:phys_inv", "Physical Inventory", "section", sort_order=20),
                    _n(
                        "sec:overview:resource_usage",
                        "Resource Usage",
                        "section",
                        sort_order=30,
                        children=[
                            _n("sub:overview:res:classic", "Classic Architecture", "sub_section", sort_order=10),
                            _n("sub:overview:res:hyperconv", "Hyperconverged Architecture", "sub_section", sort_order=20),
                            _n("sub:overview:res:ibm", "IBM Power", "sub_section", sort_order=30),
                        ],
                    ),
                    _n("sec:overview:energy", "Energy by Source", "section", sort_order=40),
                    _n("sec:overview:dc_landscape", "DC Landscape", "section", sort_order=50),
                    _n("sec:overview:dc_summary", "DC Summary Table", "section", sort_order=60),
                    _n("action:overview:export", "Export (PDF/CSV/Excel)", "action", sort_order=100),
                ],
            ),
            _n(
                "page:datacenters",
                "Data Centers",
                "page",
                route_pattern="/datacenters",
                icon="solar:server-square-bold-duotone",
                sort_order=20,
                children=[
                    _n("sec:datacenters:grid", "DC Vault Grid", "section", sort_order=10),
                    _n("action:datacenters:export", "Export", "action", sort_order=100),
                ],
            ),
            _n(
                "page:dc_view",
                "DC View",
                "page",
                route_pattern="/datacenter/{id}",
                icon="solar:server-square-bold-duotone",
                sort_order=30,
                children=[
                    _n(
                        "sec:dc_view:summary",
                        "Summary",
                        "section",
                        sort_order=10,
                        children=[
                            _n("sub:dc_view:summary:infra", "Combined Infrastructure", "sub_section"),
                            _n("sub:dc_view:summary:util", "Resource Utilization", "sub_section"),
                            _n("sub:dc_view:summary:cap", "Capacity Detail", "sub_section"),
                            _n("sub:dc_view:summary:power", "Power Compute IBM", "sub_section"),
                            _n("sub:dc_view:summary:energy", "Energy Breakdown", "sub_section"),
                        ],
                    ),
                    _n(
                        "sec:dc_view:virtualization",
                        "Virtualization",
                        "section",
                        component_id="dc-virt-tabs",
                        sort_order=20,
                        children=[
                            _n("sub:dc_view:virt:classic", "Classic Architecture", "sub_section", component_id="classic-virt-panel"),
                            _n("sub:dc_view:virt:hyperconv", "Hyperconverged Architecture", "sub_section", component_id="hyperconv-virt-panel"),
                            _n("sub:dc_view:virt:power", "Power Architecture", "sub_section"),
                        ],
                    ),
                    _n(
                        "sec:dc_view:storage",
                        "Storage",
                        "section",
                        sort_order=30,
                        children=[
                            _n("sub:dc_view:storage:intel", "Intel Storage", "sub_section"),
                            _n("sub:dc_view:storage:ibm", "IBM Storage", "sub_section"),
                            _n("sub:dc_view:storage:s3", "Object Storage S3", "sub_section"),
                        ],
                    ),
                    _n(
                        "sec:dc_view:backup",
                        "Backup and Replication",
                        "section",
                        sort_order=40,
                        children=[
                            _n("sub:dc_view:backup:zerto", "Zerto", "sub_section"),
                            _n("sub:dc_view:backup:veeam", "Veeam", "sub_section"),
                            _n("sub:dc_view:backup:netbackup", "NetBackup", "sub_section"),
                            _n("sub:dc_view:backup:nutanix", "Nutanix", "sub_section"),
                        ],
                    ),
                    _n("sec:dc_view:phys_inv", "Physical Inventory", "section", sort_order=50),
                    _n(
                        "sec:dc_view:network",
                        "Network",
                        "section",
                        sort_order=60,
                        children=[
                            _n("sub:dc_view:net:dashboard", "Network Dashboard", "sub_section"),
                            _n("sub:dc_view:net:san", "SAN", "sub_section"),
                        ],
                    ),
                    _n("sec:dc_view:availability", "Availability", "section", sort_order=70),
                    _n("action:dc_view:export", "Export", "action", sort_order=100),
                ],
            ),
            _n(
                "page:dc_detail",
                "DC Detail (Racks)",
                "page",
                route_pattern="/dc-detail/{id}",
                sort_order=40,
                children=[
                    _n("sec:dc_detail:racks", "Rack Grid", "section"),
                    _n("sec:dc_detail:rack_detail", "Rack Detail Panel", "section"),
                ],
            ),
        ],
    )

    global_grp = _n(
        "grp:global",
        "Global",
        "page_group",
        icon="solar:global-bold-duotone",
        sort_order=20,
        children=[
            _n(
                "page:global_view",
                "Global View",
                "page",
                route_pattern="/global-view",
                sort_order=10,
                children=[
                    _n("sec:global:globe", "Globe Map", "section"),
                    _n("sec:global:regions", "Region Navigation", "section"),
                    _n("sec:global:detail", "DC Info / Detail Panel", "section"),
                    _n("sec:global:floor", "Floor Map", "section"),
                    _n("sec:global:3d", "3D Rack Overlay", "section"),
                    _n("action:global:export", "Export", "action"),
                ],
            ),
            _n(
                "page:region_drilldown",
                "Region Drilldown",
                "page",
                route_pattern="/region-drilldown",
                sort_order=20,
            ),
        ],
    )

    customer_grp = _n(
        "grp:customer",
        "Customer",
        "page_group",
        icon="solar:users-group-rounded-bold-duotone",
        sort_order=30,
        children=[
            _n(
                "page:customer_view",
                "Customer View",
                "page",
                route_pattern="/customer-view",
                sort_order=10,
                children=[
                    _n(
                        "sec:customer:summary",
                        "Summary",
                        "section",
                        children=[
                            _n("sub:customer:sum:compute", "Compute Resources", "sub_section"),
                            _n("sub:customer:sum:backup", "Backup Services", "sub_section"),
                        ],
                    ),
                    _n(
                        "sec:customer:virtualization",
                        "Virtualization",
                        "section",
                        children=[
                            _n("sub:customer:virt:classic", "Classic Architecture", "sub_section"),
                            _n("sub:customer:virt:hyperconv", "Hyperconverged Architecture", "sub_section"),
                            _n("sub:customer:virt:nutanix", "Pure Nutanix AHV", "sub_section"),
                            _n("sub:customer:virt:power", "Power Architecture", "sub_section"),
                        ],
                    ),
                    _n("sec:customer:availability", "Availability", "section"),
                    _n(
                        "sec:customer:backup",
                        "Backup",
                        "section",
                        children=[
                            _n("sub:customer:backup:veeam", "Veeam", "sub_section"),
                            _n("sub:customer:backup:zerto", "Zerto", "sub_section"),
                            _n("sub:customer:backup:netbackup", "NetBackup", "sub_section"),
                        ],
                    ),
                    _n("sec:customer:billing", "Billing", "section"),
                    _n("sec:customer:phys_inv", "Physical Inventory", "section"),
                    _n("sec:customer:s3", "S3", "section"),
                    _n("action:customer:export", "Export", "action"),
                ],
            ),
        ],
    )

    query_grp = _n(
        "grp:query",
        "Query",
        "page_group",
        icon="solar:code-square-bold-duotone",
        sort_order=40,
        children=[
            _n(
                "page:query_explorer",
                "Query Explorer",
                "page",
                route_pattern="/query-explorer",
                sort_order=10,
                children=[
                    _n("sec:qe:catalog", "Query Catalog", "section"),
                    _n("sec:qe:run", "Run Query", "section"),
                    _n("sec:qe:edit_sql", "Edit SQL", "section"),
                    _n("sec:qe:add_query", "Add New Query", "section"),
                    _n("action:qe:export", "Export Result", "action"),
                ],
            ),
        ],
    )

    settings_grp = _n(
        "grp:settings",
        "Settings",
        "page_group",
        icon="solar:settings-bold-duotone",
        sort_order=50,
        children=[
            _n("page:settings_users", "User Management", "config", route_pattern="/settings/iam/users", sort_order=10),
            _n("page:settings_roles", "Role Management", "config", route_pattern="/settings/iam/roles", sort_order=20),
            _n("page:settings_permissions", "Permission Management", "config", route_pattern="/settings/iam/permissions", sort_order=30),
            _n("page:settings_teams", "Team Management", "config", route_pattern="/settings/iam/teams", sort_order=40),
            _n("page:settings_ldap", "LDAP Configuration", "config", route_pattern="/settings/integrations/ldap", sort_order=50),
            _n("page:settings_integrations", "Integrations Overview", "config", route_pattern="/settings/integrations", sort_order=55),
            _n("page:settings_auranotify", "AuraNotify Integration", "config", route_pattern="/settings/integrations/auranotify", sort_order=58),
            _n(
                "page:settings_crm_overview",
                "CRM Dynamics 365 overview",
                "config",
                route_pattern="/settings/integrations/crm",
                sort_order=56,
            ),
            _n(
                "page:settings_service_mapping",
                "CRM service mapping",
                "config",
                route_pattern="/settings/integrations/crm/service-mapping",
                sort_order=57,
            ),
            _n(
                "page:settings_crm_aliases",
                "CRM customer aliases",
                "config",
                route_pattern="/settings/integrations/crm/aliases",
                sort_order=58,
            ),
            _n(
                "page:settings_crm_thresholds",
                "CRM capacity thresholds",
                "config",
                route_pattern="/settings/integrations/crm/thresholds",
                sort_order=59,
            ),
            _n(
                "page:settings_crm_price_overrides",
                "CRM price overrides",
                "config",
                route_pattern="/settings/integrations/crm/price-overrides",
                sort_order=60,
            ),
            _n(
                "page:settings_crm_calc_config",
                "CRM calculation variables",
                "config",
                route_pattern="/settings/integrations/crm/calc-config",
                sort_order=61,
            ),
            _n(
                "page:settings_crm_panels",
                "CRM panel registry",
                "config",
                route_pattern="/settings/integrations/crm/panels",
                sort_order=62,
            ),
            _n(
                "page:settings_crm_infra_sources",
                "CRM panel infra-source bindings",
                "config",
                route_pattern="/settings/integrations/crm/infra-sources",
                sort_order=63,
            ),
            _n(
                "page:settings_crm_resource_ratios",
                "CRM resource ratios",
                "config",
                route_pattern="/settings/integrations/crm/resource-ratios",
                sort_order=64,
            ),
            _n(
                "page:settings_crm_unit_conversions",
                "CRM unit conversions",
                "config",
                route_pattern="/settings/integrations/crm/unit-conversions",
                sort_order=65,
            ),
            _n(
                "page:dashboard_crm_sellable",
                "CRM Sellable Potential dashboard",
                "view",
                route_pattern="/crm/sellable-potential",
                sort_order=10,
            ),
            _n("page:settings_auth", "Auth Settings", "config", route_pattern="/settings/iam/auth", sort_order=60),
            _n("page:settings_audit", "Audit Log", "config", route_pattern="/settings/iam/audit", sort_order=70),
        ],
    )

    return [dashboard, global_grp, customer_grp, query_grp, settings_grp]
