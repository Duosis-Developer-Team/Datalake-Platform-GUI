"""Dash callbacks for the Internal (Bulutistan) source mappings page.

Single-entity mirror of crm_aliases_callbacks (no table / slide panel). All
component ids use the "internal-alias" prefix so they never collide with the
Customer aliases page. Saves go to the reserved crm_accountid="INTERNAL" via
the shared PUT /crm/aliases/{id}/source-mappings endpoint.
"""
from __future__ import annotations

import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, callback, ctx, no_update
from dash.exceptions import PreventUpdate

from src.pages.settings.integrations.crm_aliases import (
    build_editor_shell,
    section_refresh_outputs,
)
from src.pages.settings.integrations.crm_internal_aliases import (
    INTERNAL_ACCOUNT_ID,
    INTERNAL_ACCOUNT_NAME,
    PREFIX,
    build_internal_content,
)
from src.services import api_client as api
from src.utils.crm_source_mapping_ui import (
    UI_COLUMNS,
    add_mapping_row,
    build_editor_state,
    editor_state_from_dash_states,
    editor_state_to_save_payload,
    remove_mapping_row,
)

_DEFAULT_OPEN = [UI_COLUMNS[0][0]]


def _editor_state_from_alias(alias: dict | None) -> dict | None:
    return build_editor_state(alias)


def _merge_editor_from_form_states(editor_state, *, method_states, value_states, enabled_states, source_states, notes):
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


@callback(
    Output("internal-alias-page-root", "children"),
    Input("url", "pathname"),
)
def load_internal_aliases_page(pathname):
    path = pathname or ""
    if "/integrations/crm/internal-aliases" not in path:
        raise PreventUpdate
    try:
        internal_alias = api.get_crm_internal_alias()
    except Exception:  # noqa: BLE001
        return build_internal_content(None, load_error=True)
    return build_internal_content(internal_alias or None)


@callback(
    Output({"type": f"{PREFIX}-section-rows", "section": ALL}, "children"),
    Output({"type": f"{PREFIX}-section-count", "section": ALL}, "children"),
    Input("internal-alias-editor-state", "data"),
    prevent_initial_call=True,
)
def refresh_editor_sections(editor_state):
    if not isinstance(editor_state, dict):
        raise PreventUpdate
    return section_refresh_outputs(editor_state, prefix=PREFIX)


@callback(
    Output("internal-alias-editor-open-sections", "data", allow_duplicate=True),
    Input(f"{PREFIX}-editor-accordion", "value"),
    prevent_initial_call=True,
)
def persist_editor_accordion_open(value):
    if isinstance(value, list) and value:
        return value
    return _DEFAULT_OPEN


@callback(
    Output("internal-alias-editor-state", "data", allow_duplicate=True),
    Input({"type": f"{PREFIX}-edit-add", "section": ALL}, "n_clicks"),
    State({"type": f"{PREFIX}-edit-method", "section": ALL, "index": ALL}, "value"),
    State({"type": f"{PREFIX}-edit-value", "section": ALL, "index": ALL}, "value"),
    State({"type": f"{PREFIX}-edit-enabled", "section": ALL, "index": ALL}, "checked"),
    State({"type": f"{PREFIX}-edit-source", "section": ALL, "index": ALL}, "value"),
    State(f"{PREFIX}-edit-notes", "value"),
    State("internal-alias-editor-state", "data"),
    prevent_initial_call=True,
)
def add_mapping_row_cb(_n_clicks, _methods, _values, _enabled, _sources, notes, editor_state):
    trig = ctx.triggered_id
    if not isinstance(trig, dict) or trig.get("type") != f"{PREFIX}-edit-add":
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
    Output("internal-alias-editor-state", "data", allow_duplicate=True),
    Input({"type": f"{PREFIX}-edit-remove", "section": ALL, "index": ALL}, "n_clicks"),
    State({"type": f"{PREFIX}-edit-method", "section": ALL, "index": ALL}, "value"),
    State({"type": f"{PREFIX}-edit-value", "section": ALL, "index": ALL}, "value"),
    State({"type": f"{PREFIX}-edit-enabled", "section": ALL, "index": ALL}, "checked"),
    State({"type": f"{PREFIX}-edit-source", "section": ALL, "index": ALL}, "value"),
    State(f"{PREFIX}-edit-notes", "value"),
    State("internal-alias-editor-state", "data"),
    prevent_initial_call=True,
)
def remove_mapping_row_cb(_n_clicks, _methods, _values, _enabled, _sources, notes, editor_state):
    trig = ctx.triggered_id
    if not isinstance(trig, dict) or trig.get("type") != f"{PREFIX}-edit-remove":
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
    Output("internal-alias-editor-state", "data", allow_duplicate=True),
    Output("internal-alias-editor-panel", "children", allow_duplicate=True),
    Input(f"{PREFIX}-edit-reset", "n_clicks"),
    State("internal-alias-editor-open-sections", "data"),
    prevent_initial_call=True,
)
def reset_editor_cb(_n_clicks, open_sections):
    if not _n_clicks:
        return no_update, no_update
    try:
        internal_alias = api.get_crm_internal_alias()
    except Exception:  # noqa: BLE001
        return no_update, no_update
    refreshed = _editor_state_from_alias(internal_alias or None)
    if not refreshed:
        return no_update, no_update
    sections = open_sections if isinstance(open_sections, list) else _DEFAULT_OPEN
    return refreshed, build_editor_shell(refreshed, open_sections=sections, prefix=PREFIX)


@callback(
    Output("internal-alias-feedback", "children"),
    Output("internal-alias-editor-state", "data", allow_duplicate=True),
    Output("internal-alias-editor-panel", "children", allow_duplicate=True),
    Input(f"{PREFIX}-edit-save", "n_clicks"),
    State({"type": f"{PREFIX}-edit-method", "section": ALL, "index": ALL}, "value"),
    State({"type": f"{PREFIX}-edit-value", "section": ALL, "index": ALL}, "value"),
    State({"type": f"{PREFIX}-edit-enabled", "section": ALL, "index": ALL}, "checked"),
    State({"type": f"{PREFIX}-edit-source", "section": ALL, "index": ALL}, "value"),
    State(f"{PREFIX}-edit-notes", "value"),
    State("internal-alias-editor-state", "data"),
    State("internal-alias-editor-open-sections", "data"),
    prevent_initial_call=True,
)
def save_editor_mappings_cb(_n_clicks, _methods, _values, _enabled, _sources, notes, editor_state, open_sections):
    if not editor_state:
        return dmc.Alert(color="yellow", title="Nothing to save."), no_update, no_update

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
        saved, cache_warning = api.put_crm_source_mappings(
            INTERNAL_ACCOUNT_ID,
            crm_account_name=INTERNAL_ACCOUNT_NAME,
            mappings=mappings,
            notes=note_text,
        )
        refreshed_alias = {
            "crm_accountid": INTERNAL_ACCOUNT_ID,
            "crm_account_name": INTERNAL_ACCOUNT_NAME,
            "notes": note_text,
            "source": "internal",
            "source_mappings": saved or mappings,
        }
        refreshed_editor = build_editor_state(refreshed_alias)
        sections = open_sections if isinstance(open_sections, list) else _DEFAULT_OPEN
        if cache_warning:
            # Saved, but the cached views may still show the old mapping.
            save_alert = dmc.Alert(
                color="yellow",
                title="Saved — cache warning",
                children=cache_warning,
            )
        else:
            save_alert = dmc.Alert(
                color="green", title="Saved", children="Internal (Bulutistan) mappings updated."
            )
        return (
            save_alert,
            refreshed_editor,
            build_editor_shell(refreshed_editor, open_sections=sections, prefix=PREFIX),
        )
    except Exception as exc:  # noqa: BLE001
        return dmc.Alert(color="red", title="Save failed", children=str(exc)), no_update, no_update
