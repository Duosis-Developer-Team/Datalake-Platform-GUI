"""Audit log viewer."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import html

from src.services import admin_client as settings_crud
from src.utils.ui_tokens import ON_SURFACE, relative_time, section_header, settings_page_shell


def _action_color(action: str) -> str:
    a = (action or "").lower()
    if "login" in a:
        return "blue"
    if "logout" in a:
        return "gray"
    if "settings" in a or "admin" in a:
        return "violet"
    if "fail" in a or "error" in a:
        return "red"
    return "indigo"


def build_layout(search: str | None = None) -> html.Div:
    logs = settings_crud.list_audit_log(250)
    rows = []
    for x in logs:
        action = str(x.get("action", ""))
        rows.append(
            html.Tr(
                style={"borderBottom": "1px solid #eef1f4"},
                children=[
                    html.Td(
                        dmc.Stack(
                            gap=0,
                            children=[
                                dmc.Text(str(x.get("created_at", ""))[:19], size="sm", fw=500),
                                dmc.Text(relative_time(x.get("created_at")), size="xs", c="dimmed"),
                            ],
                        )
                    ),
                    html.Td(str(x.get("username") or x.get("user_id") or "—")),
                    html.Td(
                        dmc.Badge(
                            action[:48] + ("…" if len(action) > 48 else ""),
                            variant="light",
                            color=_action_color(action),
                            size="sm",
                        )
                    ),
                    html.Td(str(x.get("detail") or "")[:160], style={"fontSize": "13px", "maxWidth": "420px"}),
                    html.Td(str(x.get("ip_address") or "—"), style={"fontSize": "12px"}),
                ],
            )
        )

    table = dmc.Paper(
        p=0,
        radius="md",
        withBorder=True,
        children=[
            html.Div(
                style={"padding": "16px 20px", "borderBottom": "1px solid #eef1f4"},
                children=[
                    dmc.Group(
                        justify="space-between",
                        children=[
                            dmc.Text("Audit log", fw=700, c=ON_SURFACE),
                            dmc.Text("Last 250 records", size="xs", c="dimmed"),
                        ],
                    )
                ],
            ),
            html.Div(
                style={"overflowX": "auto"},
                children=[
                    html.Table(
                        [
                            html.Tr(
                                [
                                    html.Th("Time", style=_th()),
                                    html.Th("User", style=_th()),
                                    html.Th("Action", style=_th()),
                                    html.Th("Detail", style=_th()),
                                    html.Th("IP", style=_th()),
                                ]
                            ),
                            *rows,
                        ],
                        style={"width": "100%", "fontSize": "13px", "borderCollapse": "collapse"},
                    )
                ],
            ),
        ],
    )

    return html.Div(
        settings_page_shell(
            [
                section_header(
                    "Audit log",
                    "Authentication events and administrative changes.",
                    icon="solar:clipboard-list-bold-duotone",
                ),
                table,
            ]
        )
    )


def _th():
    return {"textAlign": "left", "padding": "12px 16px", "borderBottom": "1px solid #e9ecef", "color": "#2B3674", "fontSize": "11px", "textTransform": "uppercase"}
