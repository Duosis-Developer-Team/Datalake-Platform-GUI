"""Load embedded rule pack and match CRM product display names to page_key (category_code)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _embedded_rules_path() -> Path:
    return Path(__file__).resolve().parent / "embedded_rules.json"


def load_rule_pack(path: Optional[Path] = None) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    p = path or _embedded_rules_path()
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    categories = data.get("categories") or {}
    rules = list(data.get("rules") or [])
    rules.sort(key=lambda r: int(r.get("priority", 999)))
    return categories, rules


def match_product_name(
    product_name: Optional[str],
    *,
    categories: Optional[Dict[str, Any]] = None,
    rules: Optional[List[Dict[str, Any]]] = None,
    pack_path: Optional[Path] = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Return (page_key, meta) where meta includes label, gui_tab_binding, resource_unit.
    page_key matches legacy category_code values used by efficiency_usage.py.
    """
    if categories is None or rules is None:
        categories, rules = load_rule_pack(pack_path)
    name = (product_name or "").strip()
    other_meta = categories.get("other") or {
        "label": "Other / uncategorized",
        "resource_unit": "Adet",
        "gui_tab_binding": "other",
    }
    for rule in rules:
        pat = rule.get("name_regex")
        if not pat:
            continue
        try:
            if re.search(pat, name):
                code = str(rule.get("category_code") or "other")
                meta = dict(categories.get(code) or categories.get("other") or other_meta)
                return code, meta
        except re.error:
            continue
    return "other", dict(other_meta)
