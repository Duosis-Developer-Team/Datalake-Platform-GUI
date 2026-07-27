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
    assert component.children[0].cols == 4


def test_free_u_potential_tile_present_when_price_keys_present_and_resolved():
    """Keys present + a resolved price: five tiles, value rendered (DC
    Colocation tab caller)."""
    agg = {"total_u": 10, "used_u": 4, "free_u": 6, "rack_count": 2,
           "unit_price_tl": 100.0, "free_u_potential_tl": 600.0, "price_source": "crm"}
    component = build_colocation_summary(agg)
    texts = _texts(component)

    assert "Free U Potential" in texts
    assert component.children[0].cols == 5


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
    assert component.children[0].cols == 5


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


def test_free_u_potential_tooltip_unresolved_explanation():
    agg = {"total_u": 100, "used_u": 50, "free_u": 50, "rack_count": 2,
           "free_u_potential_tl": None, "unit_price_tl": None}

    texts = _texts(build_colocation_summary(agg))

    assert any("Colocation unit price unavailable" in t for t in texts)
