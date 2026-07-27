"""One-click alias action for Eşleşmeyen Veriler.

The cell IS the button: dash_table.DataTable cannot host a component, and
replacing the table with html.Table would cost the native column filtering and
sorting the page advertises. So the action column renders text and the click
arrives as active_cell.
"""
from __future__ import annotations

import logging

import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, callback, ctx, no_update
from dash.exceptions import PreventUpdate

from src.pages import unmapped_resources as page
from src.services import api_client as api
from src.utils.crm_source_mapping_ui import find_alias, merge_source_mapping

logger = logging.getLogger(__name__)

_STATUS_COLOR = {"saved": "teal", "exists": "blue", "warning": "yellow", "error": "red"}


def apply_alias_suggestion(row: dict) -> tuple[str, str]:
    """Write the suggested alias rule for one unmapped row.

    Returns (status, message) where status is saved | exists | warning | error.
    Never raises: this runs from a click handler, and a traceback there takes
    the whole page down rather than the one action that failed.
    """
    account_id = str(row.get("guessed_owner_id") or "").strip()
    alias_value = str(row.get("suggested_alias") or "").strip()
    method = str(row.get("suggested_method") or "prefix").strip()
    data_source = "backup_netbackup" if row.get("kind") == "backup" else "virtualization"

    if not account_id or not alias_value:
        return "error", "Bu satır için bağlanacak müşteri tahmini yok."

    entry = {
        "data_source": data_source,
        "match_method": method,
        "match_value": alias_value,
        "enabled": True,
        "priority": 100,
        "notes": "Eşleşmeyen Veriler ekranından tek tıkla eklendi.",
    }

    try:
        alias = find_alias(api.get_crm_aliases() or [], account_id)
        existing = list((alias or {}).get("source_mappings") or [])
        # The save endpoint replaces every mapping this account has, so the
        # union has to go out; sending the bare new rule would delete the rest.
        merged, needs_write = merge_source_mapping(existing, entry)
        if not needs_write:
            return "exists", f"‘{alias_value}’ kuralı bu müşteride zaten ekli."

        _, cache_warning = api.put_crm_source_mappings(
            account_id,
            crm_account_name=(alias or {}).get("crm_account_name") or row.get("guessed_owner"),
            mappings=merged,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("alias suggestion failed account=%s value=%s", account_id, alias_value)
        return "error", f"Kaydedilemedi: {exc}"

    if cache_warning:
        # The DB write committed before the cache drop was attempted, so this
        # is a warning about staleness, not a failed save.
        return "warning", f"Kaydedildi, ancak önbellek temizlenemedi: {cache_warning}"
    return "saved", f"‘{alias_value}’ kuralı {row.get('guessed_owner')} müşterisine eklendi."


def _notification(status: str, message: str) -> dmc.Alert:
    return dmc.Alert(
        message,
        color=_STATUS_COLOR.get(status, "gray"),
        variant="light",
        withCloseButton=True,
        mb="md",
    )


@callback(
    Output(page.BODY_ID, "children"),
    Output(page.TOAST_ID, "children"),
    Input({"type": "unmapped-table", "kind": ALL}, "active_cell"),
    State({"type": "unmapped-table", "kind": ALL}, "derived_viewport_data"),
    State({"type": "unmapped-table", "kind": ALL}, "id"),
    State(page.STORE_ID, "data"),
    prevent_initial_call=True,
)
def _on_action_cell(active_cells, viewport_data, table_ids, store):
    if not ctx.triggered_id:
        raise PreventUpdate

    # Resolve which table fired by id, not by scanning for the first active
    # cell in the action column: once the operator has clicked an action in
    # both tabs, both tables hold a stale active_cell there and a scan would
    # keep re-firing the first one.
    triggered_index = None
    for i, table_id_ in enumerate(table_ids or []):
        if table_id_ == ctx.triggered_id:
            triggered_index = i
            break
    if triggered_index is None:
        raise PreventUpdate

    cell = (active_cells or [])[triggered_index]
    if not cell or cell.get("column_id") != "action":
        raise PreventUpdate

    rows = (viewport_data or [])[triggered_index] or []
    row_index = cell.get("row")
    if row_index is None or row_index >= len(rows):
        raise PreventUpdate

    row_key = rows[row_index].get("row_key")
    payload_row = page.find_payload_row(store or {}, row_key)
    if not payload_row:
        raise PreventUpdate

    status, message = apply_alias_suggestion(payload_row)
    if status in ("error", "exists"):
        # Nothing changed on the server, so re-rendering the body would only
        # cost a refetch and lose the operator's sort/filter state.
        return no_update, _notification(status, message)

    return page.build_body(store.get("time_range")), _notification(status, message)
