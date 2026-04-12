"""Dash callbacks for LDAP settings (test connection, mapping role select)."""

from __future__ import annotations

import logging

import dash_mantine_components as dmc
from dash import Input, Output, State, callback
from dash.exceptions import PreventUpdate

from src.services import admin_client as settings_crud

logger = logging.getLogger(__name__)


def _parse_port(raw: str | None) -> int:
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return 389


def _parse_use_ssl(raw: str | None) -> bool:
    s = str(raw or "").strip().lower()
    return s in ("1", "true", "yes", "on")


@callback(
    Output("ldap-mapping-role-id", "value"),
    Input("ldap-mapping-role-select", "value"),
    prevent_initial_call=False,
)
def sync_ldap_mapping_role_hidden(select_value: str | None) -> str:
    return str(select_value or "")


@callback(
    Output("ldap-test-feedback", "children"),
    Input("ldap-test-btn", "n_clicks"),
    State("ldap-config-id", "value"),
    State("ldap-field-name", "value"),
    State("ldap-field-server_primary", "value"),
    State("ldap-field-server_secondary", "value"),
    State("ldap-field-port", "value"),
    State("ldap-field-use_ssl", "value"),
    State("ldap-field-bind_dn", "value"),
    State("ldap-field-bind_password", "value"),
    State("ldap-field-search_base_dn", "value"),
    State("ldap-field-user_search_filter", "value"),
    prevent_initial_call=True,
)
def run_ldap_connection_test(
    n_clicks,
    ldap_id_raw,
    _name,
    server_primary,
    server_secondary,
    port_raw,
    use_ssl_raw,
    bind_dn,
    bind_password,
    search_base_dn,
    user_search_filter,
):
    if not n_clicks:
        raise PreventUpdate

    if not server_primary or not str(server_primary).strip():
        return dmc.Alert("Primary server is required.", color="red", variant="light")
    if not bind_dn or not str(bind_dn).strip():
        return dmc.Alert("Bind DN is required.", color="red", variant="light")
    if not search_base_dn or not str(search_base_dn).strip():
        return dmc.Alert("Search base DN is required.", color="red", variant="light")

    ldap_id: int | None = None
    if ldap_id_raw and str(ldap_id_raw).strip().isdigit():
        ldap_id = int(str(ldap_id_raw).strip())

    sec = str(server_secondary or "").strip() or None
    pw_plain = str(bind_password or "").strip() or None

    try:
        result = settings_crud.test_ldap_connection(
            str(server_primary).strip(),
            sec,
            _parse_port(port_raw),
            _parse_use_ssl(use_ssl_raw),
            str(bind_dn).strip(),
            pw_plain,
            str(search_base_dn).strip(),
            str(user_search_filter or "(sAMAccountName={username})").strip(),
            ldap_id,
            "test",
        )
    except Exception as exc:
        logger.exception("LDAP test connection failed")
        return dmc.Alert(f"Request failed: {exc}", color="red", variant="light")

    if result.get("ok"):
        msg = result.get("message") or "Connection OK."
        return dmc.Alert(msg, color="green", variant="light")

    err = result.get("error") or "LDAP test failed."
    return dmc.Alert(str(err), color="red", variant="light")
