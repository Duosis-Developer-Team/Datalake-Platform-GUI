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
    off a different, smaller number, an arithmetically false sentence.

    2026-08-04: physical free_u may now appear as an explicitly labelled base
    ("of 5,892 free U"), so the guard is no longer "5,892 must not appear
    anywhere" -- it is that the headline value and the price arithmetic both
    read 4,477. That is what was actually wrong before; a labelled base beside
    it says something true."""
    entry = build_colocation_sellable_entry({
        "free_u": 5892, "sellable_free_u": 4477,
        "free_u_potential_tl": 4477 * 10430.84,
        "unit_price_tl": 10430.84, "price_source": "crm",
    })

    texts = _texts(entry)
    assert "4,477 U" in texts
    assert "5,892 U" not in texts
    # The arithmetic caption must cite the same base the TL value came from.
    # Asserted on the numbers rather than a fixed sentence so a rewording does
    # not fail while a wrong base still would.
    assert any("4,477" in t and "10,430.84" in t for t in texts)
    assert not any("5,892" in t and "10,430.84" in t for t in texts)


def _measured_aggregate(**overrides):
    """Measured 2026-08-04 over 188 deduped racks (see allocation.py)."""
    agg = {
        "free_u": 5892, "sellable_free_u": 3611,
        "free_u_potential_tl": 3611 * 10430.84,
        "unit_price_tl": 10430.84, "price_source": "crm",
        "colocation_allocated_u": 2259, "rack_count": 188,
        "network_free_u": 866, "network_capacity_u": 1450, "network_rack_count": 32,
        "role_breakdown": [
            {"role_id": "2", "role_name": "HOST", "sellable": True,
             "rack_count": 107, "capacity_u": 4894, "used_u": 1283, "free_u": 3611},
            {"role_id": "4", "role_name": "CUSTOMER", "sellable": False,
             "rack_count": 42, "capacity_u": 1925, "used_u": 808, "free_u": 1117},
            {"role_id": "1", "role_name": "NETWORK", "sellable": False,
             "rack_count": 32, "capacity_u": 1450, "used_u": 584, "free_u": 866},
            {"role_id": "3", "role_name": "NON-STANDART", "sellable": False,
             "rack_count": 7, "capacity_u": 334, "used_u": 37, "free_u": 297},
        ],
    }
    agg.update(overrides)
    return agg


def test_sellable_free_u_caption_shows_the_physical_base_it_was_cut_from():
    """"outside customer racks" was a static caption that named only half the
    rule and no quantity. The reader has to be able to see, on the tile, that
    3,611 is a subset of a larger physical 5,892."""
    texts = _texts(build_colocation_sellable_entry(_measured_aggregate()))

    assert any("3,611" in t for t in texts)
    assert any("of 5,892 free U" in t for t in texts)


def test_note_itemises_every_excluded_role():
    """Customer rule 2026-08-04: customer AND network cabinets come out. The
    note has to name both -- the previous wording mentioned only colocation
    customers, which would now be an incomplete explanation of the number
    right above it."""
    texts = _texts(build_colocation_sellable_entry(_measured_aggregate()))

    note = next(t for t in texts if "Excluded from sale" in t)
    assert "2,281 U" in note
    assert "1,117 U in CUSTOMER cabinets (42 racks)" in note
    assert "866 U in NETWORK cabinets (32 racks)" in note
    assert "297 U in NON-STANDART cabinets (7 racks)" in note


def test_note_omits_the_exclusion_sentence_when_nothing_was_excluded():
    """A DC with only sellable racks has no subtraction to justify."""
    agg = _measured_aggregate(
        free_u=3611, sellable_free_u=3611, network_free_u=0, network_rack_count=0,
        role_breakdown=[{"role_id": "2", "role_name": "HOST", "sellable": True,
                         "rack_count": 107, "capacity_u": 4894,
                         "used_u": 1283, "free_u": 3611}],
    )
    texts = _texts(build_colocation_sellable_entry(agg))

    assert not any("Excluded from sale" in t for t in texts)
    assert any("Included in Potential Sales" in t for t in texts)


def test_note_still_quantifies_the_exclusion_without_a_role_breakdown():
    agg = _measured_aggregate()
    agg.pop("role_breakdown")
    texts = _texts(build_colocation_sellable_entry(agg))

    note = next(t for t in texts if "Excluded from sale" in t)
    assert "2,281 U" in note
    assert "CUSTOMER" not in note


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
