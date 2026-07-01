"""Item 6.1: reusable paginated table. Large VM/LPAR lists render only one page
of rows in the DOM (killing the render bloat) while keeping rich cells (badges,
formatted Td). The full row set lives in a Store; a MATCH callback swaps pages.
"""
from dash import dcc, html

from src.pages import customer_view as cv


def test_page_slice_returns_requested_page():
    rows = list(range(250))
    assert cv._page_slice(rows, 1, page_size=100) == list(range(0, 100))
    assert cv._page_slice(rows, 2, page_size=100) == list(range(100, 200))
    assert cv._page_slice(rows, 3, page_size=100) == list(range(200, 250))


def test_page_slice_handles_empty_and_bad_page():
    assert cv._page_slice([], 1) == []
    assert cv._page_slice([1, 2, 3], 0, page_size=100) == [1, 2, 3]  # clamped to page 1
    assert cv._page_slice([1, 2, 3], None, page_size=100) == [1, 2, 3]


def _walk(node):
    """Yield every component in a Dash tree."""
    yield node
    children = getattr(node, "children", None)
    if isinstance(children, (list, tuple)):
        for c in children:
            yield from _walk(c)
    elif children is not None:
        yield from _walk(children)


def test_paginated_rows_table_dom_holds_only_first_page():
    rows = [html.Tr(html.Td(str(i))) for i in range(250)]
    header = [html.Th("X")]
    comp = cv._paginated_rows_table(header, rows, "vm-classic", page_size=100)

    nodes = list(_walk(comp))
    # The full row set is stored, not rendered.
    stores = [n for n in nodes if isinstance(n, dcc.Store)]
    assert stores and len(stores[0].data) == 250
    # Only the first page is in the rendered Tbody.
    tbodies = [n for n in nodes if isinstance(n, html.Tbody)]
    assert tbodies and len(tbodies[0].children) == 100


def test_paginated_rows_table_pagination_total_pages():
    import dash_mantine_components as dmc

    rows = [html.Tr(html.Td(str(i))) for i in range(250)]
    comp = cv._paginated_rows_table([html.Th("X")], rows, "vm-x", page_size=100)
    pagers = [n for n in _walk(comp) if isinstance(n, dmc.Pagination)]
    assert pagers and pagers[0].total == 3  # ceil(250/100)
