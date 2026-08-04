"""build_colocation_summary: KPI tiles + a 100% stacked bar (External/Internal/
Untagged) showing where a DC's used rack-U goes. English labels only."""
from src.components.colocation_summary import build_colocation_summary


def test_summary_renders_tiles_bar_and_split_labels():
    agg = {"total_u": 1000, "used_u": 600, "free_u": 400, "rack_count": 10,
           "external_u": 149, "internal_u": 300, "untagged_u": 151,
           "external_customer_count": 5}
    text = str(build_colocation_summary(agg))
    assert "Total U" in text and "600" in text and "Racks" in text
    assert "External 149U (5 customers)" in text
    assert "Internal 300U" in text
    assert "Untagged 151U" in text


def test_summary_hides_bar_when_split_absent():
    text = str(build_colocation_summary({"total_u": 5, "used_u": 0, "free_u": 5, "rack_count": 1}))
    assert "Total U" in text            # tiles still render
    assert "where it goes" not in text  # no bar when split is all zero


def test_summary_customer_count_override():
    agg = {"total_u": 100, "used_u": 60, "free_u": 40, "rack_count": 3,
           "external_u": 20, "internal_u": 25, "untagged_u": 15,
           "external_customer_count": 9}
    text = str(build_colocation_summary(agg, customer_count=2))
    assert "External 20U (2 customers)" in text


def _texts(component):
    """Flatten every dmc.Text/str value in a Dash component tree."""
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


def test_free_u_potential_tile_renders_tl_value():
    agg = {"total_u": 2719, "used_u": 1169, "free_u": 1550, "rack_count": 57,
           "free_u_potential_tl": 1550 * 10430.84, "unit_price_tl": 10430.84,
           "price_source": "crm"}

    texts = _texts(build_colocation_summary(agg))

    assert "Free U Potential" in texts
    assert "16.17 Milyon TL" in texts


def test_free_u_potential_tile_renders_dash_when_price_unresolved():
    agg = {"total_u": 2719, "used_u": 1169, "free_u": 1550, "rack_count": 57,
           "free_u_potential_tl": None, "unit_price_tl": None,
           "price_source": "unavailable"}

    texts = _texts(build_colocation_summary(agg))

    assert "Free U Potential" in texts
    assert "—" in texts
    assert "0 TL" not in texts
    assert any("Colocation unit price unavailable" in t for t in texts)
    assert any("Shown as — rather than 0" in t for t in texts)


def test_free_u_potential_tile_absent_when_price_keys_absent():
    """Fix 2: the Floor Map feeds get_dc_racks_occupancy()["summary"], which
    carries no unit_price_tl/free_u_potential_tl keys at all (no price
    resolution happens on that path). That is "never asked", not "asked and
    unresolved" — the card must render its original four tiles with no
    fifth tile and no false "price unavailable" tooltip."""
    component = build_colocation_summary({"total_u": 10, "used_u": 4, "free_u": 6, "rack_count": 2})
    texts = _texts(component)

    assert "Free U Potential" not in texts
    assert not any("Colocation unit price unavailable" in t for t in texts)
    assert len(component.children[0].children) == 4


def test_free_u_potential_tile_present_when_price_keys_present_and_resolved():
    """Keys present + a resolved price: five tiles, value rendered (DC
    Colocation tab caller)."""
    agg = {"total_u": 10, "used_u": 4, "free_u": 6, "rack_count": 2,
           "unit_price_tl": 100.0, "free_u_potential_tl": 600.0, "price_source": "crm"}
    component = build_colocation_summary(agg)
    texts = _texts(component)

    assert "Free U Potential" in texts
    assert len(component.children[0].children) == 5


def test_free_u_potential_tile_dash_when_price_keys_present_but_none():
    """Keys present but the price resolved to None: five tiles, — rendered,
    and the "unavailable" tooltip is accurate here (the caller did ask)."""
    agg = {"total_u": 10, "used_u": 4, "free_u": 6, "rack_count": 2,
           "unit_price_tl": None, "free_u_potential_tl": None, "price_source": "unavailable"}
    component = build_colocation_summary(agg)
    texts = _texts(component)

    assert "Free U Potential" in texts
    assert "—" in texts
    assert any("Colocation unit price unavailable" in t for t in texts)
    assert len(component.children[0].children) == 5


def test_free_u_potential_tooltip_names_crm_price_source():
    agg = {"total_u": 100, "used_u": 50, "free_u": 50, "rack_count": 2,
           "free_u_potential_tl": 50 * 100.0, "unit_price_tl": 100.0,
           "price_source": "crm"}

    texts = _texts(build_colocation_summary(agg))

    assert any("100.00 TL per U" in t and "CRM price list" in t for t in texts)


def test_free_u_potential_tooltip_names_override_price_source():
    agg = {"total_u": 100, "used_u": 50, "free_u": 50, "rack_count": 2,
           "free_u_potential_tl": 50 * 100.0, "unit_price_tl": 100.0,
           "price_source": "override"}

    texts = _texts(build_colocation_summary(agg))

    assert any("100.00 TL per U" in t and "operator override" in t for t in texts)


def test_free_u_potential_tooltip_prices_sellable_free_u_not_total_free_u():
    """Design section 3: free U inside a colocation-allocated rack isn't
    sellable, so free_u_potential_tl prices sellable_free_u, which can be
    much smaller than the Free U tile's total. The tooltip must cite
    sellable_free_u, not the (larger) Free U tile value -- previously it
    named the Free U tile's number even though the TL figure was priced off
    a different, smaller count."""
    agg = {"total_u": 8603, "used_u": 2711, "free_u": 5892, "rack_count": 188,
           "sellable_free_u": 4477, "free_u_potential_tl": 4477 * 10430.84,
           "unit_price_tl": 10430.84, "price_source": "crm"}

    texts = _texts(build_colocation_summary(agg))

    assert any("4,477 sellable free U x 10,430.84 TL per U" in t for t in texts)
    assert not any("5,892 sellable free U" in t for t in texts)


def test_free_u_potential_tooltip_unresolved_explanation():
    agg = {"total_u": 100, "used_u": 50, "free_u": 50, "rack_count": 2,
           "free_u_potential_tl": None, "unit_price_tl": None}

    texts = _texts(build_colocation_summary(agg))

    assert any("Colocation unit price unavailable" in t for t in texts)


# ── Sellable Free U tile + role breakdown (customer rule 2026-08-04) ─────────
#
# Measured 2026-08-04 over 188 deduped racks: HOST 107 racks / 4,894 U /
# 3,611 free; NETWORK 32 / 1,450 / 866; CUSTOMER 42 / 1,925 / 1,117;
# NON-STANDART 7 / 334 / 297. Used as the fixture below so the assertions read
# against real proportions.

def _measured_agg(**overrides):
    agg = {
        "total_u": 8603, "used_u": 2711, "free_u": 5892, "rack_count": 188,
        "sellable_free_u": 3611,
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


def test_sellable_free_u_tile_renders_alongside_physical_free_u():
    """The customer's complaint was that customer and network cabinets were
    counted as sellable space. The fix removes them from the priced number --
    but the physical Free U tile must keep showing physical reality, or the
    card stops matching what an operator sees on the floor."""
    component = build_colocation_summary(_measured_agg())
    texts = _texts(component)

    assert "Sellable Free U" in texts
    assert "3,611" in texts        # sellable
    assert "5,892" in texts        # physical free, unchanged
    assert "8,603" in texts        # physical total, unchanged


def test_total_u_tile_stays_physical_when_non_sellable_racks_exist():
    """Approved decision: exclusion applies to the sellable/free side only.
    Total U is a physical fact about the DC and is never reduced -- a mutant
    that netted the non-sellable capacity out of it would show 4,894."""
    texts = _texts(build_colocation_summary(_measured_agg()))

    assert "8,603" in texts
    assert "4,894" not in texts


def test_sellable_free_u_tile_absent_when_key_absent():
    """Floor Map path (get_dc_racks_occupancy summary) carries no allocation
    keys at all -- no sellability was ever computed there, so the card must
    not invent a tile whose value would silently equal the physical free U."""
    component = build_colocation_summary(
        {"total_u": 10, "used_u": 4, "free_u": 6, "rack_count": 2}
    )
    texts = _texts(component)

    assert "Sellable Free U" not in texts
    assert len(component.children[0].children) == 4


def test_sellable_free_u_tooltip_names_every_excluded_role_with_numbers():
    """"Shrank by 2,281 U" is not an explanation. The tooltip has to name what
    came out and how much, or the number looks like a regression."""
    texts = _texts(build_colocation_summary(_measured_agg()))

    tip = next(t for t in texts if "3,611 of 5,892 free U" in t)
    assert "2,281 U excluded" in tip
    assert "CUSTOMER 1,117 U (42 racks)" in tip
    assert "NETWORK 866 U (32 racks)" in tip
    assert "NON-STANDART 297 U (7 racks)" in tip


def test_sellable_free_u_tooltip_without_role_breakdown_still_quantifies():
    """A caller that computed sellable_free_u but passes no role_breakdown
    still gets the difference spelled out, just not itemised."""
    agg = _measured_agg()
    agg.pop("role_breakdown")
    texts = _texts(build_colocation_summary(agg))

    tip = next(t for t in texts if "3,611 of 5,892 free U" in t)
    assert "2,281 U" in tip
    assert "CUSTOMER" not in tip


def test_role_breakdown_line_lists_every_role_sellable_first():
    texts = _texts(build_colocation_summary(_measured_agg()))

    assert any("Free U by rack role" in t for t in texts)
    assert "HOST 3,611U (107 racks)" in texts
    assert "CUSTOMER 1,117U (42 racks)" in texts
    assert "NETWORK 866U (32 racks)" in texts
    assert "NON-STANDART 297U (7 racks)" in texts


def test_role_breakdown_line_absent_when_breakdown_absent():
    agg = _measured_agg()
    agg.pop("role_breakdown")
    texts = _texts(build_colocation_summary(agg))

    assert not any("Free U by rack role" in t for t in texts)


def test_role_breakdown_line_absent_when_only_sellable_roles_present():
    """A DC with nothing but HOST racks has nothing to explain -- the line
    exists to justify a subtraction, so with no subtraction it is noise."""
    agg = _measured_agg(
        sellable_free_u=3611, network_free_u=0, network_rack_count=0,
        role_breakdown=[{"role_id": "2", "role_name": "HOST", "sellable": True,
                         "rack_count": 107, "capacity_u": 4894,
                         "used_u": 1283, "free_u": 3611}],
    )
    texts = _texts(build_colocation_summary(agg))

    assert not any("Free U by rack role" in t for t in texts)


def test_sellable_free_u_tile_sits_between_free_u_and_racks():
    """Reading order carries the argument: physical free, then what of it is
    sellable, then the rack count it came from."""
    component = build_colocation_summary(_measured_agg())

    def _tile_label(node):
        # tooltip-wrapped tiles (Sellable Free U, Free U Potential) nest one
        # level deeper than the plain ones
        if getattr(node, "label", None) is not None:
            node = node.children
        return node.children[0].children

    labels = [_tile_label(t) for t in component.children[0].children]

    assert labels == ["Total U", "Used U", "Free U", "Sellable Free U", "Racks"]


def _tile_papers(component):
    """The dmc.Paper of every tile, unwrapping the dmc.Tooltip on the ones
    that carry a tooltip."""
    out = []
    for node in component.children[0].children:
        out.append(node.children if getattr(node, "label", None) is not None else node)
    return out


def test_every_tile_fills_its_grid_cell():
    """dmc.Tooltip renders a wrapper element, so the tooltip-carrying tiles
    (Sellable Free U, Free U Potential) are one level below the grid item and
    size to their content instead of filling the cell. Both axes go wrong:
    a Sellable Free U tile a third the width of its neighbours, and heights
    that stagger whenever one value wraps. Pinning every Paper to the full
    cell makes the tooltip and non-tooltip tiles indistinguishable."""
    component = build_colocation_summary(
        _measured_agg(unit_price_tl=10430.84, free_u_potential_tl=3611 * 10430.84,
                      price_source="crm")
    )

    papers = _tile_papers(component)
    assert len(papers) == 6
    assert all(getattr(p, "h", None) == "100%" for p in papers)
    assert all(getattr(p, "w", None) == "100%" for p in papers)


def test_tooltip_wrapper_is_stretched_not_just_the_paper_inside_it():
    """The Paper's own w/h are not enough on a tooltip tile, and measuring the
    rendered page is the only way to see why: dmc.Tooltip renders
    ``<Box w="fit-content">`` around its child, and that Box -- not the Paper --
    is the grid item. A Paper at width:100% of a fit-content parent stays
    fit-content, which is how "Sellable Free U" rendered 120px wide beside a
    318px "Racks" in a grid whose columns were all 318px.

    boxWrapperProps is dmc's escape hatch for exactly this: the component
    merges it OVER its own ``{"w": "fit-content"}`` default, so it is the one
    prop that can undo it. Asserted here rather than on the Paper because the
    Paper assertion above passed throughout the bug."""
    component = build_colocation_summary(
        _measured_agg(unit_price_tl=10430.84, free_u_potential_tl=3611 * 10430.84,
                      price_source="crm")
    )

    tooltips = [n for n in component.children[0].children
                if getattr(n, "label", None) is not None]
    assert len(tooltips) == 2, "Sellable Free U and Free U Potential carry tips"
    for tip in tooltips:
        assert tip.boxWrapperProps == {"w": "100%", "h": "100%"}


def test_tile_grid_wraps_instead_of_narrowing_each_tile():
    """One column per tile put six tiles across the DC shell's ~985px of
    content, ~150px each -- narrow enough to wrap '4.26 Milyon TL' onto a
    second line. The strip must cap its columns and wrap into a second row
    instead, and must never widen past three however many tiles there are:
    SimpleGrid's breakpoints read the viewport, which cannot see that the
    sidebar has already taken ~340px of it."""
    grid = build_colocation_summary(_measured_agg()).children[0]

    assert isinstance(grid.cols, dict)
    assert max(grid.cols.values()) == 3
    assert grid.cols["base"] < grid.cols["sm"]
