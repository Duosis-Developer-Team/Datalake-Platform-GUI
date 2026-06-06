"""Integrations — CRM customer source mappings (gui_crm_customer_source_mapping)."""

from __future__ import annotations

import dash
from dash import Input, Output, State, ALL, callback, ctx, dcc, html, no_update
import dash_mantine_components as dmc
from dash_iconify import DashIconify

from src.services import api_client as api
from src.utils.crm_source_mapping_ui import (
    MATCH_METHOD_OPTIONS,
    UI_COLUMNS,
    collect_mappings_for_account,
    mappings_for_column,
)


def _mapping_editor(alias: dict, column_key: str, label: str, data_sources: tuple[str, ...]):
    account_id = alias.get("crm_accountid", "")
    entries = mappings_for_column(alias.get("source_mappings") or [], data_sources)
    default_source = data_sources[0]

    if not entries:
        entries = [{"data_source": default_source, "match_method": "contains", "match_value": "", "enabled": True}]

    blocks = []
    for idx, entry in enumerate(entries):
        blocks.append(
            dmc.Paper(
                withBorder=True,
                p="xs",
                mb="xs",
                children=[
                    dmc.Group(
                        gap="xs",
                        wrap="nowrap",
                        children=[
                            dmc.Select(
                                id={
                                    "type": "map-method",
                                    "account": account_id,
                                    "column": column_key,
                                    "index": idx,
                                },
                                data=MATCH_METHOD_OPTIONS,
                                value=entry.get("match_method") or "contains",
                                size="xs",
                                style={"minWidth": "110px"},
                            ),
                            dmc.TextInput(
                                id={
                                    "type": "map-value",
                                    "account": account_id,
                                    "column": column_key,
                                    "index": idx,
                                },
                                value=entry.get("match_value") or "",
                                placeholder="match value",
                                size="xs",
                                style={"minWidth": "120px", "flex": 1},
                            ),
                            dmc.Switch(
                                id={
                                    "type": "map-enabled",
                                    "account": account_id,
                                    "column": column_key,
                                    "index": idx,
                                },
                                checked=bool(entry.get("enabled", True)),
                                size="xs",
                                label="On",
                            ),
                            dmc.ActionIcon(
                                DashIconify(icon="tabler:trash", width=16),
                                id={
                                    "type": "map-delete",
                                    "account": account_id,
                                    "column": column_key,
                                    "index": idx,
                                },
                                color="red",
                                variant="light",
                                size="sm",
                            ),
                        ],
                    ),
                    dmc.Select(
                        id={
                            "type": "map-source",
                            "account": account_id,
                            "column": column_key,
                            "index": idx,
                        },
                        data=[{"label": s, "value": s} for s in data_sources],
                        value=entry.get("data_source") or default_source,
                        size="xs",
                        mt="xs",
                    ),
                ],
            )
        )

    return html.Td(
        [
            html.Div(blocks, id={"type": "map-block-wrap", "account": account_id, "column": column_key}),
            dmc.Button(
                "Add mapping",
                id={"type": "map-add-btn", "account": account_id, "column": column_key},
                size="xs",
                variant="light",
                color="gray",
                mt="xs",
            ),
            dcc.Store(
                id={"type": "map-entry-count", "account": account_id, "column": column_key},
                data=len(entries),
            ),
        ],
        style={"minWidth": "260px", "verticalAlign": "top"},
    )


def _row(alias: dict):
    account_id = alias.get("crm_accountid", "")
    mapping_count = len(alias.get("source_mappings") or [])
    return html.Tr(
        [
            html.Td(
                account_id,
                style={"fontSize": "11px", "color": "#888", "maxWidth": "120px", "overflow": "hidden", "textOverflow": "ellipsis"},
            ),
            html.Td(alias.get("crm_account_name") or "-"),
            *[
                _mapping_editor(alias, column_key, label, data_sources)
                for column_key, label, data_sources in UI_COLUMNS
            ],
            html.Td(
                dmc.TextInput(
                    id={"type": "alias-notes", "index": account_id},
                    value=alias.get("notes") or "",
                    size="xs",
                    placeholder="notes",
                )
            ),
            html.Td(
                dmc.Group(
                    gap="xs",
                    wrap="nowrap",
                    children=[
                        dmc.Badge(str(mapping_count), color="blue" if mapping_count else "gray", size="sm"),
                        dmc.Button(
                            "Save",
                            id={"type": "alias-save-btn", "index": account_id},
                            size="xs",
                            color="indigo",
                            variant="light",
                        ),
                    ],
                )
            ),
        ]
    )


def build_layout(search: str | None = None) -> html.Div:
    aliases = api.get_crm_aliases()
    if not aliases:
        info = dmc.Alert(
            color="yellow",
            title="No CRM project customers",
            children="Customer list comes from CRM PRJ-* sales orders. Verify customer-api connectivity.",
        )
    else:
        info = dmc.Alert(
            color="teal",
            title=f"{len(aliases)} CRM customers",
            children="Configure source mappings per column. Boyner seed values appear after POST /crm/aliases/seed-boyner.",
        )

    headers = [
        html.Th("CRM Account ID"),
        html.Th("CRM Account Name"),
        *[html.Th(label) for _, label, _ in UI_COLUMNS],
        html.Th("Notes"),
        html.Th(""),
    ]

    table = dmc.Table(
        striped=True,
        highlightOnHover=True,
        withTableBorder=True,
        children=[
            html.Thead(html.Tr(headers)),
            html.Tbody([_row(a) for a in aliases] if aliases else [html.Tr([html.Td("No data", colSpan=len(headers))])]),
        ],
    )

    return html.Div(
        children=[
            dmc.Group(
                gap="sm",
                mb="lg",
                children=[
                    dmc.ThemeIcon(
                        size="xl",
                        variant="light",
                        color="teal",
                        radius="md",
                        children=DashIconify(icon="solar:link-circle-bold-duotone", width=28),
                    ),
                    dmc.Stack(
                        gap=0,
                        children=[
                            dmc.Text("Customer source mappings", fw=700, size="xl", c="#2B3674"),
                            dmc.Text(
                                "Map CRM project customers to infra data sources using multi-value match rules.",
                                size="sm",
                                c="#A3AED0",
                            ),
                        ],
                    ),
                    dmc.Button(
                        "Seed Boyner defaults",
                        id="alias-seed-boyner-btn",
                        color="teal",
                        variant="light",
                        ml="auto",
                    ),
                ],
            ),
            info,
            html.Div(id="alias-feedback", style={"marginBottom": "12px"}),
            html.Div(style={"overflowX": "auto"}, children=[table]),
            dcc.Store(id="alias-page-data", data=aliases),
        ]
    )


def _collect_mappings_for_account(
    account_id: str,
    method_states: list,
    value_states: list,
    enabled_states: list,
    source_states: list,
) -> list[dict]:
    return collect_mappings_for_account(
        account_id,
        method_states,
        value_states,
        enabled_states,
        source_states,
    )


@callback(
    Output("alias-feedback", "children"),
    Input({"type": "alias-save-btn", "index": ALL}, "n_clicks"),
    State({"type": "map-method", "account": ALL, "column": ALL, "index": ALL}, "value"),
    State({"type": "map-value", "account": ALL, "column": ALL, "index": ALL}, "value"),
    State({"type": "map-enabled", "account": ALL, "column": ALL, "index": ALL}, "checked"),
    State({"type": "map-source", "account": ALL, "column": ALL, "index": ALL}, "value"),
    State({"type": "alias-notes", "index": ALL}, "value"),
    State("alias-page-data", "data"),
    prevent_initial_call=True,
)
def _save_mappings(_n_clicks, methods, values, enabled_flags, sources, notes_list, page_data):
    trig = ctx.triggered_id
    if not isinstance(trig, dict) or trig.get("type") != "alias-save-btn":
        return no_update

    account_id = str(trig["index"])
    account_name = account_id
    for row in page_data or []:
        if str(row.get("crm_accountid")) == account_id:
            account_name = str(row.get("crm_account_name") or account_id)
            break

    method_states = ctx.states_list[0] if ctx.states_list else []
    value_states = ctx.states_list[1] if len(ctx.states_list) > 1 else []
    enabled_states = ctx.states_list[2] if len(ctx.states_list) > 2 else []
    source_states = ctx.states_list[3] if len(ctx.states_list) > 3 else []
    note_states = ctx.states_list[4] if len(ctx.states_list) > 4 else []

    notes = ""
    for note_state in note_states:
        if str((note_state.get("id") or {}).get("index")) == account_id:
            notes = str(note_state.get("value") or "").strip()
            break

    mappings = _collect_mappings_for_account(
        account_id,
        method_states,
        value_states,
        enabled_states,
        source_states,
    )

    try:
        api.put_crm_source_mappings(
            account_id,
            crm_account_name=account_name,
            mappings=mappings,
            notes=notes or None,
        )
        return dmc.Alert(color="green", title="Saved — refresh page to confirm persisted values.")
    except Exception as exc:  # noqa: BLE001
        return dmc.Alert(color="red", title="Save failed", children=str(exc))


@callback(
    Output("alias-feedback", "children", allow_duplicate=True),
    Input("alias-seed-boyner-btn", "n_clicks"),
    prevent_initial_call=True,
)
def _seed_boyner(_n_clicks):
    try:
        result = api.seed_boyner_source_mappings()
        rows = result.get("rows_upserted", 0)
        return dmc.Alert(color="green", title=f"Boyner seed applied ({rows} rows) — refresh page.")
    except Exception as exc:  # noqa: BLE001
        return dmc.Alert(color="red", title="Seed failed", children=str(exc))
