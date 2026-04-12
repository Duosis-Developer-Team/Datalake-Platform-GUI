"""Team management — slide-in panel for create/edit, membership modal."""

from __future__ import annotations

from urllib.parse import parse_qs

import dash_mantine_components as dmc
from dash import dcc, html
from dash_iconify import DashIconify

from src.services import admin_client as settings_crud
from src.utils.ui_tokens import (
    ON_SURFACE,
    html_submit_button_light,
    kpi_card,
    section_header,
    settings_page_shell,
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


def build_layout(search: str | None = None) -> html.Div:
    q = ""
    if search:
        qs = parse_qs(search.lstrip("?"))
        q = (qs.get("q") or [""])[0].strip().lower()

    teams = settings_crud.list_teams()
    users = settings_crud.list_users_with_roles()
    user_options = [
        {"value": str(u["id"]), "label": f"{u.get('username', '')} ({u.get('display_name') or '—'})"}
        for u in users
    ]
    roles = settings_crud.list_roles()
    role_options = [{"value": str(r["id"]), "label": str(r["name"])} for r in roles]

    filtered = [t for t in teams if not q or q in str(t.get("name", "")).lower()]
    total_members = sum(int(t.get("member_count") or 0) for t in teams)
    largest = max(teams, key=lambda t: int(t.get("member_count") or 0), default=None)

    rows = []
    for t in filtered:
        tid = int(t["id"])
        initials = "".join(w[0] for w in str(t.get("name", "T"))[:2].upper().split())[:2]
        desc = t.get("description")
        roles_str = str(t.get("roles") or "—")
        rows.append(
            html.Tr(
                style={"borderBottom": "1px solid #eef1f4"},
                children=[
                    html.Td(
                        dmc.Group(
                            gap="sm",
                            children=[
                                dmc.Avatar(initials, radius="md", color="grape", size="md"),
                                dmc.Stack(
                                    gap=0,
                                    children=[
                                        dmc.Text(str(t.get("name", "")), fw=700, size="sm"),
                                        dmc.Text(f"ID: T-{tid:04d}", size="xs", c="dimmed"),
                                    ],
                                ),
                            ],
                        )
                    ),
                    html.Td(str(desc) if desc else "—", style={"color": "#6c757d", "fontSize": "13px", "maxWidth": "240px"}),
                    html.Td(str(t.get("created_by_name") or t.get("created_by") or "—")),
                    html.Td(
                        dmc.Text(
                            roles_str,
                            size="sm",
                            style={"whiteSpace": "nowrap", "overflow": "hidden", "textOverflow": "ellipsis", "maxWidth": "min(280px, 26vw)"},
                        )
                    ),
                    html.Td(dmc.Badge(str(t.get("member_count", 0)), color="indigo", variant="light")),
                    html.Td(
                        dmc.Group(
                            gap="xs",
                            children=[
                                dmc.Button(
                                    "Edit",
                                    id={"type": "iam-team-edit", "tid": tid},
                                    size="xs",
                                    variant="light",
                                    color="indigo",
                                ),
                                dmc.Button(
                                    "Members",
                                    id={"type": "iam-team-members", "tid": tid},
                                    size="xs",
                                    variant="light",
                                    color="grape",
                                ),
                            ],
                        )
                    ),
                ],
            )
        )

    panel_form = [
        dmc.Text(
            "Team roles apply to all members in addition to each user's own roles.",
            size="sm",
            c="dimmed",
            mb="md",
        ),
        dmc.Text("Team name", size="xs", fw=600, c="dimmed", mb=4),
        dcc.Input(id="iam-team-form-name", type="text", style=_input_style()),
        dmc.Text("Description", size="xs", fw=600, c="dimmed", mb=4, mt="sm"),
        dcc.Input(id="iam-team-form-description", type="text", style=_input_style(), placeholder="Optional"),
        dmc.Text("Roles", size="xs", fw=600, c="dimmed", mb=4, mt="sm"),
        dmc.MultiSelect(
            id="iam-team-form-role-ids",
            data=role_options,
            placeholder="Roles granted via this team",
            searchable=True,
            clearable=True,
        ),
        html.Div(id="iam-team-form-feedback", style={"marginTop": "12px"}),
        dmc.Group(
            gap="sm",
            mt="md",
            justify="flex-end",
            children=[dmc.Button("Save", id="iam-team-form-save", variant="filled", color="indigo")],
        ),
    ]

    slide_panel = html.Div(
        id="team-slide-panel",
        className="team-slide-panel closed",
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
                            dmc.Text(id="iam-team-panel-title", children="Team", fw=700, c=ON_SURFACE),
                            dmc.ActionIcon(
                                DashIconify(icon="solar:close-circle-bold", width=22),
                                id="iam-team-panel-close",
                                variant="subtle",
                                color="gray",
                                radius="xl",
                            ),
                        ],
                    ),
                    dmc.Stack(gap="sm", children=panel_form),
                ],
            ),
        ],
    )

    toolbar = html.Form(
        method="GET",
        action="/settings/iam/teams",
        style={"flex": 1, "maxWidth": "420px", "display": "flex", "gap": "8px", "alignItems": "center"},
        children=[
            dcc.Input(
                name="q",
                type="text",
                placeholder="Filter teams by name…",
                value=q,
                style={
                    "flex": 1,
                    "padding": "10px 12px",
                    "borderRadius": "8px",
                    "border": "1px solid #e9ecef",
                    "fontFamily": "inherit",
                },
            ),
            html_submit_button_light("Filter", scheme="gray", small=True),
        ],
    )

    stats = dmc.SimpleGrid(
        cols=3,
        spacing="md",
        children=[
            kpi_card("Total teams", len(teams), icon="solar:users-group-two-rounded-bold-duotone"),
            kpi_card("Total members", total_members, icon="solar:user-check-rounded-bold-duotone"),
            kpi_card(
                "Largest team",
                str(largest.get("name", "—")) if largest else "—",
                trend=f"{int(largest.get('member_count') or 0)} members" if largest else None,
                icon="solar:chart-2-bold-duotone",
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
                children=dmc.Text("Teams", fw=700, c=ON_SURFACE),
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
                                        html.Th("Team", style=_th()),
                                        html.Th("Description", style=_th()),
                                        html.Th("Created by", style=_th()),
                                        html.Th("Roles", style=_th()),
                                        html.Th("Members", style=_th()),
                                        html.Th("Actions", style=_th()),
                                    ]
                                )
                            ),
                            html.Tbody(rows or [html.Tr([html.Td("No teams match.", colSpan=6)])]),
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

    filter_row = dmc.Group(
        justify="space-between",
        align="flex-end",
        mb="md",
        wrap="wrap",
        children=[
            toolbar,
            dmc.Button(
                "Create team",
                id="iam-team-open-create",
                leftSection=DashIconify(icon="solar:add-circle-bold-duotone", width=18),
                variant="gradient",
                gradient={"from": "indigo", "to": "violet", "deg": 105},
            ),
        ],
    )

    return html.Div(
        [
            dcc.Store(id="iam-team-panel-store", data={"open": False, "mode": "create", "tid": None}),
            dcc.Store(id="iam-team-members-tid-store", data=None),
            dmc.Modal(
                title="Team members",
                id="iam-team-members-modal",
                size="lg",
                opened=False,
                children=[
                    dmc.Text(
                        "Members inherit permissions from team roles shown on the team record.",
                        size="xs",
                        c="dimmed",
                        mb="sm",
                    ),
                    html.Div(id="iam-team-members-list"),
                    dmc.Text("Add users", size="xs", fw=600, c="dimmed", mb=4, mt="md"),
                    dmc.MultiSelect(
                        id="iam-team-add-user-ids",
                        data=user_options,
                        placeholder="Select users to add",
                        searchable=True,
                        clearable=True,
                    ),
                    dmc.Button(
                        "Add selected",
                        id="iam-team-add-members-btn",
                        mt="sm",
                        variant="light",
                        color="grape",
                    ),
                    html.Div(id="iam-team-members-feedback", style={"marginTop": "8px"}),
                ],
            ),
            settings_page_shell(
                [
                    section_header(
                        "Teams management",
                        "Organize collaboration groups, rename teams, and manage membership.",
                        icon="solar:users-group-two-rounded-bold-duotone",
                    ),
                    stats,
                    dmc.Space(h="md"),
                    filter_row,
                    body_row,
                ]
            ),
        ]
    )


def _th():
    return {
        "textAlign": "left",
        "padding": "12px 16px",
        "borderBottom": "1px solid #e9ecef",
        "color": "#2B3674",
        "fontSize": "11px",
        "textTransform": "uppercase",
    }
