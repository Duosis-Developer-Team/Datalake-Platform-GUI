"""Licensed OS detection — detected licensed-OS distribution + CRM reconciliation (TASK-81)."""
from __future__ import annotations

from typing import Any

import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dcc, html

from shared.licensing.reconcile import reconcile
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


def _reconcile_header() -> html.Thead:
    return html.Thead(html.Tr([
        html.Th("Customer"), html.Th("OS"), html.Th("Detected"),
        html.Th("Sold"), html.Th("Delta"),
    ]))


def _reconcile_row(customer: str, row: dict) -> html.Tr:
    delta = int(row.get("delta", 0))
    delta_cell = dmc.Text(f"{delta:+,}", fw=700, c="red" if delta > 0 else "dimmed")
    return html.Tr([
        html.Td(customer),
        html.Td(row.get("label")),
        html.Td(f"{int(row.get('detected', 0)):,}"),
        html.Td(f"{int(row.get('sold', 0)):,}"),
        html.Td(delta_cell),
    ])


def _reconcile_table(customer: str, rows: list[dict]) -> Any:
    body = (
        [_reconcile_row(customer, r) for r in rows]
        if rows
        else [html.Tr([html.Td("No data", colSpan=5)])]
    )
    return dmc.Card(
        [
            dmc.Text("Detected vs. sold reconciliation", fw=600, mb="xs"),
            dmc.Table(
                striped=True, highlightOnHover=True, withColumnBorders=True,
                children=[_reconcile_header(), html.Tbody(body)],
            ),
        ],
        withBorder=True, padding="md", radius="md", mt="md",
    )


def _no_data_banner() -> Any:
    """Shown when the selected period has no detected OS at all, so an honest
    'nothing here yet' reads instead of a wall of zero cards."""
    return dmc.Alert(
        "No licensed OS was detected in the selected period. Pick a wider range, "
        "or one that overlaps the latest inventory collection.",
        title="Nothing to show for this period",
        color="gray",
        variant="light",
        mt="md",
    )


def build_layout(visible_sections=None, tr=None) -> html.Div:  # noqa: ARG001 - visible_sections kept for sig parity
    summary = api.get_licensed_os_summary(tr=tr)
    fam = summary.get("families") or {}
    total_detected = sum(int(fam.get(k, 0)) for k in ("rhel", "suse", "windows", "free", "unknown"))

    cards = [_stat_card(lbl, int(fam.get(key, 0)), color) for key, lbl, color in _LICENSED]
    cards.append(_stat_card("Free", int(fam.get("free", 0)), "gray"))
    cards.append(_stat_card("Unknown", int(fam.get("unknown", 0)), "orange"))

    unknown = summary.get("unknown_samples") or []
    unknown_block = dmc.Card(
        [
            dmc.Text("Needs manual review (unknown)", fw=600, mb="xs"),
            dmc.Stack(
                [dmc.Text(f"• {s}", size="sm") for s in unknown],
                gap=4,
            ) if unknown
            else dmc.Text("None", c="dimmed", size="sm"),
        ],
        withBorder=True, padding="md", radius="md", mt="md",
    )

    customers = api.get_customer_list() or []
    customer_select = dmc.Select(
        id="licensed-os-customer-select",
        label="Select a customer to reconcile",
        placeholder="Select a customer",
        data=[{"value": c, "label": c} for c in customers],
        value=None,
        clearable=True,
        searchable=True,
        nothingFoundMessage="No customer found",
        style={"maxWidth": "360px"},
        mt="lg",
    )

    return html.Div([
        dmc.Title("Licensed OS detection", order=2, mb="md"),
        dmc.SimpleGrid(cards, cols=5, spacing="md"),
        _no_data_banner() if total_detected == 0 else None,
        unknown_block,
        customer_select,
        html.Div(id="licensed-os-reconcile-container"),
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
    return build_layout(visible_sections=visible_sections, tr=time_range)


@callback(
    Output("licensed-os-reconcile-container", "children"),
    Input("licensed-os-customer-select", "value"),
    State("app-time-range", "data"),
)
def _fill_licensed_os_reconciliation(name, time_range):
    if not name:
        return dash.no_update
    summary = api.get_licensed_os_summary(customer=name, tr=time_range)
    detected = summary.get("families") or {}
    sold_rows = api.get_customer_efficiency_by_category(name, time_range)
    rows = reconcile(detected, sold_rows)
    return _reconcile_table(name, rows)
