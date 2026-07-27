"""The colocation tables carry a potential-TL column computed at list price.
The header must not imply billed revenue: no rack tenant currently matches a
CRM colocation contract (verified 2026-07-27)."""
from src.pages.dc_view import build_colocation_tab


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


def _table_rows(component):
    """Every dmc.Table body row as a list of its cells' flattened text."""
    rows = []
    stack = [component]
    while stack:
        node = stack.pop()
        if node is None or isinstance(node, str):
            continue
        if type(node).__name__ == "Tr":
            cells = []
            for td in (getattr(node, "children", None) or []):
                if type(td).__name__ != "Td":
                    continue
                cells.append(" ".join(t for t in _texts(td)).strip())
            if cells:
                rows.append(cells)
            continue
        children = getattr(node, "children", None)
        if isinstance(children, (list, tuple)):
            stack.extend(children)
        elif children is not None:
            stack.append(children)
    return rows


def _payload(potential):
    return {
        "aggregate": {"total_u": 2719, "used_u": 1169, "free_u": 1550,
                      "rack_count": 57, "unit_price_tl": 10430.84,
                      "price_source": "crm",
                      "free_u_potential_tl": 1550 * 10430.84},
        "customers": [{"tenant": "Boyner", "crm_account_name": None,
                       "match_status": "unmatched", "racks": ["122"],
                       "used_u": 85, "potential_tl": potential}],
        "internal": [{"tenant": "Bulutistan - Linux TEAM", "racks": ["116"],
                      "used_u": 15, "potential_tl": potential}],
    }


def test_customer_table_has_potential_column_header():
    texts = _texts(build_colocation_tab(_payload(85 * 10430.84)))

    assert "Potential (TL)" in texts


def test_customer_potential_value_rendered():
    # fmt_tl is the compact executive formatter: 886,621.4 -> "886.6 Bin TL".
    # Used here so an unresolved price renders "—" through the same function.
    rows = _table_rows(build_colocation_tab(_payload(85 * 10430.84)))

    boyner = next(r for r in rows if r[0] == "Boyner")
    assert boyner[-1] == "886.6 Bin TL"


def test_internal_table_has_potential_column():
    tab = build_colocation_tab(_payload(15 * 10430.84))
    texts = _texts(tab)

    assert texts.count("Potential (TL)") == 2


def test_unresolved_potential_renders_dash_not_zero():
    # Assert the potential CELL specifically, not "no '0' anywhere in the tree" —
    # the tree is full of legitimate numbers and a blanket scan would pass or fail
    # for reasons unrelated to this behaviour.
    tab = build_colocation_tab(_payload(None))
    rows = _table_rows(tab)

    boyner = next(r for r in rows if r[0] == "Boyner")
    assert boyner[-1] == "—"

    internal = next(r for r in rows if r[0] == "Bulutistan - Linux TEAM")
    assert internal[-1] == "—"


def test_header_disclaims_billed_revenue():
    texts = " ".join(_texts(build_colocation_tab(_payload(1.0))))

    assert "list price" in texts.lower()
    assert "not billed" in texts.lower()
