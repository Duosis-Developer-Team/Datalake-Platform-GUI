"""Onay bekleyen taslağın panelde incelenmesi: Onayla / Reddet.

Taslak metni iki katmanla korunuyor:
  1. Release listesi taslağı hiç taşımaz (`headline_block` ona bakmaz).
  2. Taslak yalnızca yetkili kullanıcıya, ayrı ve açıkça kapılanmış bir yoldan
     (`pending`) gelir.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from dash.exceptions import PreventUpdate

from src.auth import versions_crud
from src.pages.settings.platform import versions_callbacks as cb
from src.pages.settings.platform import versions_view as vv

CODE = "sec:settings_platform_versions:regenerate"
CONFIRM = "Onayla ve yayına al"
REJECT = "Reddet"


def _texts(node) -> list[str]:
    out: list[str] = []
    if node is None:
        return out
    if isinstance(node, (str, int, float)):
        return [str(node)]
    if isinstance(node, (list, tuple)):
        for n in node:
            out.extend(_texts(n))
        return out
    out.extend(_texts(getattr(node, "children", None)))
    label = getattr(node, "label", None)
    if isinstance(label, str):
        out.append(label)
    return out


def _release(version: str = "2026.08.1") -> dict:
    return {
        "id": 7,
        "version": version,
        "released_at": "2026-08-03",
        "note": {"headline": None, "source": "auto", "body": {"added": [], "fixed": []}},
        "changes": [],
        "services": [],
    }


def _draft() -> dict:
    return {
        "release_id": 7,
        "draft_headline": "Panel baştan yazıldı",
        "draft_body": {
            "added": [{"text": "Sürüm kartları yenilendi", "shas": ["aaaaaaaaaaaa"]}],
            "fixed": [{"text": "Hizalama düzeltildi", "shas": ["bbbbbbbbbbbb"]}],
            "improved": [],
        },
        "model": "gpt-oss-120b",
    }


# --- taslakların okunması -------------------------------------------------

def test_pending_drafts_are_keyed_by_version():
    """admin-api `id` döndürmüyor; iki taşıma yolunda da ortak anahtar sürüm."""
    rows = [{"version": "2026.08.1", "release_id": 7, "draft_headline": "X",
             "draft_body": {"added": []}, "model": "m"}]
    with patch.object(versions_crud.db, "fetch_all", return_value=rows):
        out = versions_crud.pending_draft_notes()
    assert set(out) == {"2026.08.1"}
    assert out["2026.08.1"]["release_id"] == 7


def test_pending_drafts_query_skips_rows_without_a_draft():
    seen: dict = {}

    def _fetch(sql, params=None):
        seen["sql"] = sql
        return []

    with patch.object(versions_crud.db, "fetch_all", side_effect=_fetch):
        versions_crud.pending_draft_notes()
    assert "draft_body is not null" in seen["sql"].lower()


# --- taslak bloğunun çizimi ----------------------------------------------

def test_draft_block_shows_the_draft_text_and_both_buttons():
    text = " ".join(_texts(vv.draft_review_block("2026.08.1", _draft())))
    assert "Panel baştan yazıldı" in text
    assert "Sürüm kartları yenilendi" in text
    assert CONFIRM in text
    assert REJECT in text


def test_draft_buttons_carry_the_version():
    assert vv.confirm_button("2026.08.1").id == {"type": "pv-confirm", "version": "2026.08.1"}
    assert vv.reject_button("2026.08.1").id == {"type": "pv-reject", "version": "2026.08.1"}


def test_draft_block_labels_keep_the_dotted_turkish_i():
    """CSS uppercase Türkçe 'İ'yi bozuyor — etiket hazır büyük harf gelmeli."""
    labels: list = []

    def collect(node):
        if node is None or isinstance(node, str):
            return
        if isinstance(node, (list, tuple)):
            for n in node:
                collect(n)
            return
        if getattr(node, "tt", None) == "uppercase":
            labels.append(getattr(node, "children", None))
        collect(getattr(node, "children", None))

    collect(vv.draft_review_block("2026.08.1", _draft()))
    assert not labels, f"CSS uppercase Türkçe etiketi bozuyor: {labels}"
    assert "ONAY BEKLEYEN TASLAK" in _texts(vv.draft_review_block("2026.08.1", _draft()))


def test_hero_card_shows_the_draft_only_when_one_is_passed():
    with_draft = " ".join(_texts(vv.hero_card(_release(), can_regenerate=True, draft=_draft())))
    without = " ".join(_texts(vv.hero_card(_release(), can_regenerate=True)))
    assert CONFIRM in with_draft
    assert CONFIRM not in without


def test_history_row_marks_a_pending_draft_in_the_closed_line():
    """Satırı açmadan da taslağı olan sürüm görünmeli."""
    text = " ".join(_texts(vv.history_row(_release(), can_regenerate=True, draft=_draft())))
    assert "Taslak bekliyor" in text
    assert "Taslak bekliyor" not in " ".join(_texts(vv.history_row(_release(), can_regenerate=True)))


def test_release_list_never_draws_a_draft_without_permission():
    """İkinci kat: çağıran boş sözlük göndermeyi unutsa bile taslak sızmamalı."""
    pending = {"2026.08.1": _draft()}
    allowed = " ".join(_texts(vv.release_list([_release()], "2026.08.1",
                                              can_regenerate=True, pending=pending)))
    refused = " ".join(_texts(vv.release_list([_release()], "2026.08.1",
                                              can_regenerate=False, pending=pending)))
    assert CONFIRM in allowed
    assert CONFIRM not in refused
    assert "Panel baştan yazıldı" not in refused


def test_search_panel_forwards_pending_drafts():
    panel = vv.search_panel([_release()], "2026.08.1", "", can_regenerate=True,
                            pending={"2026.08.1": _draft()})
    assert CONFIRM in " ".join(_texts(panel))


def test_published_note_stays_visible_while_a_draft_waits():
    """Onaylanana kadar kullanıcı yayındaki (otomatik) notu görmeye devam eder."""
    rel = _release()
    rel["note"]["body"] = {"added": [{"text": "x", "shas": ["a"]}], "fixed": [], "improved": []}
    text = " ".join(_texts(vv.hero_card(rel, can_regenerate=True, draft=_draft())))
    assert "otomatik özet" in text


# --- taslakların callback'e taşınması -------------------------------------

def test_filter_callback_reads_no_drafts_without_permission():
    def _boom():
        pytest.fail("yetkisiz kullanıcı için taslak okunmamalı")

    seen: dict = {}

    def _panel(releases, live, term, *, can_regenerate=False, pending=None):
        seen["pending"] = pending
        return "liste"

    with patch.object(cb, "can_edit", lambda uid, code: False), \
         patch.object(cb.versions_crud, "pending_draft_notes", _boom), \
         patch.object(cb.page, "load_releases", lambda: ([], None)), \
         patch.object(cb.vv, "search_panel", _panel):
        cb.filter_releases("", {"id": 5})

    assert seen["pending"] == {}


def test_filter_callback_passes_drafts_through_with_permission():
    seen: dict = {}

    def _panel(releases, live, term, *, can_regenerate=False, pending=None):
        seen["pending"] = pending
        return "liste"

    with patch.object(cb, "can_edit", lambda uid, code: True), \
         patch.object(cb.versions_crud, "pending_draft_notes", lambda: {"2026.08.1": _draft()}), \
         patch.object(cb.page, "load_releases", lambda: ([], None)), \
         patch.object(cb.vv, "search_panel", _panel):
        cb.filter_releases("", {"id": 5})

    assert set(seen["pending"]) == {"2026.08.1"}


def test_panel_still_draws_when_the_draft_query_blows_up():
    def _boom():
        raise RuntimeError("db down")

    with patch.object(cb, "can_edit", lambda uid, code: True), \
         patch.object(cb.versions_crud, "pending_draft_notes", _boom), \
         patch.object(cb.page, "load_releases", lambda: ([], None)), \
         patch.object(cb.vv, "search_panel",
                      lambda *a, can_regenerate=False, pending=None: f"liste:{pending}"):
        assert cb.filter_releases("", {"id": 5}) == "liste:{}"


# --- onayla / reddet callback'leri ----------------------------------------

def _run(fn, term=""):
    return fn([1], {"id": 5}, term)


def test_confirm_publishes_the_draft_for_the_clicked_version():
    seen: dict = {}

    with patch.object(cb, "can_edit", lambda uid, code: True), \
         patch.object(cb.ctx_helper, "triggered_version", lambda: "2026.08.1"), \
         patch.object(cb.versions_crud, "get_release_by_version", lambda v: {"id": 7}), \
         patch.object(cb.versions_crud, "confirm_draft_note",
                      lambda rid: seen.setdefault("rid", rid)), \
         patch.object(cb.versions_crud, "pending_draft_notes", dict), \
         patch.object(cb.page, "load_releases", lambda: ([], None)), \
         patch.object(cb.vv, "search_panel",
                      lambda *a, can_regenerate=False, pending=None: "yeni liste"):
        out = _run(cb.confirm_draft)

    assert seen["rid"] == 7
    assert out == "yeni liste"


def test_reject_drops_the_draft_for_the_clicked_version():
    seen: dict = {}

    with patch.object(cb, "can_edit", lambda uid, code: True), \
         patch.object(cb.ctx_helper, "triggered_version", lambda: "2026.08.1"), \
         patch.object(cb.versions_crud, "get_release_by_version", lambda v: {"id": 7}), \
         patch.object(cb.versions_crud, "reject_draft_note",
                      lambda rid: seen.setdefault("rid", rid)), \
         patch.object(cb.versions_crud, "pending_draft_notes", dict), \
         patch.object(cb.page, "load_releases", lambda: ([], None)), \
         patch.object(cb.vv, "search_panel",
                      lambda *a, can_regenerate=False, pending=None: "yeni liste"):
        _run(cb.reject_draft)

    assert seen["rid"] == 7


@pytest.mark.parametrize("fn_name,crud_name", [
    ("confirm_draft", "confirm_draft_note"),
    ("reject_draft", "reject_draft_note"),
])
def test_decision_refuses_without_permission(fn_name, crud_name):
    """Düğmenin çizilmiş olması yetki değildir: callback kendi kontrolünü yapar."""
    def _boom(_rid):
        pytest.fail("yetkisiz kullanıcı için karar yazılmamalı")

    with patch.object(cb, "can_edit", lambda uid, code: False), \
         patch.object(cb.versions_crud, crud_name, _boom):
        with pytest.raises(PreventUpdate):
            _run(getattr(cb, fn_name))


@pytest.mark.parametrize("fn_name,crud_name", [
    ("confirm_draft", "confirm_draft_note"),
    ("reject_draft", "reject_draft_note"),
])
def test_decision_refuses_without_a_user(fn_name, crud_name):
    def _boom(_rid):
        pytest.fail("kullanıcısız istekte karar yazılmamalı")

    with patch.object(cb, "can_edit", lambda uid, code: True), \
         patch.object(cb.versions_crud, crud_name, _boom):
        with pytest.raises(PreventUpdate):
            getattr(cb, fn_name)([1], None, "")


@pytest.mark.parametrize("fn_name", ["confirm_draft", "reject_draft"])
def test_decision_ignores_a_render_without_clicks(fn_name):
    with pytest.raises(PreventUpdate):
        getattr(cb, fn_name)([None], {"id": 5}, "")


@pytest.mark.parametrize("fn_name", ["confirm_draft", "reject_draft"])
def test_decision_prevents_update_for_an_unknown_version(fn_name):
    with patch.object(cb, "can_edit", lambda uid, code: True), \
         patch.object(cb.ctx_helper, "triggered_version", lambda: "9999.99.9"), \
         patch.object(cb.versions_crud, "get_release_by_version", lambda v: None):
        with pytest.raises(PreventUpdate):
            _run(getattr(cb, fn_name))


def test_confirm_keeps_the_search_term():
    seen: dict = {}

    def _panel(releases, live, term, *, can_regenerate=False, pending=None):
        seen["term"] = term
        return "yeni liste"

    with patch.object(cb, "can_edit", lambda uid, code: True), \
         patch.object(cb.ctx_helper, "triggered_version", lambda: "2026.08.1"), \
         patch.object(cb.versions_crud, "get_release_by_version", lambda v: {"id": 7}), \
         patch.object(cb.versions_crud, "confirm_draft_note", lambda rid: True), \
         patch.object(cb.versions_crud, "pending_draft_notes", dict), \
         patch.object(cb.page, "load_releases", lambda: ([], None)), \
         patch.object(cb.vv, "search_panel", _panel):
        _run(cb.confirm_draft, term="panel")

    assert seen["term"] == "panel"


def test_confirm_still_redraws_when_the_write_blows_up():
    def _boom(_rid):
        raise RuntimeError("db down")

    with patch.object(cb, "can_edit", lambda uid, code: True), \
         patch.object(cb.ctx_helper, "triggered_version", lambda: "2026.08.1"), \
         patch.object(cb.versions_crud, "get_release_by_version", lambda v: {"id": 7}), \
         patch.object(cb.versions_crud, "confirm_draft_note", _boom), \
         patch.object(cb.versions_crud, "pending_draft_notes", dict), \
         patch.object(cb.page, "load_releases", lambda: ([], None)), \
         patch.object(cb.vv, "search_panel",
                      lambda *a, can_regenerate=False, pending=None: "yeni liste"):
        assert _run(cb.confirm_draft) == "yeni liste"
