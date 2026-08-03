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
    """Oturumdaki kullanıcının notu yeniden üretme yetkisi var mı.

    Onaylama/reddetme de aynı koda bağlı: üretimi tetikleyebilen kişi, çıkan
    taslağı yayına alabilecek kişidir. Ayrı bir yetki düğümü açmak katalogda
    kullanılmayan bir kod bırakırdı.
    """
    user_id = (user_store or {}).get("id")
    if not user_id:
        return False
    return bool(can_edit(int(user_id), REGENERATE_CODE))


def _pending_drafts(allowed: bool) -> dict[str, dict]:
    """Onay bekleyen taslaklar; yetkisi olmayana hiç okunmaz.

    Taslak metni admin-api'den gelmez (router taslak alanlarını bilerek dışarı
    vermiyor), doğrudan DB'den okunur. Bu okuma başarısız olsa bile panel çizilmeye
    devam etmeli — taslak yoksa sadece onay kutusu görünmez.
    """
    if not allowed:
        return {}
    try:
        return versions_crud.pending_draft_notes()
    except Exception:
        logger.exception("pending drafts could not be read")
        return {}


def _redraw(term, *, allowed: bool):
    releases, live_version = page.load_releases()
    return vv.search_panel(
        releases,
        live_version,
        str(term or ""),
        can_regenerate=allowed,
        pending=_pending_drafts(allowed),
    )


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
    return _redraw(term, allowed=_may_regenerate(user_store))


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

    return _redraw(term, allowed=True)


def _decide(n_clicks, user_store, term, action, what: str):
    """Onayla/Reddet callback'lerinin ortak gövdesi.

    Yetki burada tekrar kontrol edilir; düğmenin çizilmiş olması yetki değildir.
    """
    if not any(n_clicks or []):
        raise PreventUpdate
    if not _may_regenerate(user_store):
        logger.warning("%s refused: user lacks %s", what, REGENERATE_CODE)
        raise PreventUpdate

    version = ctx_helper.triggered_version()
    if not version:
        raise PreventUpdate
    row = versions_crud.get_release_by_version(version)
    if not row:
        raise PreventUpdate

    try:
        action(int(row["id"]))
    except Exception:
        logger.exception("%s failed for %s", what, version)

    return _redraw(term, allowed=True)


@callback(
    Output(page.LIST_ID, "children", allow_duplicate=True),
    Input({"type": "pv-confirm", "version": ALL}, "n_clicks"),
    State("auth-user-store", "data"),
    State(page.SEARCH_ID, "value"),
    prevent_initial_call=True,
)
def confirm_draft(n_clicks, user_store, term):
    """Taslağı yayına alır: `body` modelin metni olur, kaynak `model` olarak işaretlenir."""
    return _decide(n_clicks, user_store, term, versions_crud.confirm_draft_note, "confirm")


@callback(
    Output(page.LIST_ID, "children", allow_duplicate=True),
    Input({"type": "pv-reject", "version": ALL}, "n_clicks"),
    State("auth-user-store", "data"),
    State(page.SEARCH_ID, "value"),
    prevent_initial_call=True,
)
def reject_draft(n_clicks, user_store, term):
    """Taslağı siler. Yayındaki nota dokunmaz — panel otomatik özette kalır."""
    return _decide(n_clicks, user_store, term, versions_crud.reject_draft_note, "reject")
