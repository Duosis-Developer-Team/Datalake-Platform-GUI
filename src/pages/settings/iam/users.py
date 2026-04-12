"""User management — list, create local user, LDAP import, edit."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import dcc, html
from dash_iconify import DashIconify

from src.services import admin_client as settings_crud
from src.utils.ui_tokens import ON_SURFACE, html_submit_button_gradient, section_header, settings_page_shell


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
                    html.Td(dmc.Text(str(u.get("roles", "")), size="sm", style={"maxWidth": "240px"})),
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

    ad_import_card = dmc.Paper(
        p="lg",
        radius="md",
        withBorder=True,
        mb="lg",
        children=[
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
                "Search the directory, select one or more accounts, then assign roles and teams before import.",
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
                                placeholder="min. 2 characters (name, email, …)",
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
        ],
    )

    form_card = dmc.Paper(
        p="lg",
        radius="md",
        withBorder=True,
        mb="lg",
        children=[
            dmc.Text("Create local user", fw=700, mb="sm", c=ON_SURFACE),
            dmc.Text(
                "LDAP users can also be provisioned via directory import above.",
                size="sm",
                c="dimmed",
                mb="md",
            ),
            html.Form(
                method="POST",
                action="/auth/settings/create-user",
                children=[
                    dmc.SimpleGrid(
                        cols=2,
                        spacing="md",
                        children=[
                            html.Div(
                                [
                                    dmc.Text("Username", size="xs", fw=600, c="dimmed", mb=4),
                                    dcc.Input(name="username", required=True, style=_input_style()),
                                ]
                            ),
                            html.Div(
                                [
                                    dmc.Text("Password", size="xs", fw=600, c="dimmed", mb=4),
                                    dcc.Input(name="password", type="password", required=True, style=_input_style()),
                                ]
                            ),
                            html.Div(
                                [
                                    dmc.Text("Display name", size="xs", fw=600, c="dimmed", mb=4),
                                    dcc.Input(name="display_name", style=_input_style()),
                                ]
                            ),
                            html.Div(
                                [
                                    dmc.Text("Roles (IDs, comma-separated)", size="xs", fw=600, c="dimmed", mb=4),
                                    dcc.Input(name="role_ids", placeholder="e.g. 1,2", style=_input_style()),
                                ]
                            ),
                        ],
                    ),
                    html_submit_button_gradient(
                        "Create user",
                        icon="solar:user-plus-bold-duotone",
                        style_extra={"marginTop": "16px"},
                    ),
                ],
            ),
        ],
    )

    table = dmc.Paper(
        p=0,
        radius="md",
        withBorder=True,
        children=[
            html.Div(
                style={"padding": "16px 20px", "borderBottom": "1px solid #eef1f4"},
                children=dmc.Text("Directory", fw=700, c=ON_SURFACE),
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

    return html.Div(
        [
            dcc.Store(id="ad-search-results-store", data=[]),
            dcc.Store(id="iam-edit-user-store", data=None),
            dmc.Modal(
                title="Directory search results",
                id="ad-search-modal",
                size="xl",
                opened=False,
                children=[
                    dmc.Text("Select accounts to import.", size="xs", c="dimmed", mb="sm"),
                    dcc.Checklist(
                        id="ad-import-checklist",
                        options=[],
                        value=[],
                        labelStyle={"display": "block", "marginBottom": "8px"},
                        inputStyle={"marginRight": "8px"},
                    ),
                ],
            ),
            dmc.Modal(
                title="Edit user",
                id="iam-user-edit-modal",
                size="lg",
                opened=False,
                children=[
                    dmc.Text("Display name", size="xs", fw=600, c="dimmed", mb=4),
                    dcc.Input(id="iam-user-edit-display-name", type="text", style=_input_style()),
                    dmc.Text("Email", size="xs", fw=600, c="dimmed", mb=4, mt="sm"),
                    dcc.Input(id="iam-user-edit-email", type="text", style=_input_style()),
                    dmc.Text("Roles", size="xs", fw=600, c="dimmed", mb=4, mt="sm"),
                    dmc.MultiSelect(
                        id="iam-user-edit-role-ids",
                        data=role_options,
                        placeholder="Roles",
                        searchable=True,
                        clearable=True,
                    ),
                    dmc.Text("Teams", size="xs", fw=600, c="dimmed", mb=4, mt="sm"),
                    dmc.MultiSelect(
                        id="iam-user-edit-team-ids",
                        data=team_options,
                        placeholder="Teams",
                        searchable=True,
                        clearable=True,
                    ),
                    html.Div(id="iam-user-edit-feedback", style={"marginTop": "12px"}),
                    dmc.Group(
                        gap="sm",
                        mt="md",
                        justify="flex-end",
                        children=[
                            dmc.Button("Cancel", id="iam-user-edit-cancel", variant="default", color="gray"),
                            dmc.Button(
                                "Save",
                                id="iam-user-edit-save",
                                variant="filled",
                                color="indigo",
                            ),
                        ],
                    ),
                ],
            ),
            settings_page_shell(
                [
                    section_header(
                        "Users",
                        "Provision local accounts, import from AD, and manage directory members.",
                        icon="solar:users-group-rounded-bold-duotone",
                    ),
                    ad_import_card,
                    form_card,
                    table,
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
        ("john", "all users with 'john' anywhere in name"),
        ("svc-backup", "service / system account lookup"),
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
            dmc.Text("Search by any of: username, display name, email, or CN.", size="xs", fw=600, mb=6),
            html.Table(children=[html.Tbody(rows)], style={"marginBottom": "10px"}),
            dmc.Divider(mb=8),
            dmc.Stack(
                gap=3,
                children=[
                    dmc.Text("Tips", size="xs", fw=600, mb=2),
                    dmc.Text("• Minimum 2 characters required", size="xs", c="dimmed"),
                    dmc.Text("• Wildcard (*) is applied automatically on both sides", size="xs", c="dimmed"),
                    dmc.Text("• Results are capped at 50 entries per search", size="xs", c="dimmed"),
                    dmc.Text("• Search scope is defined by the Search Base DN in Settings › Integrations › LDAP", size="xs", c="dimmed"),
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
