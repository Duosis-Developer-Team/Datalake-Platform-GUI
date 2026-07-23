from unittest.mock import patch

import dash

from src.pages import licensed_os


def test_build_layout_renders_family_counts():
    fake = {
        "families": {"rhel": 3, "suse": 1, "windows": 5, "free": 10, "unknown": 2},
        "total": 21, "unknown_samples": ["Other Linux (64-bit)"],
    }
    with patch("src.pages.licensed_os.api.get_licensed_os_summary", return_value=fake):
        layout = licensed_os.build_layout()
    # smoke: it builds without error and is a Dash component tree
    assert layout is not None
    assert hasattr(layout, "children")


def test_page_module_exposes_shell_and_layout():
    # both entry points the app.py router relies on must exist and be callable
    assert callable(licensed_os.build_layout_shell)
    assert callable(licensed_os.build_layout)


def test_build_layout_populates_customer_select():
    fake = {
        "families": {"rhel": 3, "suse": 1, "windows": 5, "free": 10, "unknown": 2},
        "total": 21, "unknown_samples": [],
    }
    with patch("src.pages.licensed_os.api.get_licensed_os_summary", return_value=fake), \
         patch("src.pages.licensed_os.api.get_customer_list", return_value=["Acme A.S."]):
        layout = licensed_os.build_layout()
    selects = [c for c in layout.children if getattr(c, "id", None) == "licensed-os-customer-select"]
    assert len(selects) == 1
    assert selects[0].data == [{"value": "Acme A.S.", "label": "Acme A.S."}]


def test_reconciliation_callback_guards_empty_selection():
    assert licensed_os._fill_licensed_os_reconciliation(None) is dash.no_update
    assert licensed_os._fill_licensed_os_reconciliation("") is dash.no_update


def _extract_texts(node) -> list[str]:
    """Flatten a Dash component tree into the list of raw text leaves it renders."""
    children = getattr(node, "children", None)
    if isinstance(children, str):
        return [children]
    if isinstance(children, (list, tuple)):
        out: list[str] = []
        for c in children:
            out.extend(_extract_texts(c))
        return out
    if children is not None:
        return _extract_texts(children)
    return []


def test_reconciliation_callback_renders_leakage_row():
    fake_summary = {
        "families": {"rhel": 10, "suse": 0, "windows": 0, "free": 0, "unknown": 0},
        "total": 10, "unknown_samples": [],
    }
    # Real CRM row shape from customer-api: category_code (not page_key) + sold_qty (not entitled_qty).
    sold_rows = [{"category_code": "license_redhat", "sold_qty": 4}]
    with patch("src.pages.licensed_os.api.get_licensed_os_summary", return_value=fake_summary), \
         patch("src.pages.licensed_os.api.get_customer_efficiency_by_category", return_value=sold_rows):
        table_card = licensed_os._fill_licensed_os_reconciliation("Acme A.S.")

    texts = _extract_texts(table_card)

    assert "Acme A.S." in texts
    assert "RHEL" in texts
    assert "10" in texts  # detected
    assert "4" in texts   # sold
    assert "+6" in texts  # delta = detected - sold, positive = leakage
