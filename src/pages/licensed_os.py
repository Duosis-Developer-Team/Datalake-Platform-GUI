"""Lisanslı OS Tespiti — detected licensed-OS distribution + CRM reconciliation (TASK-81)."""
from __future__ import annotations

from typing import Any

import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dcc, html

from src.services import api_client as api

_PATH = "/licensed-os"
_LICENSED = [("rhel", "RHEL", "red"), ("suse", "SUSE", "green"),
             ("windows", "Windows", "blue")]


def build_layout_shell(visible_sections=None) -> html.Div:
    return html.Div([
        dcc.Store(id="licensed-os-visible-sections",
                  data=list(visible_sections) if visible_sections else None),
        dcc.Loading(
            id="licensed-os-content-loading", type="circle", color="#4318FF",
            delay_show=150,
            children=html.Div(id="licensed-os-page-root",
                              style={"minHeight": "60vh", "padding": "0 8px"}),
        ),
    ])


def _stat_card(label: str, value: int, color: str) -> Any:
    return dmc.Card(
        dmc.Group([
            dmc.Text(label, size="sm", c="dimmed"),
            dmc.Text(f"{value:,}", fw=700, size="xl", c=color),
        ], justify="space-between"),
        withBorder=True, padding="md", radius="md",
    )


def build_layout(visible_sections=None) -> html.Div:  # noqa: ARG001 - sig parity
    summary = api.get_licensed_os_summary()
    fam = summary.get("families") or {}
    cards = [_stat_card(lbl, int(fam.get(key, 0)), color) for key, lbl, color in _LICENSED]
    cards.append(_stat_card("Ücretsiz", int(fam.get("free", 0)), "gray"))
    cards.append(_stat_card("Bilinmiyor", int(fam.get("unknown", 0)), "orange"))

    unknown = summary.get("unknown_samples") or []
    unknown_block = dmc.Card(
        [
            dmc.Text("Manuel inceleme gerektiren (bilinmiyor)", fw=600, mb="xs"),
            dmc.Stack(
                [dmc.Text(f"• {s}", size="sm") for s in unknown],
                gap=4,
            ) if unknown
            else dmc.Text("Yok", c="dimmed", size="sm"),
        ],
        withBorder=True, padding="md", radius="md", mt="md",
    )

    return html.Div([
        dmc.Title("Lisanslı OS Tespiti", order=2, mb="md"),
        dmc.SimpleGrid(cards, cols=5, spacing="md"),
        unknown_block,
    ])


@callback(
    Output("licensed-os-page-root", "children"),
    Input("url", "pathname"),
    Input("app-time-range", "data"),
    State("licensed-os-visible-sections", "data"),
)
def _fill_licensed_os_content(pathname, time_range, visible_sections):
    if pathname != _PATH:
        return dash.no_update
    return build_layout(visible_sections=visible_sections)
