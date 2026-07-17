"""Smoke tests for Customer View loading shell."""

from __future__ import annotations


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


def _find_by_id(component, target_id: str):
    for node in _walk(component):
        if getattr(node, "id", None) == target_id:
            return node
    return None


def test_build_customer_loading_shell_has_skeleton_and_dots():
    from src.components.customer_loading import build_customer_loading_shell

    shell = build_customer_loading_shell("Acme Corp")
    assert shell is not None
    text = str(shell)
    assert "building-reveal-dots" in text
    assert "customer-load-shimmer" in text or "Skeleton" in text


def test_build_customer_tab_loading_shell_has_skeleton_not_dot_loading():
    from src.components.customer_loading import build_customer_tab_loading_shell

    shell = build_customer_tab_loading_shell("backup", "Acme Corp")
    assert shell is not None
    text = str(shell)
    assert "building-reveal-dots" in text
    assert 'type="dot"' not in text
    assert "Loading backup data" in text


def test_build_customer_layout_shell_has_static_skeleton_inside_page_root():
    from src.pages.customer_view import build_customer_layout_shell

    layout = build_customer_layout_shell(
        ["p"], selected_customer="Acme Corp", time_range={"preset": "7d"}
    )
    ids = _collect_ids(layout)
    assert "customer-view-page-root" in ids
    assert "customer-loading-status" in ids
    assert "customer-loading-stage-interval" in ids
    assert "customer-view-active-tab" in ids

    page_root = _find_by_id(layout, "customer-view-page-root")
    assert page_root is not None
    root_ids = _collect_ids(page_root)
    # Status bar + interval live INSIDE page-root so they unmount with content swap.
    assert "customer-loading-status" in root_ids
    assert "customer-loading-stage-interval" in root_ids
    assert "customer-loading-layer" in root_ids or "building-reveal-dots" in str(page_root)
    # DC parity: loading Tabs must expose customer-main-tabs so State deps exist.
    assert "customer-main-tabs" in root_ids

    text = str(layout)
    assert 'type="circle"' not in text
    assert 'type="dot"' not in text


def test_render_customer_shell_tab_placeholders_use_loading_shell():
    from src.pages.customer_view import render_customer_shell

    shell = render_customer_shell("Acme Corp", {"preset": "7d"}, None)
    text = str(shell)
    assert "cust-tab-body-summary" in text
    assert "building-reveal-dots" in text
    assert 'type="dot"' not in text
    assert "customer-main-tabs" in text


def test_resolve_customer_active_tab_preserves_on_time_range():
    from src.pages.customer_view import resolve_customer_active_tab

    active = resolve_customer_active_tab(
        triggered_id="app-time-range",
        prev_customer="Acme",
        new_customer="Acme",
        tabs_value="backup",
        stored_tab="summary",
    )
    assert active == "backup"


def test_resolve_customer_active_tab_resets_on_customer_change():
    from src.pages.customer_view import resolve_customer_active_tab

    active = resolve_customer_active_tab(
        triggered_id="url.search",
        prev_customer="Acme",
        new_customer="Boyner",
        tabs_value="backup",
        stored_tab="backup",
    )
    assert active == "summary"


def test_build_customer_layout_without_customer_shows_catalog_link():
    from src.pages.customer_view import build_customer_layout

    layout = build_customer_layout(selected_customer="")
    text = str(layout)
    assert "Customers catalog" in text or "/customers" in text


def test_build_customer_layout_with_customer_has_async_roots():
    from src.pages.customer_view import build_customer_layout

    layout = build_customer_layout(selected_customer="Acme Corp")
    assert layout is not None

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


def test_customer_view_page_root_has_single_initial_writer():
    """No Phase-B skeleton filler racing load_customer_view_data on page-root."""
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    cv_src = (root / "src" / "pages" / "customer_view.py").read_text(encoding="utf-8")
    cb_src = (root / "src" / "pages" / "customer_view_callbacks.py").read_text(encoding="utf-8")

    assert "def _fill_customer_view_content" not in cv_src

    tree = ast.parse(cb_src)
    load_fn = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "load_customer_view_data":
            load_fn = node
            break
    assert load_fn is not None

    # Decorator must include a plain (non-duplicate) Output for page-root children.
    deco_src = ast.get_source_segment(cb_src, load_fn.decorator_list[0]) or ""
    assert 'Output("customer-view-page-root", "children")' in deco_src
    assert 'Output("customer-view-page-root", "children", allow_duplicate=True)' not in deco_src
    assert "prevent_initial_call=False" in deco_src or "prevent_initial_call" not in deco_src
