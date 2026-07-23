# tests/test_dc_view_colocation_tab.py
"""build_colocation_tab renders KPIs + customer rows; the lazy 'colo' tab is
registered so build_dc_view exposes a dc-tab-colo-root."""
from unittest.mock import patch

from src.pages import dc_view
from src.pages.dc_view import _LAZY_TAB_KEYS, build_colocation_tab, _find_component_by_id


def test_colo_is_a_registered_lazy_tab():
    assert "colo" in _LAZY_TAB_KEYS


def test_build_colocation_tab_renders_kpis_and_customers():
    payload = {
        "aggregate": {"total_u": 3616, "used_u": 1817, "free_u": 1799, "rack_count": 78},
        "customers": [
            {"tenant": "AytemizBank", "crm_account_name": "Aytemiz Bank",
             "match_status": "matched", "racks": ["209"], "used_u": 52, "crm_accountid": "A-1"},
        ],
        "racks": [],
    }
    comp = build_colocation_tab(payload)
    # Renders without error and mentions the free-U and the customer.
    text = str(comp)
    assert "1799" in text or "1,799" in text
    assert "AytemizBank" in text


def test_dc_view_exposes_colo_root_when_eager():
    # build_dc_view always fetches get_dc_details in batch1 regardless of which
    # tab is eager, so it needs a minimally valid payload (meta.name etc.) —
    # every other get_* accessor can safely return {} since only "colo" is eager.
    api_patch = {name: (lambda *a, **k: {}) for name in dir(dc_view.api) if name.startswith("get_")}
    api_patch["get_dc_details"] = lambda dc, tr=None: {
        "meta": {"name": "DC13", "location": "Istanbul"},
        "classic": {"hosts": 1, "cpu_cap": 10, "cpu_used": 5, "mem_cap": 100, "mem_used": 50, "stor_cap": 1, "stor_used": 0.5},
        "hyperconv": {},
        "power": {},
        "energy": {},
        "intel": {"vms": 0},
    }
    api_patch["get_colocation"] = lambda dc: {"aggregate": {"total_u": 0, "used_u": 0, "free_u": 0, "rack_count": 0}, "customers": [], "racks": []}
    with patch.multiple("src.pages.dc_view.api", **api_patch):
        page = dc_view.build_dc_view("DC13", time_range={"preset": "7d"}, eager_tabs=frozenset({"colo"}))
    assert _find_component_by_id(page, "dc-tab-colo-root") is not None
