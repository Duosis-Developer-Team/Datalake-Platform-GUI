"""The auranotify section renders a searchable Select fed by AuraNotify options."""
from __future__ import annotations

from unittest.mock import patch

import dash_mantine_components as dmc

from src.pages.settings.integrations import crm_aliases


def _find(component, predicate):
    """Depth-first search over a Dash component tree."""
    if predicate(component):
        return component
    children = getattr(component, "children", None)
    if children is None:
        return None
    if not isinstance(children, (list, tuple)):
        children = [children]
    for child in children:
        if hasattr(child, "children") or hasattr(child, "id"):
            found = _find(child, predicate)
            if found is not None:
                return found
    return None


def test_auranotify_row_uses_searchable_select_with_options():
    opts = [{"label": "4a_Kozmetik · id 1498", "value": "1498"}]
    crm_aliases._AURANOTIFY_OPTIONS_CACHE = None  # reset memoised options so the patch is used
    with patch.object(crm_aliases.api, "get_auranotify_customer_options", return_value=opts):
        entry = {"data_source": "auranotify", "match_method": "id_exact", "match_value": "1498", "enabled": True}
        row = crm_aliases._render_mapping_entry("auranotify", ("auranotify",), entry, 0)

    def is_value_select(c):
        cid = getattr(c, "id", None)
        return isinstance(c, dmc.Select) and isinstance(cid, dict) and cid.get("type") == "alias-edit-value"

    sel = _find(row, is_value_select)
    assert sel is not None, "auranotify value control must be a dmc.Select"
    assert getattr(sel, "searchable", False) is True
    assert sel.data == opts
    assert sel.value == "1498"


def test_non_auranotify_row_keeps_text_input():
    entry = {"data_source": "virtualization", "match_method": "contains", "match_value": "Boyner", "enabled": True}
    row = crm_aliases._render_mapping_entry("virtualization", ("virtualization",), entry, 0)

    def is_value_textinput(c):
        cid = getattr(c, "id", None)
        return isinstance(c, dmc.TextInput) and isinstance(cid, dict) and cid.get("type") == "alias-edit-value"

    assert _find(row, is_value_textinput) is not None
