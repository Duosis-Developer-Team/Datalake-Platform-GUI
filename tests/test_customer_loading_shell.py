"""Smoke tests for Customer View loading shell."""

from __future__ import annotations


def test_build_customer_loading_shell_has_status_and_skeleton():
    from src.components.customer_loading import build_customer_loading_shell

    shell = build_customer_loading_shell("Acme Corp")
    assert shell is not None

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

    ids = set()
    for node in _walk(shell):
        node_id = getattr(node, "id", None)
        if node_id:
            ids.add(node_id)

    assert "customer-loading-status" in ids
    assert "customer-loading-stage-interval" in ids


def test_build_customer_layout_without_customer_shows_catalog_link():
    from src.pages.customer_view import build_customer_layout

    layout = build_customer_layout(selected_customer="")
    text = str(layout)
    assert "Customers catalog" in text or "/customers" in text


def test_build_customer_layout_with_customer_has_async_roots():
    from src.pages.customer_view import build_customer_layout

    layout = build_customer_layout(selected_customer="Acme Corp")
    assert layout is not None

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

    string_ids = set()
    for node in _walk(layout):
        node_id = getattr(node, "id", None)
        if node_id is None or isinstance(node_id, dict):
            continue
        string_ids.add(node_id)

    assert "customer-view-page-root" in string_ids
    assert "customer-export-store" in string_ids
    assert "customer-view-visible-sections" in string_ids
    assert "customer-export-toolbar" in string_ids
    assert "customer-export-csv" in str(layout)
