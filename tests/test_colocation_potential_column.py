"""The colocation tables carry a potential-TL column computed at list price.
The header must not imply billed revenue: no rack allocation currently matches
a CRM colocation contract (verified 2026-07-27).

Phase 2 Task C: the Dedicated Customers table now reads payload["allocation"]
(rack role + tenant/tags/description attribution — see
docs/superpowers/specs/2026-07-27-colocation-allocation-model-design.md)
instead of the old tenancy-only payload["customers"]. Unlike payload["customers"]
and payload["internal"], allocation rows carry NO precomputed potential_tl —
services/customer-api/app/services/colocation_matching_service.py never adds
one (see aggregate_rack_allocations) — so build_colocation_tab must derive it
itself from aggregate["unit_price_tl"]."""
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


def _visible_text(node):
    """Flattened *rendered* text of a node — descends into ``children`` only,
    never into a dmc.Tooltip's ``label`` (that's hover-only content, not what
    a cell actually displays). Used for table-cell text specifically; _texts
    above (which does follow ``label``) stays available for asserting a
    tooltip's own wording elsewhere in this file.
    """
    out = []
    stack = [node]
    while stack:
        n = stack.pop()
        if n is None:
            continue
        if isinstance(n, str):
            out.append(n)
            continue
        children = getattr(n, "children", None)
        if isinstance(children, (list, tuple)):
            stack.extend(children)
        elif children is not None:
            stack.append(children)
    return out


def _table_rows(component):
    """Every dmc.Table body row as a list of its cells' flattened, VISIBLE
    text (a Tooltip's hover-only label is deliberately excluded — see
    _visible_text)."""
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
                cells.append(" ".join(t for t in _visible_text(td)).strip())
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


def _payload(unit_price):
    """unit_price is the resolved per-U list price, or None when unresolved.
    10430.84 is the measured prod CRM figure (2026-07-27); used here only as a
    test fixture value, per this branch's "literal only in fixtures" rule.

    The Boyner allocation row deliberately gives allocated_u (85) and used_u
    (40) DIFFERENT values: a test asserting the rendered Potential figure
    against 85 * unit_price also proves the column prices Allocated U, not
    Used U — if it priced used_u the same assertion would see 40 * unit_price
    instead and fail.
    """
    free_u_potential = (1550 * unit_price) if unit_price is not None else None
    internal_potential = (15 * unit_price) if unit_price is not None else None
    return {
        "aggregate": {"total_u": 2719, "used_u": 1169, "free_u": 1550,
                      "rack_count": 57, "unit_price_tl": unit_price,
                      "price_source": "crm" if unit_price is not None else "unavailable",
                      "free_u_potential_tl": free_u_potential},
        "allocation": [{"customer": "Boyner", "allocated_u": 85, "used_u": 40,
                        "rack_count": 1, "racks": ["122"]}],
        "internal": [{"tenant": "Bulutistan - Linux TEAM", "racks": ["116"],
                      "used_u": 15, "potential_tl": internal_potential}],
    }


def test_customer_table_has_potential_column_header():
    texts = _texts(build_colocation_tab(_payload(10430.84)))

    assert "Potential (TL)" in texts


def test_customer_potential_value_rendered():
    # fmt_tl is the compact executive formatter: 886,621.4 -> "886.6 Bin TL".
    # 85 (allocated_u) * 10430.84, NOT 40 (used_u) * 10430.84 — see _payload's
    # docstring for why the two U fields are deliberately unequal here.
    rows = _table_rows(build_colocation_tab(_payload(10430.84)))

    boyner = next(r for r in rows if r[0] == "Boyner")
    assert boyner[-1] == "886.6 Bin TL"


def test_internal_table_has_potential_column():
    # Checked against each table's own header row, not a tree-wide occurrence
    # count — a count of 2 would also pass if one table had the header twice
    # and the other had none.
    tab = build_colocation_tab(_payload(10430.84))

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


def test_dedicated_customers_table_has_no_crm_account_or_match_columns():
    # Task B never adds crm_account_name/match_status to allocation rows (the
    # design doc's own worked table confirms none of these customers has a
    # CRM sales record at all) — rendering those columns here would just be a
    # column of em dashes, which the task explicitly says to drop instead.
    tab = build_colocation_tab(_payload(10430.84))
    headers = _table_header_texts(_card_for_title(tab, "Dedicated Customers"))

    assert headers == ["Customer", "Racks", "Allocated U", "Used U", "Potential (TL)"]
    assert "CRM Account" not in headers
    assert "Match" not in headers


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


def test_unattributed_row_is_visible_with_its_own_allocated_and_used_u():
    # Unattributed is the second-largest group in prod (465 U across 10 racks)
    # — it must render as a normal row, not be filtered out of the table.
    payload = _payload(10430.84)
    payload["allocation"] = [
        {"customer": "Boyner", "allocated_u": 312, "used_u": 222,
         "rack_count": 7, "racks": ["122", "123"]},
        {"customer": "Unattributed", "allocated_u": 465, "used_u": 214,
         "rack_count": 10, "racks": ["112", "114", "116", "306"]},
    ]
    rows = _table_rows(build_colocation_tab(payload))

    unattributed = next((r for r in rows if r[0].strip().startswith("Unattributed")), None)
    assert unattributed is not None
    assert "465" in unattributed
    assert "214" in unattributed
    assert "10" in unattributed[1]  # Racks column shows the rack_count


def test_unattributed_tooltip_says_ambiguous_not_unowned():
    # The task is explicit: the tooltip must say ownership is AMBIGUOUS in
    # NetBox (conflicting/missing source rows), never that the rack is
    # unowned — Unattributed racks are real customer footprint, just not
    # nameable from today's NetBox data.
    payload = _payload(10430.84)
    payload["allocation"] = [
        {"customer": "Unattributed", "allocated_u": 465, "used_u": 214,
         "rack_count": 10, "racks": ["112", "114", "116", "306"]},
    ]
    tab = build_colocation_tab(payload)
    tooltip_labels = [
        getattr(n, "label", None)
        for n in _flatten(tab)
        if getattr(n, "label", None) is not None
    ]
    ambiguous_tips = [t for t in tooltip_labels if isinstance(t, str) and "ambiguous" in t.lower()]

    assert ambiguous_tips, "expected an Unattributed tooltip mentioning ambiguous ownership"
    assert any("unowned" not in t.lower() for t in ambiguous_tips)


def _flatten(component):
    out = []
    stack = [component]
    while stack:
        node = stack.pop()
        if node is None or isinstance(node, str):
            continue
        out.append(node)
        children = getattr(node, "children", None)
        if isinstance(children, (list, tuple)):
            stack.extend(children)
        elif children is not None:
            stack.append(children)
    return out
