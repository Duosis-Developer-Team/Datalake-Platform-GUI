"""Login page layout: Dash 4+ has no html.Input — use dcc.Input (see build_login_layout)."""

from __future__ import annotations

from typing import Any, Iterable


def _walk_children(obj: Any) -> Iterable[Any]:
    if obj is None:
        return
    if isinstance(obj, (list, tuple)):
        for item in obj:
            yield from _walk_children(item)
        return
    yield obj
    ch = getattr(obj, "children", None)
    if ch is not None:
        yield from _walk_children(ch)


def _dcc_inputs(root: Any) -> list[Any]:
    out: list[Any] = []
    for node in _walk_children(root):
        ns = getattr(node, "_namespace", None)
        if ns == "dash_core_components" and type(node).__name__ == "Input":
            out.append(node)
    return out


def test_build_login_layout_uses_dcc_input_not_html_input():
    from dash import html

    from src.pages.login import build_login_layout

    layout = build_login_layout("/", error=False)
    inputs = _dcc_inputs(layout)
    assert len(inputs) >= 3, "expected hidden next + username + password"

    names = []
    for inp in inputs:
        j = inp.to_plotly_json()
        props = j.get("props") or {}
        names.append(props.get("name"))

    assert "next" in names
    assert "username" in names
    assert "password" in names

    assert not hasattr(html, "Input")
