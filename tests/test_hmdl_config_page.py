"""Smoke + behavior tests for the HMDL configuration page."""

from unittest.mock import patch

import dash_mantine_components as dmc
from dash import html

from src.pages.settings.integrations import hmdl_config as page


def _walk(node):
    yield node
    children = getattr(node, "children", None)
    if children is None:
        return
    if not isinstance(children, (list, tuple)):
        children = [children]
    for c in children:
        yield from _walk(c)


def _ids(layout):
    out = []
    for n in _walk(layout):
        cid = getattr(n, "id", None)
        if cid is not None:
            out.append(cid)
    return out


def test_layout_renders_banner_when_awx_unavailable():
    with patch.object(page.api, "get_hmdl_awx_config",
                      return_value={"awx_available": False, "extra_vars": {}, "schedules": []}):
        layout = page.build_layout()
    assert isinstance(layout, html.Div)
    # a visible Alert somewhere in the tree
    assert any(isinstance(n, dmc.Alert) for n in _walk(layout))


def test_layout_prefills_fields_from_extra_vars():
    with patch.object(page.api, "get_hmdl_awx_config",
                      return_value={"awx_available": True,
                                    "extra_vars": {"dry_run": True, "device_limit": 7, "device_source": "loki"},
                                    "schedules": []}):
        layout = page.build_layout()
    ids = _ids(layout)
    # value fields and bool fields are addressed by pattern-matching ids
    assert {"type": "hmdlcfg-val", "key": "device_source"} in ids
    assert {"type": "hmdlcfg-bool", "key": "dry_run"} in ids
    assert {"type": "hmdlcfg-val", "key": "device_limit"} in ids


def test_field_specs_cover_whitelist():
    keys = [f["key"] for f in page.FIELD_SPECS]
    assert len(keys) == len(set(keys))
    assert "dry_run" in keys and "device_source" in keys and "mail_recipients" in keys
