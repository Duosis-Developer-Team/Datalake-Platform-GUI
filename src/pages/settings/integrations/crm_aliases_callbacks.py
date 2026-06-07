"""Dash callbacks for CRM customer source mappings (slide-in panel)."""
from __future__ import annotations

import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, callback, ctx, no_update
from dash.exceptions import PreventUpdate

from src.pages.settings.integrations.crm_aliases import (
    TABLE_PAGE_SIZE,
    build_editor_shell,
    build_table_body_rows,
    section_refresh_outputs,
    visible_table_rows,
)
from src.services import api_client as api
from src.utils.crm_source_mapping_ui import (
    UI_COLUMNS,
    add_mapping_row,
    alias_from_table_selection,
    aliases_to_table_rows,
    build_editor_state,
    editor_state_from_dash_states,
    editor_state_to_save_payload,
    filter_alias_table_rows,
    find_alias,
    merge_alias_after_save,
    remove_mapping_row,
)


def _panel_store(open_state: bool, account_id: str | None) -> dict:
    return {"open": bool(open_state), "crm_accountid": account_id}


def _merge_editor_from_form_states(
    editor_state: dict | None,
    *,
    method_states: list,
    value_states: list,
    enabled_states: list,
    source_states: list,
    notes: str | None,
) -> dict | None:
    """Capture live form values before structural editor changes (add/remove row)."""
    if not editor_state:
        return None
    return editor_state_from_dash_states(
        editor_state,
        method_states=method_states,
        value_states=value_states,
        enabled_states=enabled_states,
        source_states=source_states,
        notes=notes,
    )


def _editor_for_account(page_data: list[dict], account_id: str) -> tuple[dict | None, dict | None]:
    alias = find_alias(page_data or [], account_id)
    if not alias:
        alias = alias_from_table_selection(
            {"crm_accountid": account_id, "crm_account_name": account_id},
            page_data or [],
        )
    editor = build_editor_state(alias)
    return alias, editor


def _table_refresh_outputs(page_data: list[dict], query: str, page: int):
    rows, pages = visible_table_rows(page_data or [], query or "", page)
    safe_page = min(max(int(page or 0), 0), pages - 1)
    rows, pages = visible_table_rows(page_data or [], query or "", safe_page)
    start = safe_page * TABLE_PAGE_SIZE
    end = start + len(rows)
    filtered = filter_alias_table_rows(aliases_to_table_rows(page_data or []), query or "")
    filtered_total = len(filtered)
    label = (
        f"Showing {start + 1}-{min(end, filtered_total)} of {filtered_total}"
        if filtered_total
        else "No matches"
    )
    return (
        build_table_body_rows(rows),
        pages,
        safe_page + 1,
        safe_page,
        f"{filtered_total} customer(s)",
        label,
    )


@callback(
    Output("alias-slide-panel", "className"),
    Input("alias-panel-store", "data"),
)
def sync_alias_panel_class(store):
    if store and store.get("open"):
        return "alias-slide-panel open"
    return "alias-slide-panel closed"


@callback(
    Output("alias-panel-store", "data"),
    Output("alias-panel-title", "children"),
    Output("alias-panel-subtitle", "children"),
    Output("alias-editor-state", "data"),
    Output("alias-editor-panel", "children"),
    Output("alias-editor-open-sections", "data"),
    Input({"type": "alias-edit-open", "account": ALL}, "n_clicks"),
    State("alias-page-data", "data"),
    prevent_initial_call=True,
)
def open_alias_editor_panel(_clicks, page_data):
    trig = ctx.triggered_id
    if not isinstance(trig, dict) or trig.get("type") != "alias-edit-open":
        raise PreventUpdate
    if not ctx.triggered or not ctx.triggered[0].get("value"):
        raise PreventUpdate
    account_id = str(trig.get("account") or "")
    if not account_id:
        raise PreventUpdate
    alias, editor = _editor_for_account(page_data or [], account_id)
    if not editor:
        raise PreventUpdate
    name = str(alias.get("crm_account_name") if alias else account_id)
    open_sections = [UI_COLUMNS[0][0]]
    return (
        _panel_store(True, account_id),
        f"Edit mappings — {name}",
        account_id,
        editor,
        build_editor_shell(editor, open_sections=open_sections),
        open_sections,
    )


@callback(
    Output("alias-panel-store", "data", allow_duplicate=True),
    Input("alias-panel-close", "n_clicks"),
    prevent_initial_call=True,
)
def close_alias_editor_panel(_n_clicks):
    return _panel_store(False, None)


@callback(
    Output("alias-table-body", "children"),
    Output("alias-table-pagination", "total"),
    Output("alias-table-pagination", "value"),
    Output("alias-table-page", "data"),
    Output("alias-table-count", "children"),
    Output("alias-table-page-label", "children"),
    Input("alias-table-search", "value"),
    Input("alias-table-pagination", "value"),
    Input("alias-page-data", "data"),
    prevent_initial_call=False,
)
def refresh_alias_table(query, page_value, page_data):
    page = max(int(page_value or 1) - 1, 0)
    trig = ctx.triggered_id
    if trig == "alias-table-search":
        page = 0
    return _table_refresh_outputs(page_data or [], query or "", page)


@callback(
    Output({"type": "alias-section-rows", "section": ALL}, "children"),
    Output({"type": "alias-section-count", "section": ALL}, "children"),
    Input("alias-editor-state", "data"),
    prevent_initial_call=True,
)
def refresh_editor_sections(editor_state):
    if not isinstance(editor_state, dict):
        raise PreventUpdate
    return section_refresh_outputs(editor_state)


@callback(
    Output("alias-editor-open-sections", "data", allow_duplicate=True),
    Input("alias-editor-accordion", "value"),
    prevent_initial_call=True,
)
def persist_editor_accordion_open(value):
    if isinstance(value, list) and value:
        return value
    return [UI_COLUMNS[0][0]]


@callback(
    Output("alias-editor-state", "data", allow_duplicate=True),
    Input({"type": "alias-edit-add", "section": ALL}, "n_clicks"),
    State({"type": "alias-edit-method", "section": ALL, "index": ALL}, "value"),
    State({"type": "alias-edit-value", "section": ALL, "index": ALL}, "value"),
    State({"type": "alias-edit-enabled", "section": ALL, "index": ALL}, "checked"),
    State({"type": "alias-edit-source", "section": ALL, "index": ALL}, "value"),
    State("alias-edit-notes", "value"),
    State("alias-editor-state", "data"),
    prevent_initial_call=True,
)
def add_mapping_row_cb(
    _n_clicks,
    _methods,
    _values,
    _enabled,
    _sources,
    notes,
    editor_state,
):
    trig = ctx.triggered_id
    if not isinstance(trig, dict) or trig.get("type") != "alias-edit-add":
        return no_update
    if not ctx.triggered or not ctx.triggered[0].get("value"):
        return no_update
    section = str(trig.get("section") or "")
    synced = _merge_editor_from_form_states(
        editor_state,
        method_states=ctx.states_list[0] if ctx.states_list else [],
        value_states=ctx.states_list[1] if len(ctx.states_list) > 1 else [],
        enabled_states=ctx.states_list[2] if len(ctx.states_list) > 2 else [],
        source_states=ctx.states_list[3] if len(ctx.states_list) > 3 else [],
        notes=notes,
    )
    updated = add_mapping_row(synced, section)
    if updated is None:
        return no_update
    return updated


@callback(
    Output("alias-editor-state", "data", allow_duplicate=True),
    Input({"type": "alias-edit-remove", "section": ALL, "index": ALL}, "n_clicks"),
    State({"type": "alias-edit-method", "section": ALL, "index": ALL}, "value"),
    State({"type": "alias-edit-value", "section": ALL, "index": ALL}, "value"),
    State({"type": "alias-edit-enabled", "section": ALL, "index": ALL}, "checked"),
    State({"type": "alias-edit-source", "section": ALL, "index": ALL}, "value"),
    State("alias-edit-notes", "value"),
    State("alias-editor-state", "data"),
    prevent_initial_call=True,
)
def remove_mapping_row_cb(
    _n_clicks,
    _methods,
    _values,
    _enabled,
    _sources,
    notes,
    editor_state,
):
    trig = ctx.triggered_id
    if not isinstance(trig, dict) or trig.get("type") != "alias-edit-remove":
        return no_update
    if not ctx.triggered or not ctx.triggered[0].get("value"):
        return no_update
    section = str(trig.get("section") or "")
    index = int(trig.get("index", 0))
    synced = _merge_editor_from_form_states(
        editor_state,
        method_states=ctx.states_list[0] if ctx.states_list else [],
        value_states=ctx.states_list[1] if len(ctx.states_list) > 1 else [],
        enabled_states=ctx.states_list[2] if len(ctx.states_list) > 2 else [],
        source_states=ctx.states_list[3] if len(ctx.states_list) > 3 else [],
        notes=notes,
    )
    updated = remove_mapping_row(synced, section, index)
    if updated is None:
        return no_update
    return updated


@callback(
    Output("alias-editor-state", "data", allow_duplicate=True),
    Output("alias-editor-panel", "children", allow_duplicate=True),
    Input("alias-edit-reset", "n_clicks"),
    State("alias-page-data", "data"),
    State("alias-editor-state", "data"),
    State("alias-editor-open-sections", "data"),
    prevent_initial_call=True,
)
def reset_editor_cb(_n_clicks, page_data, editor_state, open_sections):
    if not editor_state:
        return no_update, no_update
    account_id = str(editor_state.get("crm_accountid") or "")
    _, refreshed = _editor_for_account(page_data or [], account_id)
    if not refreshed:
        return no_update, no_update
    sections = open_sections if isinstance(open_sections, list) else [UI_COLUMNS[0][0]]
    return refreshed, build_editor_shell(refreshed, open_sections=sections)


@callback(
    Output("alias-feedback", "children"),
    Output("alias-page-data", "data"),
    Output("alias-table-body", "children", allow_duplicate=True),
    Output("alias-table-pagination", "total", allow_duplicate=True),
    Output("alias-table-pagination", "value", allow_duplicate=True),
    Output("alias-table-page", "data", allow_duplicate=True),
    Output("alias-table-count", "children", allow_duplicate=True),
    Output("alias-table-page-label", "children", allow_duplicate=True),
    Output("alias-panel-store", "data", allow_duplicate=True),
    Output("alias-panel-title", "children", allow_duplicate=True),
    Output("alias-panel-subtitle", "children", allow_duplicate=True),
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
    State("alias-table-search", "value"),
    State("alias-table-page", "data"),
    State("alias-editor-open-sections", "data"),
    prevent_initial_call=True,
)
def save_editor_mappings_cb(
    _n_clicks,
    _methods,
    _values,
    _enabled_flags,
    _sources,
    notes,
    editor_state,
    page_data,
    query,
    page_index,
    open_sections,
):
    if not editor_state:
        return (dmc.Alert(color="yellow", title="Select a customer first."),) + (no_update,) * 11

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
        refreshed_editor = build_editor_state(find_alias(updated_page, account_id))
        table_out = _table_refresh_outputs(updated_page, query or "", int(page_index or 0))
        sections = open_sections if isinstance(open_sections, list) else [UI_COLUMNS[0][0]]
        return (
            dmc.Alert(color="green", title="Saved", children=f"Mappings updated for {account_name}."),
            updated_page,
            *table_out,
            _panel_store(True, account_id),
            f"Edit mappings — {account_name}",
            account_id,
            refreshed_editor,
            build_editor_shell(refreshed_editor, open_sections=sections),
        )
    except Exception as exc:  # noqa: BLE001
        return (dmc.Alert(color="red", title="Save failed", children=str(exc)),) + (no_update,) * 11


@callback(
    Output("alias-feedback", "children", allow_duplicate=True),
    Output("alias-page-data", "data", allow_duplicate=True),
    Output("alias-table-body", "children", allow_duplicate=True),
    Output("alias-table-pagination", "total", allow_duplicate=True),
    Output("alias-table-pagination", "value", allow_duplicate=True),
    Output("alias-table-page", "data", allow_duplicate=True),
    Output("alias-table-count", "children", allow_duplicate=True),
    Output("alias-table-page-label", "children", allow_duplicate=True),
    Output("alias-panel-store", "data", allow_duplicate=True),
    Output("alias-panel-title", "children", allow_duplicate=True),
    Output("alias-panel-subtitle", "children", allow_duplicate=True),
    Output("alias-editor-state", "data", allow_duplicate=True),
    Output("alias-editor-panel", "children", allow_duplicate=True),
    Input("alias-seed-boyner-btn", "n_clicks"),
    State("alias-table-search", "value"),
    prevent_initial_call=True,
)
def seed_boyner_cb(_n_clicks, query):
    try:
        result = api.seed_boyner_source_mappings()
        aliases = api.get_crm_aliases()
        rows_upserted = result.get("rows_upserted", 0)
        boyner_id = str(result.get("crm_accountid") or "")
        alias, editor = _editor_for_account(aliases, boyner_id) if boyner_id else (None, None)
        table_out = _table_refresh_outputs(aliases, query or "", 0)
        name = str(alias.get("crm_account_name") if alias else "Boyner")
        open_sections = [UI_COLUMNS[0][0]]
        return (
            dmc.Alert(color="green", title=f"Boyner seed applied ({rows_upserted} rows)"),
            aliases,
            *table_out,
            _panel_store(True, boyner_id) if boyner_id else _panel_store(False, None),
            f"Edit mappings — {name}" if boyner_id else "Edit mappings",
            boyner_id if boyner_id else "",
            editor,
            build_editor_shell(editor, open_sections=open_sections) if editor else build_editor_shell(None),
        )
    except Exception as exc:  # noqa: BLE001
        return (dmc.Alert(color="red", title="Seed failed", children=str(exc)),) + (no_update,) * 11
