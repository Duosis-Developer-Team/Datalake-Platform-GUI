"""Item 3.3/3.4: async per-tab loading. The page renders an instant shell (tab
bar + per-tab placeholders + a ctx Store) with NO data fetch; each tab body is
filled independently by _render_tab_body from the ctx, so a slow tab can't block
the others. Export builds its context on demand from the (cached) getters.
"""
import contextlib
from unittest.mock import patch

import dash
from dash import dcc, html

from src.pages import customer_view as cv
from tests.test_customer_view_tab_sections import _patch_all_getters, _tr


def _walk(node):
    yield node
    children = getattr(node, "children", None)
    if isinstance(children, (list, tuple)):
        for c in children:
            yield from _walk(c)
    elif children is not None:
        yield from _walk(children)


def _ids(node):
    return {getattr(n, "id", None) for n in _walk(node)}


def test_shell_has_ctx_store_and_tab_placeholders():
    shell = cv.render_customer_shell("Acme", _tr(), None, perspective=cv.PERSPECTIVE_MANAGER)
    ids = _ids(shell)
    assert "customer-view-ctx" in ids
    assert "cust-tab-body-summary" in ids
    assert "cust-tab-body-itsm" in ids
    assert "cust-tab-body-s3" in ids


def test_shell_does_not_fetch_any_data():
    with patch.object(cv, "_customer_content") as m_content, \
         patch.object(cv.api, "get_customer_resources") as m_res:
        cv.render_customer_shell("Acme", _tr(), None, perspective=cv.PERSPECTIVE_MANAGER)
    m_content.assert_not_called()
    m_res.assert_not_called()


def test_render_tab_body_availability_fetches_only_availability():
    ctx = {"customer": "Acme", "perspective": cv.PERSPECTIVE_MANAGER, "tr": _tr()}
    with patch.object(cv.api, "get_customer_availability_bundle",
                      return_value={"vm_outage_counts": {}}) as m:
        out = cv._render_tab_body("avail", ctx)
    m.assert_called_once()
    assert out is not None


def test_render_tab_body_summary_renders():
    ctx = {"customer": "Acme", "perspective": cv.PERSPECTIVE_MANAGER, "tr": _tr()}
    with contextlib.ExitStack() as s:
        _patch_all_getters(s)
        out = cv._render_tab_body("summary", ctx)
    assert out is not None


def test_render_tab_body_empty_customer_no_update():
    assert cv._render_tab_body("avail", {}) is dash.no_update
    assert cv._render_tab_body("avail", {"customer": "  "}) is dash.no_update


def test_build_export_context_from_getters():
    with contextlib.ExitStack() as s:
        _patch_all_getters(s)
        with patch.object(cv.api, "get_customer_itsm_extremes", return_value={}), \
             patch.object(cv.api, "get_customer_itsm_tickets", return_value=[]), \
             patch.object(cv.api, "get_physical_inventory_customer", return_value=[]):
            ctx = cv._build_export_context("Acme", _tr())
    assert ctx["customer_name"] == "Acme"
    assert "totals" in ctx and "assets" in ctx
