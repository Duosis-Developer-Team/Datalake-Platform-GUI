"""Team management — create teams and view membership."""

from __future__ import annotations

from urllib.parse import parse_qs

import dash_mantine_components as dmc
from dash import dcc, html

from src.services import admin_client as settings_crud
from src.utils.ui_tokens import (
    ON_SURFACE,
    html_submit_button_gradient,
    html_submit_button_light,
    kpi_card,
    section_header,
    settings_page_shell,
)


def build_layout(search: str | None = None) -> html.Div:
    q = ""
    if search:
        qs = parse_qs(search.lstrip("?"))
        q = (qs.get("q") or [""])[0].strip().lower()

    teams = settings_crud.list_teams()
    filtered = [t for t in teams if not q or q in str(t.get("name", "")).lower()]
    total_members = sum(int(t.get("member_count") or 0) for t in teams)
    largest = max(teams, key=lambda t: int(t.get("member_count") or 0), default=None)

    rows = []
    for t in filtered:
        tid = int(t["id"])
        initials = "".join(w[0] for w in str(t.get("name", "T"))[:2].upper().split())[:2]
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
                    html.Td("—", style={"color": "#6c757d", "fontSize": "13px"}),
                    html.Td(str(t.get("created_by_name") or t.get("created_by") or "—")),
                    html.Td(dmc.Badge(str(t.get("member_count", 0)), color="indigo", variant="light")),
                ],
            )
        )

    toolbar = dmc.Group(
        justify="space-between",
        align="flex-end",
        mb="md",
        wrap="nowrap",
        children=[
            html.Form(
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
                        },
                    ),
                    html_submit_button_light("Filter", scheme="gray", small=True),
                ],
            ),
            html.Form(
                method="POST",
                action="/auth/settings/team-create",
                style={"display": "flex", "gap": "8px", "alignItems": "flex-end"},
                children=[
                    dcc.Input(
                        name="name",
                        placeholder="New team name",
                        required=True,
                        style={
                            "padding": "8px 12px",
                            "borderRadius": "8px",
                            "border": "1px solid #e9ecef",
                            "minWidth": "200px",
                        },
                    ),
                    html_submit_button_gradient("Create team", icon="solar:add-circle-bold-duotone"),
                ],
            ),
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
                                        html.Th("Members", style=_th()),
                                    ]
                                )
                            ),
                            html.Tbody(rows or [html.Tr([html.Td("No teams match.", colSpan=4)])]),
                        ],
                    )
                ],
            ),
        ],
    )

    return html.Div(
        settings_page_shell(
            [
                section_header(
                    "Teams management",
                    "Organize collaboration groups and monitor membership counts.",
                    icon="solar:users-group-two-rounded-bold-duotone",
                ),
                stats,
                dmc.Space(h="md"),
                toolbar,
                table,
            ]
        )
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
