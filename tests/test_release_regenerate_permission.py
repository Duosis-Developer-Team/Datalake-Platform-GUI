"""Yeniden üret düğmesi — yetki hem görünürlükte hem callback'in içinde kontrol edilir.

Görünürlük tek başına yetki değildir: istemci tarafı her zaman taklit edilebilir,
bu yüzden callback kendi kontrolünü tekrar yapar.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from dash.exceptions import PreventUpdate

from src.auth import permission_catalog
from src.pages.settings.platform import versions_callbacks as cb
from src.pages.settings.platform import versions_view as vv

CODE = "sec:settings_platform_versions:regenerate"
PAGE_CODE = "page:settings_platform_versions"
LABEL = "Yeniden üret"


def _texts(node) -> list[str]:
    """Bileşen ağacındaki bütün metinleri toplar."""
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


def _codes(node, out=None) -> list[str]:
    out = out if out is not None else []
    out.append(node.code)
    for child in node.children or []:
        _codes(child, out)
    return out


def _find(node, code: str):
    if node.code == code:
        return node
    for child in node.children or []:
        hit = _find(child, code)
        if hit:
            return hit
    return None


def _find_in_roots(code: str):
    for root in permission_catalog.build_default_permission_roots():
        hit = _find(root, code)
        if hit:
            return hit
    return None


def _release(version: str = "2026.08.1") -> dict:
    return {
        "id": 7,
        "version": version,
        "released_at": "2026-08-03",
        "note": None,
        "changes": [],
        "services": [],
    }


# --- yetki düğümü ---------------------------------------------------------

def test_permission_code_is_registered():
    codes: list[str] = []
    for root in permission_catalog.build_default_permission_roots():
        _codes(root, codes)
    assert CODE in codes


def test_permission_code_is_a_child_of_the_versions_page():
    page_node = _find_in_roots(PAGE_CODE)
    assert page_node is not None
    assert CODE in [c.code for c in page_node.children or []]


def test_permission_code_is_an_action_not_a_new_page():
    node = _find_in_roots(CODE)
    assert node is not None
    assert node.resource_type == "action"
    assert not node.route_pattern


# --- düğmenin çizimi ------------------------------------------------------

def test_button_id_carries_the_version():
    button = vv.regenerate_button("2026.08.1")
    assert button.id == {"type": "pv-regen", "version": "2026.08.1"}


def test_hero_card_shows_the_button_only_with_permission():
    rel = _release()
    assert LABEL in " ".join(_texts(vv.hero_card(rel, can_regenerate=True)))
    assert LABEL not in " ".join(_texts(vv.hero_card(rel, can_regenerate=False)))
    assert LABEL not in " ".join(_texts(vv.hero_card(rel)))


def test_history_row_shows_the_button_only_with_permission():
    rel = _release()
    assert LABEL in " ".join(_texts(vv.history_row(rel, can_regenerate=True)))
    assert LABEL not in " ".join(_texts(vv.history_row(rel)))


def test_release_list_passes_the_flag_down_to_every_card():
    releases = [_release("2026.08.2"), _release("2026.07.1")]
    with_btn = " ".join(_texts(vv.release_list(releases, "2026.08.2", can_regenerate=True)))
    without = " ".join(_texts(vv.release_list(releases, "2026.08.2")))
    assert with_btn.count(LABEL) == 2
    assert LABEL not in without


def test_search_panel_forwards_the_flag():
    panel = vv.search_panel([_release()], "2026.08.1", "", can_regenerate=True)
    assert LABEL in " ".join(_texts(panel))
    assert LABEL not in " ".join(_texts(vv.search_panel([_release()], "2026.08.1", "")))


# --- arama callback'i -----------------------------------------------------

def test_filter_callback_draws_no_button_without_permission():
    seen: dict = {}

    def _panel(releases, live, term, *, can_regenerate=False, pending=None):
        seen["flag"] = can_regenerate
        return "liste"

    with patch.object(cb, "can_edit", lambda uid, code: False), \
         patch.object(cb.versions_crud, "pending_draft_notes", dict), \
         patch.object(cb.page, "load_releases", lambda: ([], None)), \
         patch.object(cb.vv, "search_panel", _panel):
        assert cb.filter_releases("", {"id": 5}) == "liste"

    assert seen["flag"] is False


def test_filter_callback_checks_the_regenerate_code():
    seen: dict = {}

    def _panel(releases, live, term, *, can_regenerate=False, pending=None):
        seen["flag"] = can_regenerate
        return "liste"

    with patch.object(cb, "can_edit", lambda uid, code: code == CODE), \
         patch.object(cb.versions_crud, "pending_draft_notes", dict), \
         patch.object(cb.page, "load_releases", lambda: ([], None)), \
         patch.object(cb.vv, "search_panel", _panel):
        cb.filter_releases("panel", {"id": 5})

    assert seen["flag"] is True


def test_filter_callback_draws_no_button_without_a_user():
    seen: dict = {}

    def _panel(releases, live, term, *, can_regenerate=False, pending=None):
        seen["flag"] = can_regenerate
        return "liste"

    with patch.object(cb, "can_edit", lambda uid, code: True), \
         patch.object(cb.versions_crud, "pending_draft_notes", dict), \
         patch.object(cb.page, "load_releases", lambda: ([], None)), \
         patch.object(cb.vv, "search_panel", _panel):
        cb.filter_releases("", None)

    assert seen["flag"] is False


# --- yeniden üret callback'i ---------------------------------------------

def test_callback_ignores_a_render_without_clicks():
    with pytest.raises(PreventUpdate):
        cb.regenerate_note([None], {"id": 5}, [{"type": "pv-regen", "version": "2026.08.1"}], "")


def test_callback_refuses_without_permission():
    def _boom(_rid):
        pytest.fail("yetkisiz kullanıcı için üretim çağrılmamalı")

    with patch.object(cb, "can_edit", lambda uid, code: False), \
         patch.object(cb.generator, "generate_for_release", _boom):
        with pytest.raises(PreventUpdate):
            cb.regenerate_note([1], {"id": 5}, [{"type": "pv-regen", "version": "2026.08.1"}], "")


def test_callback_refuses_without_a_user():
    def _boom(_rid):
        pytest.fail("kullanıcısız istekte üretim çağrılmamalı")

    with patch.object(cb, "can_edit", lambda uid, code: True), \
         patch.object(cb.generator, "generate_for_release", _boom):
        with pytest.raises(PreventUpdate):
            cb.regenerate_note([1], None, [{"type": "pv-regen", "version": "2026.08.1"}], "")


def test_callback_regenerates_for_the_clicked_version():
    seen: dict = {}

    with patch.object(cb, "can_edit", lambda uid, code: True), \
         patch.object(cb.ctx_helper, "triggered_version", lambda: "2026.08.1"), \
         patch.object(cb.versions_crud, "get_release_by_version", lambda v: {"id": 7}), \
         patch.object(cb.generator, "generate_for_release", lambda rid: seen.setdefault("rid", rid)), \
         patch.object(cb.versions_crud, "pending_draft_notes", dict), \
         patch.object(cb.page, "load_releases", lambda: ([], None)), \
         patch.object(cb.vv, "search_panel", lambda rels, live, t, *, can_regenerate=False, pending=None: "yeni liste"):
        out = cb.regenerate_note([1], {"id": 5}, [{"type": "pv-regen", "version": "2026.08.1"}], "")

    assert seen["rid"] == 7
    assert out == "yeni liste"


def test_callback_keeps_the_search_term_after_regenerating():
    seen: dict = {}

    def _panel(releases, live, term, *, can_regenerate=False, pending=None):
        seen["term"] = term
        return "yeni liste"

    with patch.object(cb, "can_edit", lambda uid, code: True), \
         patch.object(cb.ctx_helper, "triggered_version", lambda: "2026.08.1"), \
         patch.object(cb.versions_crud, "get_release_by_version", lambda v: {"id": 7}), \
         patch.object(cb.generator, "generate_for_release", lambda rid: None), \
         patch.object(cb.versions_crud, "pending_draft_notes", dict), \
         patch.object(cb.page, "load_releases", lambda: ([], None)), \
         patch.object(cb.vv, "search_panel", _panel):
        cb.regenerate_note([1], {"id": 5}, [{"type": "pv-regen", "version": "2026.08.1"}], "panel")

    assert seen["term"] == "panel"


def test_callback_prevents_update_for_unknown_version():
    with patch.object(cb, "can_edit", lambda uid, code: True), \
         patch.object(cb.ctx_helper, "triggered_version", lambda: "9999.99.9"), \
         patch.object(cb.versions_crud, "get_release_by_version", lambda v: None):
        with pytest.raises(PreventUpdate):
            cb.regenerate_note([1], {"id": 5}, [{"type": "pv-regen", "version": "9999.99.9"}], "")


def test_callback_prevents_update_when_the_trigger_has_no_version():
    with patch.object(cb, "can_edit", lambda uid, code: True), \
         patch.object(cb.ctx_helper, "triggered_version", lambda: None):
        with pytest.raises(PreventUpdate):
            cb.regenerate_note([1], {"id": 5}, [{"type": "pv-regen", "version": "2026.08.1"}], "")


def test_callback_still_redraws_when_generation_blows_up():
    def _boom(_rid):
        raise RuntimeError("chatbot down")

    with patch.object(cb, "can_edit", lambda uid, code: True), \
         patch.object(cb.ctx_helper, "triggered_version", lambda: "2026.08.1"), \
         patch.object(cb.versions_crud, "get_release_by_version", lambda v: {"id": 7}), \
         patch.object(cb.generator, "generate_for_release", _boom), \
         patch.object(cb.versions_crud, "pending_draft_notes", dict), \
         patch.object(cb.page, "load_releases", lambda: ([], None)), \
         patch.object(cb.vv, "search_panel", lambda rels, live, t, *, can_regenerate=False, pending=None: "yeni liste"):
        assert cb.regenerate_note([1], {"id": 5}, [{"type": "pv-regen", "version": "2026.08.1"}], "") == "yeni liste"
