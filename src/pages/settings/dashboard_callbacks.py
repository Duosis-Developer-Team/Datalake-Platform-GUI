"""Callbacks for Settings overview (platform cache refresh)."""

from __future__ import annotations

import logging

import dash_mantine_components as dmc
from dash import Input, Output, State, callback
from dash.exceptions import PreventUpdate

from src.auth.permission_service import can_view
from src.pages.settings.shell import has_any_settings_access
from src.services import api_client as api

logger = logging.getLogger(__name__)


def _feedback_lines(payload: dict) -> list[str]:
    lines: list[str] = []
    services = (payload or {}).get("services") or {}
    order = ("datacenter_api", "customer_api", "crm_engine")
    labels = {
        "datacenter_api": "Datacenter API",
        "customer_api": "Customer API",
        "crm_engine": "CRM engine",
    }
    for key in order:
        row = services.get(key)
        if not row:
            continue
        label = labels.get(key, key)
        if row.get("ok"):
            lines.append(f"{label}: OK")
        else:
            err = row.get("error") or "failed"
            lines.append(f"{label}: {err}")
    if (payload or {}).get("gui_cache_cleared"):
        lines.append("GUI HTTP cache: cleared")
    elif (payload or {}).get("gui_cache_error"):
        lines.append(f"GUI HTTP cache: {payload.get('gui_cache_error')}")
    return lines


@callback(
    Output("settings-cache-refresh-feedback", "children"),
    Input("settings-cache-refresh-btn", "n_clicks"),
    State("auth-user-store", "data"),
    prevent_initial_call=True,
)
def run_platform_cache_refresh(n_clicks: int | None, user_store: dict | None):
    if not n_clicks:
        raise PreventUpdate

    uid = (user_store or {}).get("id")
    if not uid:
        return dmc.Alert(
            "You must be signed in to refresh caches.",
            color="red",
            variant="light",
        )

    user_id = int(uid)
    if not (can_view(user_id, "grp:settings") or has_any_settings_access(user_id)):
        return dmc.Alert(
            "You do not have permission to refresh platform caches.",
            color="red",
            variant="light",
        )

    try:
        payload = api.refresh_platform_redis_caches()
    except Exception as exc:
        logger.exception("refresh_platform_redis_caches failed")
        return dmc.Alert(
            f"Cache refresh failed: {exc}",
            color="red",
            variant="light",
        )

    lines = _feedback_lines(payload)
    body = "\n".join(lines) if lines else "No service results returned."

    svc = (payload or {}).get("services") or {}
    expected_keys = ("datacenter_api", "customer_api", "crm_engine")
    all_ok = len(svc) >= len(expected_keys) and all(
        svc.get(k, {}).get("ok") for k in expected_keys
    )

    color = "green" if all_ok else "yellow"
    title = "Caches refreshed" if all_ok else "Caches refreshed with warnings"

    return dmc.Alert(title=title, color=color, variant="light", children=dmc.Text(body, size="sm", style={"whiteSpace": "pre-wrap"}))
