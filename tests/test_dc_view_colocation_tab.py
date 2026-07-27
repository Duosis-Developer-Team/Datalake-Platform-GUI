# tests/test_dc_view_colocation_tab.py
"""build_colocation_tab renders KPIs + customer rows. Colocation is now a
sub-tab of Physical Inventory (see test_dc_view_phys_inv_nested_tabs.py), so
eager-loading it means eager-loading the 'phys-inv' lazy tab, which exposes
dc-tab-phys-inv-root."""
from unittest.mock import patch

from src.pages import dc_view
from src.pages.dc_view import _LAZY_TAB_KEYS, build_colocation_tab, _find_component_by_id


def test_colo_is_a_registered_lazy_tab():
    assert "colo" in _LAZY_TAB_KEYS


def test_build_colocation_tab_renders_kpis_and_customers():
    # Phase 2 Task C: the Dedicated Customers table reads payload["allocation"]
    # (rack role + tenant/tags/description), not the old tenancy-only
    # payload["customers"] — see
    # docs/superpowers/specs/2026-07-27-colocation-allocation-model-design.md.
    payload = {
        "aggregate": {"total_u": 3616, "used_u": 1817, "free_u": 1799, "rack_count": 78},
        "allocation": [
            {"customer": "AytemizBank", "allocated_u": 52, "used_u": 52,
             "rack_count": 1, "racks": ["209"]},
        ],
        "racks": [],
    }
    comp = build_colocation_tab(payload)
    # Renders without error and mentions the free-U and the customer.
    text = str(comp)
    assert "1799" in text or "1,799" in text
    assert "AytemizBank" in text


def test_colocation_tab_english_labels_and_summary():
    payload = {
        "aggregate": {"total_u": 1000, "used_u": 600, "free_u": 400, "rack_count": 10,
                      "external_u": 149, "internal_u": 300, "untagged_u": 151,
                      "external_customer_count": 1},
        "allocation": [
            {"customer": "AytemizBank", "allocated_u": 52, "used_u": 29,
             "rack_count": 1, "racks": ["209"]},
        ],
        "racks": [],
    }
    text = str(build_colocation_tab(payload))
    assert "Dedicated Customers" in text
    assert "Allocated U" in text
    assert "Kolokasyon" not in text and "Müşteri" not in text and "Dedike" not in text
    assert "External 149U" in text        # summary component embedded


def test_colocation_tab_renders_internal_resources_table():
    payload = {
        "aggregate": {"total_u": 1000, "used_u": 600, "free_u": 400, "rack_count": 10,
                      "external_u": 149, "internal_u": 300, "untagged_u": 151,
                      "external_customer_count": 1},
        "customers": [
            {"tenant": "Boyner", "crm_account_name": None, "match_status": "unmatched",
             "racks": ["122"], "used_u": 85},
        ],
        "internal": [
            {"tenant": "Bulutistan - Virtualization", "racks": ["1", "2"], "used_u": 224},
            {"tenant": "Bulutistan - Linux TEAM", "racks": ["3"], "used_u": 121},
        ],
        "racks": [],
    }
    text = str(build_colocation_tab(payload))
    assert "Internal Resources" in text
    assert "Bulutistan - Virtualization" in text and "224" in text
    assert "Resource" in text            # internal table header


def test_dc_view_exposes_colo_root_when_eager():
    # Colocation moved under Physical Inventory (Task 6): it no longer has its
    # own top-level lazy tab, so eager-loading it means eager-loading
    # "phys-inv". build_dc_view always fetches get_dc_details in batch1
    # regardless of which tab is eager, so it needs a minimally valid payload
    # (meta.name etc.) — every other get_* accessor can safely return {}
    # since only "phys-inv" is eager.
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
        page = dc_view.build_dc_view("DC13", time_range={"preset": "7d"}, eager_tabs=frozenset({"phys-inv"}))
    assert _find_component_by_id(page, "dc-tab-phys-inv-root") is not None
