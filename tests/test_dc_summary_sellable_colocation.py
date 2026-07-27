"""DC Summary carries a Physical — Colocation entry: free rack-U and its TL
value at list price. Distinct from the virtualization families and never
summed into them."""
from unittest.mock import MagicMock, patch

from src.pages import dc_view
from src.pages.dc_summary_sellable import build_colocation_sellable_entry


def _texts(component):
    out = []
    stack = [component]
    while stack:
        node = stack.pop()
        if isinstance(node, str):
            out.append(node)
            continue
        children = getattr(node, "children", None)
        if isinstance(children, (list, tuple)):
            stack.extend(children)
        elif children is not None:
            stack.append(children)
        label = getattr(node, "label", None)
        if isinstance(label, str):
            out.append(label)
    return out


def test_entry_renders_free_u_and_tl():
    entry = build_colocation_sellable_entry(
        {"free_u": 1550, "sellable_free_u": 1550, "free_u_potential_tl": 1550 * 10430.84,
         "unit_price_tl": 10430.84, "price_source": "crm"}
    )

    texts = _texts(entry)
    assert any("Colocation" in t for t in texts)
    assert any("1,550" in t for t in texts)
    assert "16.17 Milyon TL" in texts


def test_entry_shows_sellable_free_u_not_total_free_u():
    """Free U inside a colocation-allocated rack isn't sellable (design
    section 3), so free_u_potential_tl prices sellable_free_u, which can be
    much smaller than total free_u. The on-screen U count and its tooltip
    must both cite the SAME number the TL value was actually computed
    from -- previously this rendered total free_u beside a TL figure priced
    off a different, smaller number, an arithmetically false sentence."""
    entry = build_colocation_sellable_entry({
        "free_u": 5892, "sellable_free_u": 4477,
        "free_u_potential_tl": 4477 * 10430.84,
        "unit_price_tl": 10430.84, "price_source": "crm",
    })

    texts = _texts(entry)
    assert any("4,477" in t for t in texts)
    assert not any("5,892" in t for t in texts)
    # The arithmetic caption must cite the same base the TL value came from.
    # Asserted on the numbers rather than a fixed sentence so a rewording does
    # not fail while a wrong base still would.
    assert any("4,477" in t and "10,430.84" in t for t in texts)


def test_entry_renders_dash_when_price_unresolved():
    entry = build_colocation_sellable_entry(
        {"free_u": 1550, "free_u_potential_tl": None,
         "unit_price_tl": None, "price_source": "unavailable"}
    )

    assert "—" in _texts(entry)


def test_entry_is_none_without_colocation_data():
    assert build_colocation_sellable_entry(None) is None
    assert build_colocation_sellable_entry({}) is None


def _dc_view_api_patch(get_colocation):
    """Blanket-mock every api.get_* the DC view might call (each returns {}),
    with a valid get_dc_details payload and the caller-supplied get_colocation."""
    patched = {name: (lambda *a, **k: {}) for name in dir(dc_view.api) if name.startswith("get_")}
    patched["get_dc_details"] = lambda dc, tr=None: {
        "meta": {"name": "DC13", "location": "Istanbul"},
        "classic": {"hosts": 1, "cpu_cap": 10, "cpu_used": 5, "mem_cap": 100, "mem_used": 50,
                    "stor_cap": 1, "stor_used": 0.5},
        "hyperconv": {}, "power": {}, "energy": {}, "intel": {"vms": 0},
    }
    patched["get_colocation"] = get_colocation
    return patched


def test_colocation_fetched_once_when_summary_eager_and_sellable_visible():
    """Only 'summary' is eager (Physical Inventory is not) and the principal
    can see both the sellable section and Colocation: get_colocation is
    called exactly once, for the Summary sellable entry."""
    mock_colo = MagicMock(return_value={
        "aggregate": {"free_u": 100, "free_u_potential_tl": None,
                      "unit_price_tl": None, "price_source": "unavailable"},
        "customers": [], "racks": [],
    })
    with patch.multiple("src.pages.dc_view.api", **_dc_view_api_patch(mock_colo)):
        dc_view.build_dc_view(
            "DC13", time_range={"preset": "7d"},
            visible_sections=None,  # None => every section visible (backward compatible)
            eager_tabs=frozenset({"summary"}),
        )
    assert mock_colo.call_count == 1


def test_colocation_not_fetched_when_summary_sellable_hidden():
    """Only 'summary' is eager and sub:dc_view:summary:sellable is NOT in the
    principal's visible sections (even though sec:dc_view:colocation is):
    get_colocation must not be called at all."""
    mock_colo = MagicMock(return_value={
        "aggregate": {"free_u": 100, "free_u_potential_tl": None,
                      "unit_price_tl": None, "price_source": "unavailable"},
        "customers": [], "racks": [],
    })
    visible = {
        "sec:dc_view:summary", "sec:dc_view:colocation", "sec:dc_view:phys_inv",
        "sec:dc_view:virtualization", "sec:dc_view:storage", "sec:dc_view:backup",
        "sec:dc_view:network", "sec:dc_view:availability",
        # deliberately excludes "sub:dc_view:summary:sellable"
    }
    with patch.multiple("src.pages.dc_view.api", **_dc_view_api_patch(mock_colo)):
        dc_view.build_dc_view(
            "DC13", time_range={"preset": "7d"},
            visible_sections=visible,
            eager_tabs=frozenset({"summary"}),
        )
    assert mock_colo.call_count == 0
