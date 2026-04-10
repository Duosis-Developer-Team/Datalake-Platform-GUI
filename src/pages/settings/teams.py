"""Team management."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import dcc, html

from src.auth import settings_crud


def build_layout() -> html.Div:
    teams = settings_crud.list_teams()
    rows = [
        html.Tr(
            [
                html.Td(str(t["id"])),
                html.Td(str(t["name"])),
                html.Td(str(t.get("member_count", 0))),
            ]
        )
        for t in teams
    ]

    return html.Div(
        [
            dmc.Title("Teams", order=3, mb="sm", c="#2B3674"),
            html.Form(
                method="POST",
                action="/auth/settings/team-create",
                style={"padding": "16px", "border": "1px solid #E9ECEF", "borderRadius": "12px", "marginBottom": "16px"},
                children=[
                    dmc.Text("Create team", fw=600, mb="sm", size="sm"),
                    dcc.Input(
                        name="name",
                        placeholder="Team name",
                        required=True,
                        style={"width": "280px", "padding": "8px", "marginRight": "8px"},
                    ),
                    html.Button("Create", type="submit"),
                ],
            ),
            html.Table(
                [html.Tr([html.Th("ID"), html.Th("Name"), html.Th("Members")]), *rows],
                style={"width": "100%", "fontSize": "13px"},
            ),
        ]
    )
