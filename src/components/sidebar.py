import dash_mantine_components as dmc
from dash_iconify import DashIconify
from dash import html


# href -> permission code (page:*)
NAV_ITEM_SPECS: list[tuple[str, str, str, str]] = [
    ("/", "Overview", "solar:home-smile-bold-duotone", "page:overview"),
    ("/datacenters", "Data Centers", "solar:server-square-bold-duotone", "page:datacenters"),
    ("/global-view", "Global View", "solar:global-bold-duotone", "page:global_view"),
    ("/customer-view", "Customer View", "solar:users-group-rounded-bold-duotone", "page:customer_view"),
    ("/query-explorer", "Query Explorer", "solar:code-square-bold-duotone", "page:query_explorer"),
]

SETTINGS_ENTRY_CODES: tuple[str, ...] = (
    "grp:settings",
    "page:settings_users",
    "page:settings_roles",
    "page:settings_permissions",
    "page:settings_ldap",
    "page:settings_teams",
    "page:settings_auth",
    "page:settings_audit",
)


def _settings_visible(perm_map: dict | None) -> bool:
    if not perm_map:
        return True
    return any(_perm_allows(perm_map, c) for c in SETTINGS_ENTRY_CODES)


def _perm_allows(perm_map: dict | None, code: str) -> bool:
    if not perm_map:
        return True
    entry = perm_map.get(code) or {}
    return bool(entry.get("view"))


def create_sidebar_nav(active_path, perm_map: dict | None = None, username: str | None = None):
    brand = html.Div(
        [
            DashIconify(icon="mdi:cloud", width=32, color="#4318FF"),
            html.Span(
                "BULUTİSTAN",
                style={"fontSize": "24px", "fontWeight": "700", "color": "#2B3674", "marginLeft": "10px"},
            ),
        ],
        style={"display": "flex", "alignItems": "center", "marginBottom": "40px", "paddingLeft": "16px"},
    )

    search_box = dmc.TextInput(
        placeholder="Search...",
        leftSection=DashIconify(icon="solar:magnifer-linear", width=16, color="#A3AED0"),
        rightSection=dmc.Text("⌘K", size="xs", c="dimmed", style={"whiteSpace": "nowrap"}),
        size="sm",
        radius="md",
        variant="filled",
        className="sidebar-search",
        style={"marginBottom": "24px"},
        styles={
            "input": {
                "backgroundColor": "#F4F7FE",
                "border": "none",
                "color": "#2B3674",
                "fontSize": "13px",
                "cursor": "default",
            }
        },
    )

    links: list = []
    for href, label, icon, pcode in NAV_ITEM_SPECS:
        if not _perm_allows(perm_map, pcode):
            continue
        if href == "/":
            active = active_path in ("/", "")
        elif href == "/datacenters":
            active = active_path.startswith("/datacenter") or active_path == "/datacenters"
        else:
            active = active_path == href
        links.append(
            dmc.NavLink(
                label=label,
                leftSection=DashIconify(icon=icon, width=20),
                href=href,
                className="sidebar-link",
                active=active,
                variant="subtle",
                color="indigo",
                style={"borderRadius": "8px", "fontWeight": "500", "marginBottom": "5px"},
            )
        )

    if _settings_visible(perm_map):
        settings_active = active_path.startswith("/settings")
        links.append(
            dmc.NavLink(
                label="Settings",
                leftSection=DashIconify(icon="solar:settings-bold-duotone", width=20),
                href="/settings",
                className="sidebar-link",
                active=settings_active,
                variant="subtle",
                color="indigo",
                style={"borderRadius": "8px", "fontWeight": "500", "marginBottom": "5px"},
            )
        )

    links.append(
        dmc.NavLink(
            label="Analytics",
            leftSection=DashIconify(icon="solar:chart-square-bold-duotone", width=20),
            href="#",
            className="sidebar-link",
            disabled=True,
        ),
    )
    footer = html.Div(
        style={"marginTop": "auto", "paddingTop": "16px", "borderTop": "1px solid #E9ECEF"},
        children=[
            dmc.Text(username or "Signed in", size="xs", c="dimmed", mb="xs", style={"paddingLeft": "8px"}),
            html.A(
                dmc.Button("Sign out", variant="light", color="gray", size="xs", fullWidth=True),
                href="/auth/logout",
                style={"textDecoration": "none"},
            ),
        ],
    )

    return html.Div([brand, search_box, dmc.Stack(links, gap=4), footer])
