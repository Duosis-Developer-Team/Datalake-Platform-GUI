"""Audit log viewer."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import html

from src.auth import settings_crud


def build_layout() -> html.Div:
    logs = settings_crud.list_audit_log(250)
    rows = [
        html.Tr(
            [
                html.Td(str(x.get("created_at", ""))[:19]),
                html.Td(str(x.get("username") or x.get("user_id") or "")),
                html.Td(str(x.get("action", ""))),
                html.Td(str(x.get("detail") or "")[:120]),
                html.Td(str(x.get("ip_address") or "")),
            ]
        )
        for x in logs
    ]

    return html.Div(
        [
            dmc.Title("Audit log", order=3, mb="sm", c="#2B3674"),
            dmc.Text("Recent authentication and admin actions.", size="sm", c="dimmed", mb="md"),
            html.Div(
                style={"overflowX": "auto"},
                children=[
                    html.Table(
                        [
                            html.Tr(
                                [
                                    html.Th("Time"),
                                    html.Th("User"),
                                    html.Th("Action"),
                                    html.Th("Detail"),
                                    html.Th("IP"),
                                ]
                            ),
                            *rows,
                        ],
                        style={"width": "100%", "fontSize": "12px", "borderCollapse": "collapse"},
                    )
                ],
            ),
        ]
    )
