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


def _card_for_title(component, title):
    """Find the "nexus-card" html.Div whose _section_title H3 text equals `title`.

    _section_title() builds html.Div(className="dc-section-title", children=[H3, P|None])
    as the first child of a html.Div(className="nexus-card", ...) card. Locating the
    card this way lets us pull the subtitle or table that belongs to *that specific*
    card, instead of scanning the whole tree (which also holds the summary card's own
    "list price / not billed" tooltip text and the other table's header).
    """
    stack = [component]
    while stack:
        node = stack.pop()
        if node is None or isinstance(node, str):
            continue
        if type(node).__name__ == "Div" and getattr(node, "className", None) == "nexus-card":
            card_children = getattr(node, "children", None) or []
            section_title_div = card_children[0] if card_children else None
            sub_children = getattr(section_title_div, "children", None) or []
            h3 = next((c for c in sub_children if type(c).__name__ == "H3"), None)
            if h3 is not None and getattr(h3, "children", None) == title:
                return node
        children = getattr(node, "children", None)
        if isinstance(children, (list, tuple)):
            stack.extend(children)
        elif children is not None:
            stack.append(children)
    return None


def _subtitle_text(card_div):
    """The subtitle string (the html.P) of a card's _section_title, or None."""
    if card_div is None:
        return None
    section_title_div = (getattr(card_div, "children", None) or [None])[0]
    sub_children = getattr(section_title_div, "children", None) or []
    p = next((c for c in sub_children if type(c).__name__ == "P"), None)
    return getattr(p, "children", None) if p is not None else None


def _table_header_texts(card_div):
    """The flattened Th texts of the dmc.Table header found within a card Div."""
    stack = [card_div]
    while stack:
        node = stack.pop()
        if node is None or isinstance(node, str):
            continue
        if type(node).__name__ == "Thead":
            tr = getattr(node, "children", None)
            if isinstance(tr, (list, tuple)):
                tr = tr[0] if tr else None
            ths = getattr(tr, "children", None) or []
            return [" ".join(_texts(th)).strip() for th in ths if type(th).__name__ == "Th"]
        children = getattr(node, "children", None)
        if isinstance(children, (list, tuple)):
            stack.extend(children)
        elif children is not None:
            stack.append(children)
    return []


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
    # Checked against each table's own header row, not a tree-wide occurrence
    # count — a count of 2 would also pass if one table had the header twice
    # and the other had none.
    tab = build_colocation_tab(_payload(15 * 10430.84))

    customer_headers = _table_header_texts(_card_for_title(tab, "Dedicated Customers"))
    internal_headers = _table_header_texts(_card_for_title(tab, "Internal Resources"))

    assert customer_headers.count("Potential (TL)") == 1
    assert internal_headers.count("Potential (TL)") == 1


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


def test_dedicated_customers_subtitle_discloses_list_price_not_billed():
    # Assert on the specific _section_title subtitle node under the "Dedicated
    # Customers" card, not the whole flattened tree — the tree also contains
    # build_colocation_summary()'s own "Potential at list price — not billed
    # revenue." tooltip text (src/components/colocation_summary.py), which
    # would make a tree-wide scan pass even if this subtitle lost the framing.
    tab = build_colocation_tab(_payload(1.0))
    subtitle = _subtitle_text(_card_for_title(tab, "Dedicated Customers"))

    assert subtitle is not None
    assert "list price" in subtitle.lower()
    assert "not billed" in subtitle.lower()


def test_internal_resources_subtitle_discloses_list_price_not_billed():
    tab = build_colocation_tab(_payload(1.0))
    subtitle = _subtitle_text(_card_for_title(tab, "Internal Resources"))

    assert subtitle is not None
    assert "list price" in subtitle.lower()
    assert "not billed" in subtitle.lower()
