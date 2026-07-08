#!/usr/bin/env python3
"""Tests for the Internal (Bulutistan) source mappings page + prefix namespacing."""
from __future__ import annotations

from src.pages.settings.integrations.crm_aliases import build_editor_shell
from src.pages.settings.integrations.crm_internal_aliases import (
    INTERNAL_ACCOUNT_ID,
    INTERNAL_ACCOUNT_NAME,
    PREFIX,
    build_internal_content,
    build_layout,
)
from src.utils.crm_source_mapping_ui import build_editor_state


def _collect_ids(comp, out):
    cid = getattr(comp, "id", None)
    if cid is not None:
        out.append(cid)
    children = getattr(comp, "children", None)
    if children is None:
        return out
    if not isinstance(children, (list, tuple)):
        children = [children]
    for ch in children:
        if hasattr(ch, "children") or hasattr(ch, "id"):
            _collect_ids(ch, out)
    return out


def _id_types(comp) -> set[str]:
    types: set[str] = set()
    for cid in _collect_ids(comp, []):
        if isinstance(cid, dict):
            types.add(str(cid.get("type")))
        else:
            types.add(str(cid))
    return types


def test_build_layout_has_page_root():
    layout = build_layout()
    assert "internal-alias-page-root" in _id_types(layout)


def test_internal_content_uses_internal_prefix_ids():
    alias = {
        "crm_accountid": INTERNAL_ACCOUNT_ID,
        "crm_account_name": INTERNAL_ACCOUNT_NAME,
        "source_mappings": [
            {"data_source": "virtualization", "match_method": "contains", "match_value": "Bulutistan", "enabled": True},
        ],
        "notes": "",
        "source": "internal",
    }
    content = build_internal_content(alias)
    types = _id_types(content)
    # Namespaced editor + page stores present
    assert any(t.startswith(f"{PREFIX}-edit") for t in types), types
    assert "internal-alias-editor-state" in types
    assert "internal-alias-editor-open-sections" in types
    assert "internal-alias-editor-panel" in types
    assert "internal-alias-feedback" in types
    # Never leaks the plain customer-aliases ids
    assert not any(t.startswith("alias-edit") for t in types), types


def test_internal_content_defaults_to_empty_editor():
    content = build_internal_content(None)
    types = _id_types(content)
    assert "internal-alias-editor-state" in types
    assert any(t.startswith(f"{PREFIX}-edit") for t in types)


def test_prefix_editor_ids_are_disjoint_from_default():
    st = build_editor_state({"crm_accountid": "X", "crm_account_name": "X", "source_mappings": []})
    default_types = _id_types(build_editor_shell(st))  # prefix="alias"
    internal_types = _id_types(build_editor_shell(st, prefix=PREFIX))
    assert any(t.startswith("alias-edit") for t in default_types)
    assert any(t.startswith("internal-alias-edit") for t in internal_types)
    # default page must not emit internal ids, and vice-versa (plain alias-*)
    assert not any(t.startswith("internal-alias") for t in default_types)
    assert not any(
        t.startswith("alias-") and not t.startswith("internal-alias") for t in internal_types
    )
