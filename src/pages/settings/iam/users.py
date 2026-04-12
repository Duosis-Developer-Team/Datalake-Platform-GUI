"""User management — list, create local user, LDAP import, edit (slide-in panel)."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import dcc, html
from dash_iconify import DashIconify

from src.services import admin_client as settings_crud
from src.utils.ui_tokens import ON_SURFACE, section_header, settings_page_shell


def build_layout(search: str | None = None) -> html.Div:
    rows = settings_crud.list_users_with_roles()
    roles = settings_crud.list_roles()
    teams = settings_crud.list_teams()

    role_options = [{"value": str(r["id"]), "label": str(r["name"])} for r in roles]
    team_options = [{"value": str(t["id"]), "label": str(t["name"])} for t in teams]

    table_rows = []
    for u in rows:
        uid = int(u.get("id", 0))
        src = str(u.get("source", ""))
        src_badge = dmc.Badge(src, size="xs", color="cyan" if src == "ldap" else "gray", variant="light")
        active_badge = dmc.Badge(
            "Active" if u.get("is_active") else "Inactive",
            size="xs",
            color="green" if u.get("is_active") else "gray",
            variant="light",
        )
        table_rows.append(
            html.Tr(
                style={"borderBottom": "1px solid #eef1f4"},
                children=[
                    html.Td(
                        dmc.Group(
                            gap="xs",
                            children=[
                                dmc.Avatar(
                                    (str(u.get("username", "?"))[:2]).upper(),
                                    radius="md",
                                    color="indigo",
                                    size="sm",
                                ),
                                dmc.Stack(
                                    gap=0,
                                    children=[
                                        dmc.Text(str(u.get("username", "")), fw=700, size="sm"),
                                        dmc.Text(str(u.get("email") or ""), size="xs", c="dimmed"),
                                    ],
                                ),
                            ],
                        )
                    ),
                    html.Td(str(u.get("display_name") or "—")),
                    html.Td(src_badge),
                    html.Td(active_badge),
                    html.Td(
                        dmc.Text(
                            str(u.get("roles", "")),
                            size="sm",
                            style={"whiteSpace": "nowrap", "overflow": "hidden", "textOverflow": "ellipsis", "maxWidth": "min(320px, 28vw)"},
                        )
                    ),
                    html.Td(
                        dmc.Button(
                            "Edit",
                            id={"type": "iam-user-edit", "uid": uid},
                            size="xs",
                            variant="light",
                            color="indigo",
                        )
                    ),
                ],
            )
        )

    ad_import_inner = [
        dmc.Group(
            justify="space-between",
            align="center",
            mb="sm",
            children=[
                dmc.Text("Import from Active Directory", fw=700, c=ON_SURFACE),
                dmc.Tooltip(
                    label=_ad_search_help_content(),
                    multiline=True,
                    w=440,
                    position="bottom-end",
                    withArrow=True,
                    children=dmc.ActionIcon(
                        DashIconify(icon="solar:question-circle-bold-duotone", width=20),
                        variant="subtle",
                        color="gray",
                        radius="xl",
                    ),
                ),
            ],
        ),
        dmc.Text(
            "Search by name or email, or enter an OU path to list all users under that OU.",
            size="sm",
            c="dimmed",
            mb="md",
        ),
        dmc.Group(
            gap="sm",
            align="flex-end",
            wrap="nowrap",
            children=[
                html.Div(
                    style={"flex": 1, "minWidth": "200px"},
                    children=[
                        dmc.Text("Search query", size="xs", fw=600, c="dimmed", mb=4),
                        dcc.Input(
                            id="ad-user-search-input",
                            type="text",
                            placeholder="Name, email, or OU=…,DC=… (min. 2 chars)",
                            debounce=True,
                            style=_input_style(),
                        ),
                    ],
                ),
                dmc.Button(
                    "Search directory",
                    id="ad-user-search-btn",
                    variant="filled",
                    color="indigo",
                ),
            ],
        ),
        html.Div(id="ad-user-search-feedback", style={"marginTop": "12px"}),
        dmc.Text("Directory accounts to import", size="xs", fw=600, c="dimmed", mt="sm", mb=4),
        html.Div(
            style={
                "maxHeight": "280px",
                "overflowY": "auto",
                "marginTop": "4px",
            },
            children=[
                dcc.Checklist(
                    id="ad-import-checklist",
                    options=[],
                    value=[],
                    labelStyle={"display": "block", "marginBottom": "8px"},
                    inputStyle={"marginRight": "8px"},
                ),
            ],
        ),
        dmc.Group(
            gap="md",
            mt="md",
            align="flex-start",
            children=[
                html.Div(
                    style={"flex": 1, "minWidth": "200px"},
                    children=[
                        dmc.Text("Roles to assign", size="xs", fw=600, c="dimmed", mb=4),
                        dmc.MultiSelect(
                            id="ad-import-role-ids",
                            data=role_options,
                            placeholder="Select roles",
                            searchable=True,
                            clearable=True,
                            nothingFoundMessage="No roles",
                        ),
                    ],
                ),
                html.Div(
                    style={"flex": 1, "minWidth": "200px"},
                    children=[
                        dmc.Text("Teams to assign", size="xs", fw=600, c="dimmed", mb=4),
                        dmc.MultiSelect(
                            id="ad-import-team-ids",
                            data=team_options,
                            placeholder="Select teams",
                            searchable=True,
                            clearable=True,
                            nothingFoundMessage="No teams",
                        ),
                    ],
                ),
            ],
        ),
        dmc.Group(
            gap="sm",
            mt="md",
            children=[
                dmc.Button(
                    "Import selected",
                    id="ad-import-submit-btn",
                    variant="gradient",
                    gradient={"from": "indigo", "to": "violet", "deg": 105},
                ),
            ],
        ),
        html.Div(id="ad-import-feedback", style={"marginTop": "12px"}),
    ]

    local_form = [
        dmc.Text(
            "Create a local account or edit an existing user. Team members inherit permissions from team roles.",
            size="sm",
            c="dimmed",
            mb="md",
        ),
        dmc.SimpleGrid(
            cols=1,
            spacing="sm",
            children=[
                html.Div(
                    [
                        dmc.Text("Username", size="xs", fw=600, c="dimmed", mb=4),
                        dcc.Input(id="iam-user-form-username", type="text", style=_input_style()),
                    ]
                ),
                html.Div(
                    id="iam-user-form-password-wrap",
                    children=[
                        dmc.Text("Password", size="xs", fw=600, c="dimmed", mb=4),
                        dcc.Input(id="iam-user-form-password", type="password", style=_input_style()),
                    ],
                ),
                html.Div(
                    [
                        dmc.Text("Display name", size="xs", fw=600, c="dimmed", mb=4),
                        dcc.Input(id="iam-user-form-display-name", type="text", style=_input_style()),
                    ]
                ),
                html.Div(
                    [
                        dmc.Text("Email", size="xs", fw=600, c="dimmed", mb=4),
                        dcc.Input(id="iam-user-form-email", type="text", style=_input_style()),
                    ]
                ),
                html.Div(
                    [
                        dmc.Text("Roles", size="xs", fw=600, c="dimmed", mb=4),
                        dmc.MultiSelect(
                            id="iam-user-form-role-ids",
                            data=role_options,
                            placeholder="Select roles",
                            searchable=True,
                            clearable=True,
                        ),
                    ]
                ),
                html.Div(
                    [
                        dmc.Text("Teams", size="xs", fw=600, c="dimmed", mb=4),
                        dmc.MultiSelect(
                            id="iam-user-form-team-ids",
                            data=team_options,
                            placeholder="Select teams",
                            searchable=True,
                            clearable=True,
                        ),
                    ]
                ),
            ],
        ),
        html.Div(id="iam-user-form-feedback", style={"marginTop": "12px"}),
        dmc.Group(
            gap="sm",
            mt="md",
            justify="flex-end",
            children=[
                dmc.Button("Save", id="iam-user-form-save", variant="filled", color="indigo"),
            ],
        ),
    ]

    slide_panel = html.Div(
        id="user-slide-panel",
        className="user-slide-panel closed",
        style={"alignSelf": "stretch"},
        children=[
            dmc.Paper(
                p="lg",
                radius="md",
                withBorder=True,
                style={"minWidth": "400px", "maxHeight": "calc(100vh - 220px)", "overflowY": "auto"},
                children=[
                    dmc.Group(
                        justify="space-between",
                        align="center",
                        mb="md",
                        wrap="nowrap",
                        children=[
                            dmc.Text(id="iam-user-panel-title", children="User", fw=700, c=ON_SURFACE),
                            dmc.ActionIcon(
                                DashIconify(icon="solar:close-circle-bold", width=22),
                                id="iam-user-panel-close",
                                variant="subtle",
                                color="gray",
                                radius="xl",
                            ),
                        ],
                    ),
                    dmc.Tabs(
                        [
                            dmc.TabsList(
                                [
                                    dmc.TabsTab("Local account", value="local"),
                                    dmc.TabsTab("Directory import", value="ad"),
                                ],
                                grow=True,
                            ),
                            dmc.TabsPanel(dmc.Stack(gap="sm", children=local_form), value="local", pt="md"),
                            dmc.TabsPanel(dmc.Stack(gap="sm", children=ad_import_inner), value="ad", pt="md"),
                        ],
                        value="local",
                        id="iam-user-form-tabs",
                        color="indigo",
                    ),
                ],
            ),
        ],
    )

    table = dmc.Paper(
        p=0,
        radius="md",
        withBorder=True,
        style={"flex": "1", "minWidth": 0},
        children=[
            html.Div(
                style={"padding": "16px 20px", "borderBottom": "1px solid #eef1f4"},
                children=dmc.Group(
                    justify="space-between",
                    align="center",
                    children=[
                        dmc.Text("Directory", fw=700, c=ON_SURFACE),
                        dmc.Button(
                            "Create user",
                            id="iam-user-open-create",
                            leftSection=DashIconify(icon="solar:user-plus-bold-duotone", width=18),
                            variant="gradient",
                            gradient={"from": "indigo", "to": "violet", "deg": 105},
                        ),
                    ],
                ),
            ),
            html.Div(
                style={"overflowX": "auto"},
                children=[
                    html.Table(
                        style={"width": "100%", "borderCollapse": "collapse", "fontSize": "13px"},
                        children=[
                            html.Thead(
                                html.Tr(
                                    [
                                        html.Th("User", style=_th()),
                                        html.Th("Display", style=_th()),
                                        html.Th("Source", style=_th()),
                                        html.Th("Status", style=_th()),
                                        html.Th("Roles", style=_th()),
                                        html.Th("Actions", style=_th()),
                                    ]
                                )
                            ),
                            html.Tbody(table_rows),
                        ],
                    )
                ],
            ),
        ],
    )

    body_row = html.Div(
        style={"display": "flex", "gap": "24px", "alignItems": "flex-start", "width": "100%"},
        children=[slide_panel, table],
    )

    return html.Div(
        [
            dcc.Store(id="ad-search-results-store", data=[]),
            dcc.Store(id="iam-user-panel-store", data={"open": False, "mode": "create", "uid": None}),
            settings_page_shell(
                [
                    section_header(
                        "Users",
                        "Provision local accounts, import from AD, and manage directory members.",
                        icon="solar:users-group-rounded-bold-duotone",
                    ),
                    body_row,
                ]
            ),
        ]
    )


def _ad_search_help_content() -> html.Div:
    """Tooltip content for the AD search panel help icon."""
    _mono = {"fontFamily": "monospace", "fontSize": "12px", "background": "rgba(0,0,0,0.06)", "borderRadius": "4px", "padding": "1px 5px"}
    examples = [
        ("jsmith", "matches sAMAccountName, CN, or displayName"),
        ("john.smith@corp.com", "matches by mail (email)"),
        ("OU=Sales,OU=Users,DC=corp,DC=local", "lists all users under that OU (when query starts with OU=)"),
        ("Jane Doe", "search by full display name"),
    ]
    rows = []
    for query, desc in examples:
        rows.append(
            html.Tr(
                children=[
                    html.Td(html.Span(query, style=_mono), style={"paddingRight": "10px", "paddingBottom": "4px", "whiteSpace": "nowrap"}),
                    html.Td(dmc.Text(desc, size="xs", c="dimmed"), style={"paddingBottom": "4px"}),
                ]
            )
        )

    return html.Div(
        style={"fontSize": "13px", "lineHeight": "1.6"},
        children=[
            dmc.Text("Search by username, display name, email, CN, or an OU path.", size="xs", fw=600, mb=6),
            html.Table(children=[html.Tbody(rows)], style={"marginBottom": "10px"}),
            dmc.Divider(mb=8),
            dmc.Stack(
                gap=3,
                children=[
                    dmc.Text("Tips", size="xs", fw=600, mb=2),
                    dmc.Text("• Minimum 2 characters required", size="xs", c="dimmed"),
                    dmc.Text("• OU search: enter a path starting with OU= to list users in that subtree", size="xs", c="dimmed"),
                    dmc.Text("• Results are capped at 50 entries per search", size="xs", c="dimmed"),
                    dmc.Text("• Search scope is defined by Search Base DN in Settings › Integrations › LDAP", size="xs", c="dimmed"),
                ],
            ),
        ],
    )


def _input_style():
    return {
        "width": "100%",
        "padding": "10px 12px",
        "borderRadius": "8px",
        "border": "1px solid #e9ecef",
        "fontSize": "14px",
        "fontFamily": "inherit",
    }


def _th():
    return {
        "textAlign": "left",
        "padding": "12px 16px",
        "borderBottom": "1px solid #e9ecef",
        "color": "#2B3674",
        "fontSize": "11px",
        "textTransform": "uppercase",
    }
