"""load_customer_view_data must fire without State(customer-main-tabs).

Regression: that State pointed at a component created by the callback's own
output, so Dash skipped the initial load and Customer View stayed on skeleton.
"""
from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import patch


def _walk(node):
    if node is None:
        return
    if isinstance(node, (list, tuple)):
        for item in node:
            yield from _walk(item)
        return
    yield node
    children = getattr(node, "children", None)
    if children is not None:
        yield from _walk(children)


def _collect_ids(component):
    return {getattr(n, "id", None) for n in _walk(component) if getattr(n, "id", None)}


def test_load_customer_view_data_has_no_customer_main_tabs_state():
    from src.pages import customer_view_callbacks as mod

    cb_src = Path(mod.__file__).read_text(encoding="utf-8")
    # Decorator block for load_customer_view_data (before the def line).
    marker = "def load_customer_view_data("
    idx = cb_src.index(marker)
    deco = cb_src[cb_src.rfind("@callback", 0, idx) : idx]
    # Ignore comments; only real State(...) registrations matter.
    code_lines = [
        ln for ln in deco.splitlines() if not ln.lstrip().startswith("#")
    ]
    deco_code = "\n".join(code_lines)
    assert 'State("customer-main-tabs"' not in deco_code
    assert "tabs_value" not in inspect.signature(mod.load_customer_view_data).parameters


def test_render_customer_loading_page_has_customer_main_tabs_id():
    from src.pages.customer_view import render_customer_loading_page

    page = render_customer_loading_page("Acme", {"preset": "7d"}, None)
    assert "customer-main-tabs" in _collect_ids(page)


def test_load_customer_view_data_returns_shell_with_ctx():
    from src.pages.customer_view_callbacks import load_customer_view_data

    with patch("src.pages.customer_view_callbacks.ctx") as mock_ctx:
        mock_ctx.triggered_id = "url.search"
        page, store, perspective, active = load_customer_view_data(
            "/customer-view",
            "?customer=Acme%20Corp",
            {"preset": "7d"},
            None,
            None,
            "summary",
        )

    ids = _collect_ids(page)
    assert "customer-view-ctx" in ids
    assert "cust-tab-body-summary" in ids
    assert "customer-main-tabs" in ids
    assert store["customer"] == "Acme Corp"
    assert active == "summary"
    assert perspective in ("manager", "customer")
