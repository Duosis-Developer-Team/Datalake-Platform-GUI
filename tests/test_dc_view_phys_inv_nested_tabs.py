"""Colocation renders as a Physical Inventory sub-tab, not a top-level tab."""
from unittest.mock import patch

from src.pages import dc_view


def _tab_values(component):
    """Collect every dmc.TabsTab `value` in a Dash component tree."""
    out = []
    stack = [component]
    while stack:
        node = stack.pop()
        if node is None or isinstance(node, str):
            continue
        if type(node).__name__ == "TabsTab":
            value = getattr(node, "value", None)
            if value:
                out.append(value)
        children = getattr(node, "children", None)
        if isinstance(children, (list, tuple)):
            stack.extend(children)
        elif children is not None:
            stack.append(children)
    return out


def test_phys_inv_subtab_values():
    panel = dc_view._build_phys_inv_tab_content(
        phys_inv={}, coloc={}, show_overview=True, show_colo=True,
    )

    values = _tab_values(panel)
    assert "phys-overview" in values
    assert "phys-colo" in values


def test_colocation_subtab_hidden_without_permission():
    panel = dc_view._build_phys_inv_tab_content(
        phys_inv={}, coloc={}, show_overview=True, show_colo=False,
    )

    assert "phys-colo" not in _tab_values(panel)


def test_overview_subtab_hidden_without_permission():
    panel = dc_view._build_phys_inv_tab_content(
        phys_inv={}, coloc={}, show_overview=False, show_colo=True,
    )

    values = _tab_values(panel)
    assert "phys-overview" not in values
    assert "phys-colo" in values


# ---------------------------------------------------------------------------
# Permission derivation in build_dc_view itself (dc_view.py ~5188-5541).
#
# The tests above exercise _build_phys_inv_tab_content directly with
# hand-passed show_overview / show_colo booleans — they never touch the
# derivation of those booleans from `visible_sections`, which is where the
# entire risk of the legacy-grant guarantee lives. These tests call the real
# build_dc_view() so a regression in that derivation (e.g. someone deleting
# "or show_colo") is caught by the committed suite, not just an ad hoc script.
#
# build_dc_view has two different formulas for show_phys depending on
# whether eager_tabs is None:
#   - eager_tabs is None (the "non-eager" / full-build path, used when a
#     caller doesn't restrict which tabs to build):
#       show_phys = (has_phys_inv and _sec("sec:dc_view:phys_inv") and show_phys_overview) or show_colo
#   - eager_tabs is not None (the "eager" / production path — dc_view_callbacks.py
#     always passes a non-None eager_tabs when expanding a tab):
#       show_phys = _sec("sec:dc_view:phys_inv") or show_colo
# Both are tested below so a regression in either formula is caught.
# ---------------------------------------------------------------------------


def _patched_api(*, has_phys_inv_data: bool = False):
    """Broad api mock: every get_* returns {} except get_dc_details (needed
    unconditionally by batch1) and, when has_phys_inv_data, get_physical_inventory_dc
    (needed so has_phys_inv is True for the eager_tabs=None formula, which — unlike
    the eager_tabs-not-None formula — still ANDs in has_phys_inv for the
    sec:dc_view:phys_inv-only case)."""
    api_patch = {name: (lambda *a, **k: {}) for name in dir(dc_view.api) if name.startswith("get_")}
    api_patch["get_dc_details"] = lambda dc, tr=None: {
        "meta": {"name": "DC13", "location": "Istanbul"},
        "classic": {"hosts": 1, "cpu_cap": 10, "cpu_used": 5, "mem_cap": 100, "mem_used": 50, "stor_cap": 1, "stor_used": 0.5},
        "hyperconv": {},
        "power": {},
        "energy": {},
        "intel": {"vms": 0},
    }
    api_patch["get_colocation"] = lambda dc: {
        "aggregate": {"total_u": 0, "used_u": 0, "free_u": 0, "rack_count": 0},
        "customers": [],
        "racks": [],
    }
    if has_phys_inv_data:
        api_patch["get_physical_inventory_dc"] = lambda dc_name: {
            "total": 5, "by_role": [], "by_role_manufacturer": [],
        }
    return api_patch


def test_eager_legacy_colo_grant_reaches_phys_inv_and_colo_subtab():
    """Production path (eager_tabs is not None, mirrors dc_view_callbacks.py
    always passing a concrete eager_tabs). A principal holding ONLY the
    legacy sec:dc_view:colocation grant must still reach both the parent
    Physical Inventory tab and the Colocation sub-tab."""
    with patch.multiple("src.pages.dc_view.api", **_patched_api()):
        page = dc_view.build_dc_view(
            "DC13", time_range={"preset": "7d"},
            visible_sections={"sec:dc_view:colocation"},
            eager_tabs=frozenset({"phys-inv"}),
        )
    values = _tab_values(page)
    assert "phys-inv" in values
    assert "phys-colo" in values
    assert "phys-overview" not in values


def test_eager_phys_inv_grant_alone_shows_overview_not_colo():
    """Production path (eager_tabs is not None). A principal holding only
    sec:dc_view:phys_inv (no colocation grant at all) sees Overview but not
    the Colocation sub-tab."""
    with patch.multiple("src.pages.dc_view.api", **_patched_api()):
        page = dc_view.build_dc_view(
            "DC13", time_range={"preset": "7d"},
            visible_sections={"sec:dc_view:phys_inv"},
            eager_tabs=frozenset({"phys-inv"}),
        )
    values = _tab_values(page)
    assert "phys-inv" in values
    assert "phys-overview" in values
    assert "phys-colo" not in values


def test_non_eager_legacy_colo_grant_reaches_phys_inv_and_colo_subtab():
    """Non-eager path (eager_tabs=None, the default full-build formula). A
    principal holding ONLY the legacy sec:dc_view:colocation grant must still
    reach both the parent Physical Inventory tab and the Colocation sub-tab."""
    with patch.multiple("src.pages.dc_view.api", **_patched_api()):
        page = dc_view.build_dc_view(
            "DC13", time_range={"preset": "7d"},
            visible_sections={"sec:dc_view:colocation"},
        )
    values = _tab_values(page)
    assert "phys-inv" in values
    assert "phys-colo" in values
    assert "phys-overview" not in values


def test_non_eager_phys_inv_grant_alone_shows_overview_not_colo():
    """Non-eager path (eager_tabs=None). A principal holding only
    sec:dc_view:phys_inv sees Overview but not the Colocation sub-tab. This
    formula ANDs in has_phys_inv (device data presence), unlike the eager
    formula, so the mock must report non-empty physical inventory data."""
    with patch.multiple("src.pages.dc_view.api", **_patched_api(has_phys_inv_data=True)):
        page = dc_view.build_dc_view(
            "DC13", time_range={"preset": "7d"},
            visible_sections={"sec:dc_view:phys_inv"},
        )
    values = _tab_values(page)
    assert "phys-inv" in values
    assert "phys-overview" in values
    assert "phys-colo" not in values
