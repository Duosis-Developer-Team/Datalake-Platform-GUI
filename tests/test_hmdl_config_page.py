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


def _by_id(layout, pattern_id):
    """Find a node whose id matches the given pattern-matching id dict."""
    for n in _walk(layout):
        if getattr(n, "id", None) == pattern_id:
            return n
    return None


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

    # rendered state must actually reflect the mocked extra_vars, not just
    # the presence of the id
    dry_run_switch = _by_id(layout, {"type": "hmdlcfg-bool", "key": "dry_run"})
    assert isinstance(dry_run_switch, dmc.Switch)
    assert dry_run_switch.checked is True

    device_limit_input = _by_id(layout, {"type": "hmdlcfg-val", "key": "device_limit"})
    assert isinstance(device_limit_input, dmc.NumberInput)
    assert device_limit_input.value == 7

    device_source_select = _by_id(layout, {"type": "hmdlcfg-val", "key": "device_source"})
    assert isinstance(device_source_select, dmc.Select)
    assert device_source_select.value == "loki"


def test_mail_recipients_renders_as_csv_textinput_seeded_from_list():
    with patch.object(page.api, "get_hmdl_awx_config",
                      return_value={"awx_available": True,
                                    "extra_vars": {"mail_recipients": ["a@b.c", "d@e.f"]},
                                    "schedules": []}):
        layout = page.build_layout()
    mail_field = _by_id(layout, {"type": "hmdlcfg-val", "key": "mail_recipients"})
    assert isinstance(mail_field, dmc.TextInput)
    assert "a@b.c" in mail_field.value
    assert "d@e.f" in mail_field.value


def test_field_specs_cover_whitelist():
    keys = [f["key"] for f in page.FIELD_SPECS]
    assert len(keys) == len(set(keys))
    assert "dry_run" in keys and "device_source" in keys and "mail_recipients" in keys
