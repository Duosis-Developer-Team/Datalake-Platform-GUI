"""Integrations — CRM customer source mappings (gui_crm_customer_source_mapping).

Lightweight DataTable list + focused detail editor for one customer at a time.
"""
from __future__ import annotations

import dash
from dash import Input, Output, State, ALL, callback, ctx, dash_table, dcc, html, no_update
import dash_mantine_components as dmc
from dash_iconify import DashIconify

from src.services import api_client as api
from src.utils.crm_source_mapping_ui import (
    MATCH_METHOD_OPTIONS,
    UI_COLUMNS,
    add_mapping_row,
    aliases_to_table_rows,
    alias_from_table_selection,
    build_editor_state,
    compute_summary,
    editor_state_from_dash_states,
    editor_state_from_form_inputs,
    editor_state_to_save_payload,
    find_alias,
    merge_alias_after_save,
    remove_mapping_row,
    resolve_visible_row_index,
    resolve_visible_rows,
)

_TABLE_ID = "alias-customer-table"
_STATUS_COLORS = {
    "configured": "teal",
    "seed": "blue",
    "empty": "gray",
}


def _summary_strip(aliases: list[dict]) -> dmc.Group:
    stats = compute_summary(aliases)
    return dmc.Group(
        gap="xs",
        mb="md",
        children=[
            dmc.Badge(f"Total: {stats['total']}", color="indigo", variant="light", size="lg"),
            dmc.Badge(f"Configured: {stats['configured']}", color="teal", variant="light", size="lg"),
            dmc.Badge(f"Empty: {stats['empty']}", color="gray", variant="light", size="lg"),
            dmc.Badge(
                f"Boyner mappings: {stats['boyner_mappings']}",
                color="blue" if stats["boyner_mappings"] else "gray",
                variant="light",
                size="lg",
            ),
        ],
    )


def _table_style_conditional() -> list[dict]:
    styles = [
        {
            "if": {"state": "selected"},
            "backgroundColor": "rgba(67,24,255,0.08)",
            "border": "1px solid #4318FF",
        },
        {
            "if": {"filter_query": "{status} = 'empty'", "column_id": "status"},
            "color": "#868E96",
        },
        {
            "if": {"filter_query": "{status} = 'configured'", "column_id": "status"},
            "color": "#0CA678",
            "fontWeight": "600",
        },
        {
            "if": {"filter_query": "{status} = 'seed'", "column_id": "status"},
            "color": "#1971C2",
            "fontWeight": "600",
        },
    ]
    return styles


def _render_mapping_entry(section_key: str, data_sources: tuple[str, ...], entry: dict, index: int):
    source_options = [{"label": s, "value": s} for s in data_sources]
    return dmc.Paper(
        withBorder=True,
        p="xs",
        mb="xs",
        children=[
            dmc.Group(
                gap="xs",
                wrap="wrap",
                align="flex-end",
                children=[
                    dmc.Select(
                        id={"type": "alias-edit-method", "section": section_key, "index": index},
                        label="Method" if index == 0 else None,
                        data=MATCH_METHOD_OPTIONS,
                        value=entry.get("match_method") or "contains",
                        size="xs",
                        style={"minWidth": "120px", "flex": 1},
                    ),
                    dmc.TextInput(
                        id={"type": "alias-edit-value", "section": section_key, "index": index},
                        label="Value" if index == 0 else None,
                        value=entry.get("match_value") or "",
                        placeholder="match value",
                        size="xs",
                        style={"minWidth": "160px", "flex": 2},
                    ),
                    dmc.Select(
                        id={"type": "alias-edit-source", "section": section_key, "index": index},
                        label="Source" if index == 0 else None,
                        data=source_options,
                        value=entry.get("data_source") or data_sources[0],
                        size="xs",
                        style={"minWidth": "140px", "flex": 1},
                    ),
                    dmc.Switch(
                        id={"type": "alias-edit-enabled", "section": section_key, "index": index},
                        label="On",
                        checked=bool(entry.get("enabled", True)),
                        size="xs",
                    ),
                    dmc.ActionIcon(
                        DashIconify(icon="tabler:trash", width=16),
                        id={"type": "alias-edit-remove", "section": section_key, "index": index},
                        color="red",
                        variant="light",
                        size="sm",
                    ),
                ],
            ),
        ],
    )


def _render_editor_panel(editor_state: dict | None) -> html.Div:
    if not editor_state:
        return html.Div(
            children=dmc.Alert(
                color="blue",
                title="Select a customer",
                children="Choose a row in the table below to edit source mappings for that CRM account.",
            )
        )

    account_name = editor_state.get("crm_account_name") or editor_state.get("crm_accountid")
    sections = editor_state.get("sections") or {}

    accordion_items = []
    for column_key, label, data_sources in UI_COLUMNS:
        entries = sections.get(column_key) or []
        body = [
            *[_render_mapping_entry(column_key, data_sources, entry, idx) for idx, entry in enumerate(entries)],
            dmc.Button(
                "Add mapping",
                id={"type": "alias-edit-add", "section": column_key},
                size="xs",
                variant="light",
                color="gray",
                mt="xs",
            ),
        ]
        accordion_items.append(
            dmc.AccordionItem(
                value=column_key,
                children=[
                    dmc.AccordionControl(
                        dmc.Group(
                            gap="xs",
                            children=[
                                dmc.Text(label, fw=600, size="sm"),
                                dmc.Badge(
                                    str(len([e for e in entries if str(e.get("match_value") or "").strip()])),
                                    color="gray",
                                    size="sm",
                                ),
                            ],
                        )
                    ),
                    dmc.AccordionPanel(dmc.Stack(gap="xs", children=body)),
                ],
            )
        )

    return html.Div(
        children=[
            dmc.Group(
                justify="space-between",
                mb="sm",
                children=[
                    dmc.Stack(
                        gap=0,
                        children=[
                            dmc.Title(order=5, children=f"Edit: {account_name}"),
                            dmc.Text(
                                str(editor_state.get("crm_accountid") or ""),
                                size="xs",
                                c="dimmed",
                            ),
                        ],
                    ),
                    dmc.Group(
                        gap="xs",
                        children=[
                            dmc.Button("Reset", id="alias-edit-reset", size="xs", variant="subtle", color="gray"),
                            dmc.Button("Save mappings", id="alias-edit-save", size="xs", color="indigo"),
                        ],
                    ),
                ],
            ),
            dmc.TextInput(
                id="alias-edit-notes",
                label="Notes",
                value=editor_state.get("notes") or "",
                size="xs",
                mb="md",
                placeholder="Optional operator notes",
            ),
            dmc.Accordion(
                multiple=True,
                defaultValue=[UI_COLUMNS[0][0]],
                children=accordion_items,
            ),
        ]
    )


def build_layout(search: str | None = None) -> html.Div:
    aliases = api.get_crm_aliases()
    table_rows = aliases_to_table_rows(aliases)

    if not aliases:
        empty_alert = dmc.Alert(
            color="yellow",
            title="No CRM project customers",
            children="Customer list comes from CRM PRJ-* sales orders. Verify customer-api connectivity.",
        )
    else:
        empty_alert = dmc.Text(
            "Filter and sort using column headers. Click a row or use the checkbox to edit mappings in the panel above.",
            size="sm",
            c="dimmed",
            mb="sm",
        )

    return html.Div(
        style={"padding": "30px"},
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
                                "Browse CRM project customers in the table, then edit one account at a time.",
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
            _summary_strip(aliases),
            html.Div(id="alias-feedback", style={"marginBottom": "12px"}),
            dmc.Paper(
                p="md",
                radius="md",
                withBorder=True,
                mb="md",
                children=html.Div(id="alias-editor-panel", children=_render_editor_panel(None)),
            ),
            empty_alert,
            dash_table.DataTable(
                id=_TABLE_ID,
                data=table_rows,
                columns=[
                    {"name": "CRM Account", "id": "crm_account_name"},
                    {"name": "Account ID", "id": "account_id_short"},
                    {"name": "Mappings", "id": "mapping_count", "type": "numeric"},
                    {"name": "Coverage", "id": "coverage"},
                    {"name": "Status", "id": "status"},
                ],
                row_selectable="single",
                selected_rows=[],
                page_size=25,
                page_action="native",
                filter_action="native",
                sort_action="native",
                sort_mode="multi",
                style_table={"overflowX": "auto"},
                style_cell={
                    "fontSize": "12px",
                    "fontFamily": "Inter, system-ui, sans-serif",
                    "padding": "6px 8px",
                    "textAlign": "left",
                    "whiteSpace": "normal",
                    "height": "auto",
                },
                style_header={
                    "backgroundColor": "#F4F7FE",
                    "color": "#2B3674",
                    "fontWeight": "700",
                    "border": "none",
                },
                style_data_conditional=_table_style_conditional(),
            ),
            dcc.Store(id="alias-page-data", data=aliases),
            dcc.Store(id="alias-editor-state", data=None),
        ],
    )


@callback(
    Output("alias-editor-state", "data"),
    Output("alias-editor-panel", "children"),
    Input(_TABLE_ID, "selected_rows"),
    Input(_TABLE_ID, "active_cell"),
    State(_TABLE_ID, "derived_virtual_data"),
    State(_TABLE_ID, "derived_viewport_data"),
    State(_TABLE_ID, "data"),
    State(_TABLE_ID, "page_current"),
    State(_TABLE_ID, "page_size"),
    State("alias-page-data", "data"),
    prevent_initial_call=True,
)
def _load_selected_customer(
    selected_rows,
    active_cell,
    virtual_data,
    viewport_data,
    table_data,
    page_current,
    page_size,
    page_data,
):
    visible_rows = resolve_visible_rows(
        virtual_data,
        viewport_data,
        table_data,
        page_current,
        page_size,
    )
    row_index = resolve_visible_row_index(
        selected_rows or [],
        active_cell,
        trigger_id=ctx.triggered_id,
        table_id=_TABLE_ID,
    )
    if row_index is None or row_index < 0 or row_index >= len(visible_rows):
        return None, _render_editor_panel(None)
    alias = alias_from_table_selection(visible_rows[row_index], page_data or [])
    editor = build_editor_state(alias)
    if editor is None:
        return None, _render_editor_panel(None)
    return editor, _render_editor_panel(editor)


@callback(
    Output("alias-editor-state", "data", allow_duplicate=True),
    Input({"type": "alias-edit-method", "section": ALL, "index": ALL}, "value"),
    Input({"type": "alias-edit-value", "section": ALL, "index": ALL}, "value"),
    Input({"type": "alias-edit-enabled", "section": ALL, "index": ALL}, "checked"),
    Input({"type": "alias-edit-source", "section": ALL, "index": ALL}, "value"),
    Input("alias-edit-notes", "value"),
    State("alias-editor-state", "data"),
    prevent_initial_call=True,
)
def _sync_editor_inputs(_methods, _values, _enabled, _sources, notes, editor_state):
    if not editor_state:
        return no_update
    trig = ctx.triggered_id
    if trig == "alias-edit-notes":
        return {**editor_state, "notes": str(notes or "")}
    if not isinstance(trig, dict):
        return no_update
    section = str(trig.get("section") or "")
    index = int(trig.get("index", 0))
    trig_type = str(trig.get("type") or "")
    triggered_value = ctx.triggered[0].get("value") if ctx.triggered else None
    kwargs: dict = {}
    if trig_type == "alias-edit-method":
        kwargs["match_method"] = triggered_value
    elif trig_type == "alias-edit-value":
        kwargs["match_value"] = triggered_value
    elif trig_type == "alias-edit-enabled":
        kwargs["enabled"] = bool(triggered_value)
    elif trig_type == "alias-edit-source":
        kwargs["data_source"] = triggered_value
    updated = editor_state_from_form_inputs(editor_state, section=section, index=index, **kwargs)
    return updated if updated is not None else no_update


@callback(
    Output("alias-editor-state", "data", allow_duplicate=True),
    Output("alias-editor-panel", "children", allow_duplicate=True),
    Input({"type": "alias-edit-add", "section": ALL}, "n_clicks"),
    State("alias-editor-state", "data"),
    prevent_initial_call=True,
)
def _add_mapping_row(_n_clicks, editor_state):
    trig = ctx.triggered_id
    if not isinstance(trig, dict) or trig.get("type") != "alias-edit-add":
        return no_update, no_update
    section = str(trig.get("section") or "")
    updated = add_mapping_row(editor_state, section)
    if updated is None:
        return no_update, no_update
    return updated, _render_editor_panel(updated)


@callback(
    Output("alias-editor-state", "data", allow_duplicate=True),
    Output("alias-editor-panel", "children", allow_duplicate=True),
    Input({"type": "alias-edit-remove", "section": ALL, "index": ALL}, "n_clicks"),
    State("alias-editor-state", "data"),
    prevent_initial_call=True,
)
def _remove_mapping_row(_n_clicks, editor_state):
    trig = ctx.triggered_id
    if not isinstance(trig, dict) or trig.get("type") != "alias-edit-remove":
        return no_update, no_update
    section = str(trig.get("section") or "")
    index = int(trig.get("index", 0))
    updated = remove_mapping_row(editor_state, section, index)
    if updated is None:
        return no_update, no_update
    return updated, _render_editor_panel(updated)


@callback(
    Output("alias-editor-state", "data", allow_duplicate=True),
    Output("alias-editor-panel", "children", allow_duplicate=True),
    Input("alias-edit-reset", "n_clicks"),
    State("alias-page-data", "data"),
    State("alias-editor-state", "data"),
    prevent_initial_call=True,
)
def _reset_editor(_n_clicks, page_data, editor_state):
    if not editor_state:
        return no_update, no_update
    account_id = str(editor_state.get("crm_accountid") or "")
    alias = find_alias(page_data or [], account_id)
    refreshed = build_editor_state(alias)
    return refreshed, _render_editor_panel(refreshed)


@callback(
    Output("alias-feedback", "children"),
    Output("alias-page-data", "data"),
    Output(_TABLE_ID, "data"),
    Output("alias-editor-state", "data", allow_duplicate=True),
    Output("alias-editor-panel", "children", allow_duplicate=True),
    Input("alias-edit-save", "n_clicks"),
    State({"type": "alias-edit-method", "section": ALL, "index": ALL}, "value"),
    State({"type": "alias-edit-value", "section": ALL, "index": ALL}, "value"),
    State({"type": "alias-edit-enabled", "section": ALL, "index": ALL}, "checked"),
    State({"type": "alias-edit-source", "section": ALL, "index": ALL}, "value"),
    State("alias-edit-notes", "value"),
    State("alias-editor-state", "data"),
    State("alias-page-data", "data"),
    prevent_initial_call=True,
)
def _save_editor_mappings(
    _n_clicks,
    methods,
    values,
    enabled_flags,
    sources,
    notes,
    editor_state,
    page_data,
):
    if not editor_state:
        return dmc.Alert(color="yellow", title="Select a customer first."), no_update, no_update, no_update, no_update

    account_id = str(editor_state.get("crm_accountid") or "")
    account_name = str(editor_state.get("crm_account_name") or account_id)
    method_states = ctx.states_list[0] if ctx.states_list else []
    value_states = ctx.states_list[1] if len(ctx.states_list) > 1 else []
    enabled_states = ctx.states_list[2] if len(ctx.states_list) > 2 else []
    source_states = ctx.states_list[3] if len(ctx.states_list) > 3 else []

    synced_editor = editor_state_from_dash_states(
        editor_state,
        method_states=method_states,
        value_states=value_states,
        enabled_states=enabled_states,
        source_states=source_states,
        notes=notes,
    )
    mappings, note_text = editor_state_to_save_payload(synced_editor)

    try:
        saved = api.put_crm_source_mappings(
            account_id,
            crm_account_name=account_name,
            mappings=mappings,
            notes=note_text,
        )
        updated_page = merge_alias_after_save(
            page_data or [],
            account_id=account_id,
            saved_mappings=saved or mappings,
            notes=note_text,
        )
        updated_alias = find_alias(updated_page, account_id)
        refreshed_editor = build_editor_state(updated_alias)
        table_rows = aliases_to_table_rows(updated_page)
        return (
            dmc.Alert(color="green", title="Saved", children=f"Mappings updated for {account_name}."),
            updated_page,
            table_rows,
            refreshed_editor,
            _render_editor_panel(refreshed_editor),
        )
    except Exception as exc:  # noqa: BLE001
        return (
            dmc.Alert(color="red", title="Save failed", children=str(exc)),
            no_update,
            no_update,
            no_update,
            no_update,
        )


@callback(
    Output("alias-feedback", "children", allow_duplicate=True),
    Output("alias-page-data", "data", allow_duplicate=True),
    Output(_TABLE_ID, "data", allow_duplicate=True),
    Output("alias-editor-state", "data", allow_duplicate=True),
    Output("alias-editor-panel", "children", allow_duplicate=True),
    Input("alias-seed-boyner-btn", "n_clicks"),
    prevent_initial_call=True,
)
def _seed_boyner(_n_clicks):
    try:
        result = api.seed_boyner_source_mappings()
        aliases = api.get_crm_aliases()
        rows = result.get("rows_upserted", 0)
        boyner_id = str(result.get("crm_accountid") or "")
        boyner_alias = find_alias(aliases, boyner_id) if boyner_id else None
        editor = build_editor_state(boyner_alias) if boyner_alias else None
        return (
            dmc.Alert(color="green", title=f"Boyner seed applied ({rows} rows)"),
            aliases,
            aliases_to_table_rows(aliases),
            editor,
            _render_editor_panel(editor),
        )
    except Exception as exc:  # noqa: BLE001
        return (
            dmc.Alert(color="red", title="Seed failed", children=str(exc)),
            no_update,
            no_update,
            no_update,
            no_update,
        )
