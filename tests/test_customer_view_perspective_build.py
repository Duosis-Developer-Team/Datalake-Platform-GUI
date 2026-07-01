"""Item 5: the perspective toggle should build only the requested perspective,
not both. _customer_content(only_perspective=...) builds one perspective's
summary/virt/backup; _resolve_tab_content still resolves single-perspective
content. (Refetch was already eliminated by the shared cache in items 1-2.)
"""
import contextlib
from unittest.mock import patch

from dash import html

from src.pages import customer_view as cv
from tests.test_customer_view_tab_sections import _patch_all_getters, _tr


def test_only_perspective_builds_one_summary():
    with contextlib.ExitStack() as s:
        _patch_all_getters(s)
        with patch.object(cv, "_tab_summary", return_value=html.Div("S")) as m:
            content = cv._customer_content("Acme", _tr(), only_perspective=cv.PERSPECTIVE_CUSTOMER)
    assert m.call_count == 1, "only the requested perspective's summary is built"
    assert cv._resolve_tab_content(content, cv.PERSPECTIVE_CUSTOMER).get("summary") is not None


def test_no_only_perspective_builds_both():
    with contextlib.ExitStack() as s:
        _patch_all_getters(s)
        with patch.object(cv, "_tab_summary", return_value=html.Div("S")) as m:
            cv._customer_content("Acme", _tr())
    assert m.call_count == 2, "default build covers both perspectives"


def test_resolve_tab_content_handles_single_perspective():
    content = {"customer": {"summary": "X"}, "has_s3": False}
    assert cv._resolve_tab_content(content, cv.PERSPECTIVE_CUSTOMER) == {"summary": "X"}
    # Missing perspective falls back to whichever was built (no crash).
    assert cv._resolve_tab_content(content, cv.PERSPECTIVE_MANAGER) == {"summary": "X"}
