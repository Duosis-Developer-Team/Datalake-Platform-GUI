"""Platform Versions paneli callback'leri.

Yetki iki yerde kontrol edilir: düğmenin görünürlüğünde ve callback'in içinde.
Görünürlük tek başına yetki değildir — istemci tarafı her zaman taklit edilebilir.
"""

from __future__ import annotations

import json
import logging

from dash import ALL, Input, Output, State, callback, ctx
from dash.exceptions import PreventUpdate

from src.auth import versions_crud
from src.auth.permission_service import can_edit
from src.pages.settings.platform import versions as page
from src.pages.settings.platform import versions_view as vv
from src.services import release_note_generator as generator

logger = logging.getLogger(__name__)

REGENERATE_CODE = "sec:settings_platform_versions:regenerate"


class ctx_helper:
    """Tetikleyen bileşenin sürümünü verir; testte kolayca değiştirilebilsin diye ayrı."""

    @staticmethod
    def triggered_version() -> str | None:
        triggered = getattr(ctx, "triggered_id", None)
        if isinstance(triggered, dict):
            return str(triggered.get("version") or "") or None
        if isinstance(triggered, str) and triggered.startswith("{"):
            try:
                return str(json.loads(triggered).get("version") or "") or None
            except ValueError:
                return None
        return None


def _may_regenerate(user_store: dict | None) -> bool:
    """Oturumdaki kullanıcının notu yeniden üretme yetkisi var mı."""
    user_id = (user_store or {}).get("id")
    if not user_id:
        return False
    return bool(can_edit(int(user_id), REGENERATE_CODE))


@callback(
    Output(page.LIST_ID, "children"),
    Input(page.SEARCH_ID, "value"),
    Input("auth-user-store", "data"),
)
def filter_releases(term, user_store):
    """Aramayı uygular ve listeyi yeniden çizer.

    İlk çizimde de çalışır, çünkü sayfa iskeleti (`versions.build_layout`) yetkiyi
    bilmez; düğme ancak buradan gelir. Kullanıcı store'u State değil Input: oturum
    bilgisi ilk boyamadan sonra düştüğü için, düştüğü anda liste tazelensin.
    """
    releases, live_version = page.load_releases()
    return vv.search_panel(
        releases,
        live_version,
        str(term or ""),
        can_regenerate=_may_regenerate(user_store),
    )


@callback(
    Output(page.LIST_ID, "children", allow_duplicate=True),
    Input({"type": "pv-regen", "version": ALL}, "n_clicks"),
    State("auth-user-store", "data"),
    State({"type": "pv-regen", "version": ALL}, "id"),
    State(page.SEARCH_ID, "value"),
    prevent_initial_call=True,
)
def regenerate_note(n_clicks, user_store, ids, term):
    if not any(n_clicks or []):
        raise PreventUpdate
    if not _may_regenerate(user_store):
        logger.warning("regenerate refused: user lacks %s", REGENERATE_CODE)
        raise PreventUpdate

    version = ctx_helper.triggered_version()
    if not version:
        raise PreventUpdate
    row = versions_crud.get_release_by_version(version)
    if not row:
        raise PreventUpdate

    try:
        generator.generate_for_release(int(row["id"]))
    except Exception:
        # Üretim merdiveni zaten sessizce deterministik nota düşer; buraya ancak
        # DB/veri hatası gelir. Panel yine de tazelenmeli, ekrana hata düşmemeli.
        logger.exception("release note regeneration failed for %s", version)

    releases, live_version = page.load_releases()
    return vv.search_panel(releases, live_version, str(term or ""), can_regenerate=True)
