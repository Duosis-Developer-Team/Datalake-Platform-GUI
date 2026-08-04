"""Dash callbacks for the Colocation Configuration settings page."""

from __future__ import annotations

import logging

import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, callback, ctx, no_update
from dash.exceptions import PreventUpdate

from src.auth.permission_service import can_view
from src.pages.settings.integrations.colocation_config import COLOCATION_ROLE_IDS
from src.services import api_client as api
from src.utils.colocation_config_ui import preview_sellable_free_u, render_sellable_total

logger = logging.getLogger(__name__)

# Same node the page render/nav are gated on (src/pages/settings/shell.py,
# permission_service.resolve_pathname_to_page_code). Re-checked here because a
# rendered page is not proof of authorization — Dash callback endpoints are
# reachable directly, independent of what the client actually rendered. This
# is the exact bug class fixed once already for the floor map (page gated
# under one node, its callbacks under none/another).
PERMISSION_CODE = "page:settings_colocation_config"


def _overrides(ids, values) -> dict[str, bool]:
    return {str(i["role"]): bool(v) for i, v in zip(ids or [], values or [])}


def _fmt(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _authorized(user_store: dict | None) -> bool:
    uid = (user_store or {}).get("id")
    if not uid:
        return False
    return bool(can_view(int(uid), PERMISSION_CODE))


@callback(
    Output("coloc-cfg-preview", "children"),
    Input({"type": "coloc-cfg-switch", "role": ALL}, "checked"),
    State({"type": "coloc-cfg-switch", "role": ALL}, "id"),
    State("coloc-cfg-store", "data"),
    State("auth-user-store", "data"),
    prevent_initial_call=True,
)
def preview(values, ids, store, user_store):
    if not _authorized(user_store):
        logger.warning("colocation preview refused: user lacks %s", PERMISSION_CODE)
        raise PreventUpdate
    merged = (store or {}).get("merged") or []
    ov = _overrides(ids, values)
    saved = preview_sellable_free_u(merged, {})
    pending = preview_sellable_free_u(merged, ov)
    return render_sellable_total(saved, pending)


@callback(
    Output("coloc-cfg-confirm", "opened"),
    Output("coloc-cfg-confirm-body", "children"),
    Output("coloc-cfg-msg", "children"),
    Input("coloc-cfg-save", "n_clicks"),
    State({"type": "coloc-cfg-switch", "role": ALL}, "checked"),
    State({"type": "coloc-cfg-switch", "role": ALL}, "id"),
    State("coloc-cfg-store", "data"),
    State("auth-user-store", "data"),
    prevent_initial_call=True,
)
def guard(n_clicks, values, ids, store, user_store):
    """İki riskli kombinasyonda önce onay modalı aç, aksi hâlde doğrudan kaydet."""
    if not n_clicks:
        raise PreventUpdate
    if not _authorized(user_store):
        logger.warning("colocation save refused: user lacks %s", PERMISSION_CODE)
        raise PreventUpdate
    merged = (store or {}).get("merged") or []
    ov = _overrides(ids, values)

    newly_sellable_colocation = [
        r for r in COLOCATION_ROLE_IDS
        if ov.get(r) and not next((m["sellable"] for m in merged if m["role_id"] == r), False)
    ]
    if newly_sellable_colocation:
        delta = sum(
            int(m.get("free_u") or 0) for m in merged
            if m["role_id"] in newly_sellable_colocation
        )
        return True, (
            "Bu rol müşteriye tahsisli kabinleri işaretliyor. Sellable yaparsan "
            f"aynı U hem tahsisli hem satılabilir sayılacak (+{_fmt(delta)} U)."
        ), no_update

    if not any(ov.values()):
        return True, (
            "Bütün roller hariç tutuluyor. Sellable U platform genelinde 0 olacak, "
            "TL potansiyeli sıfırlanacak."
        ), no_update

    return False, "", _save(ov, merged)


@callback(
    Output("coloc-cfg-msg", "children", allow_duplicate=True),
    Output("coloc-cfg-confirm", "opened", allow_duplicate=True),
    Input("coloc-cfg-confirm-ok", "n_clicks"),
    State({"type": "coloc-cfg-switch", "role": ALL}, "checked"),
    State({"type": "coloc-cfg-switch", "role": ALL}, "id"),
    State("coloc-cfg-store", "data"),
    State("auth-user-store", "data"),
    prevent_initial_call=True,
)
def confirm_save(n_clicks, values, ids, store, user_store):
    if not n_clicks:
        raise PreventUpdate
    if not _authorized(user_store):
        logger.warning("colocation save refused: user lacks %s", PERMISSION_CODE)
        raise PreventUpdate
    merged = (store or {}).get("merged") or []
    return _save(_overrides(ids, values), merged), False


@callback(
    Output("coloc-cfg-confirm", "opened", allow_duplicate=True),
    Input("coloc-cfg-confirm-cancel", "n_clicks"),
    prevent_initial_call=True,
)
def cancel(n_clicks):
    if not n_clicks:
        raise PreventUpdate
    return False


def _save(overrides: dict[str, bool], merged: list[dict]):
    """Tam kural setini yaz. Kısmi yazım ekran ile DB'yi ayrıştırır."""
    rules = [
        {"role_id": m["role_id"], "sellable": overrides.get(m["role_id"], bool(m["sellable"]))}
        for m in merged
    ]
    try:
        api.put_colocation_role_rules(rules)
    except Exception as exc:  # noqa: BLE001
        return dmc.Alert(f"Kaydedilemedi: {exc}", color="red", variant="light")
    return dmc.Alert(
        "Kaydedildi. Colocation kartı ve Sellable paneli yeni kurala göre hesaplanacak.",
        color="green", variant="light",
    )
