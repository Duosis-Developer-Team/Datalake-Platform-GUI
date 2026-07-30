# tests/test_floor_map_customer_panel.py
from unittest.mock import patch

from src.pages import floor_map as fm

COLOC = {
    "aggregate": {"total_u": 2629, "used_u": 1169, "free_u": 1460,
                  "rack_count": 214, "unit_price_tl": 10430.84,
                  "free_u_potential_tl": 1000000.0, "price_source": "crm"},
    "allocation": [
        {"customer": "BOYNER", "rack_count": 7, "allocated_u": 312,
         "used_u": 222, "racks": ["104", "105"]},
        {"customer": "Unattributed", "rack_count": 4, "allocated_u": 188,
         "used_u": 90, "racks": ["112", "114"]},
    ],
    "internal": [{"tenant": "BULUTISTAN", "racks": ["201"], "used_u": 40,
                  "potential_tl": 417233.6}],
}


def test_panel_lists_dedicated_customers_with_allocated_u():
    txt = str(fm.build_colocation_customer_panel(COLOC))
    assert "BOYNER" in txt
    assert "312" in txt


def test_money_columns_name_their_basis_like_dc_view():
    # Two same-named "Potential (TL)" columns in one screen is the misread
    # ADR-0028 section 4 exists to prevent.
    txt = str(fm.build_colocation_customer_panel(COLOC))
    assert "Potential (TL) — Allocated" in txt
    assert "Potential (TL) — Used" in txt


def test_unresolved_price_renders_a_dash_not_zero():
    payload = dict(COLOC)
    payload["aggregate"] = dict(COLOC["aggregate"], unit_price_tl=None)
    txt = str(fm.build_colocation_customer_panel(payload))
    assert "—" in txt
    assert "0,00 TL" not in txt


def test_unattributed_carries_the_ambiguity_tooltip():
    txt = str(fm.build_colocation_customer_panel(COLOC))
    assert "Ownership ambiguous in NetBox" in txt


def test_empty_payload_renders_an_explanatory_state_not_a_crash():
    txt = str(fm.build_colocation_customer_panel({}))
    assert "No dedicated" in txt


def test_panel_never_claims_billed_revenue():
    txt = str(fm.build_colocation_customer_panel(COLOC))
    assert "not billed revenue" in txt
    for banned in ("Revenue (TL)", "Billed"):
        assert banned not in txt


def test_internal_resources_are_listed_separately():
    txt = str(fm.build_colocation_customer_panel(COLOC))
    assert "Internal Resources" in txt
    assert "BULUTISTAN" in txt


# ── Permission gating ────────────────────────────────────────────────────
#
# The customer panel carries named customers and TL figures onto a screen
# that otherwise has no permission checks. `build_floor_map_layout` must
# fail closed: the customer panel only appears when the caller explicitly
# asserts `show_colocation=True` (resolved by app.py from
# sec:dc_view:colocation), and a caller that forgets the flag gets the same
# closed behaviour as one that was explicitly denied.

def _build_layout(show_colocation=None):
    kwargs = {} if show_colocation is None else {"show_colocation": show_colocation}
    with patch("src.services.api_client.get_dc_racks_occupancy",
               return_value={"racks": [], "summary": {}}), \
         patch("src.services.api_client.get_colocation",
               return_value=COLOC) as mock_coloc:
        layout = fm.build_floor_map_layout("DC13", "DC13", [], **kwargs)
    return layout, mock_coloc


def test_panel_renders_when_show_colocation_is_true():
    layout, mock_coloc = _build_layout(show_colocation=True)
    txt = str(layout)
    assert "fm-coloc-panel" in txt
    assert "BOYNER" in txt
    assert "Click a rack to inspect" not in txt
    mock_coloc.assert_called_once()


def test_empty_state_renders_when_show_colocation_is_false():
    layout, mock_coloc = _build_layout(show_colocation=False)
    txt = str(layout)
    assert "Click a rack to inspect" in txt
    assert "fm-coloc-panel" not in txt
    assert "BOYNER" not in txt
    # Denied callers shouldn't even pay for the fetch of data they can't see.
    mock_coloc.assert_not_called()


def test_default_flag_is_closed_not_leaking_customer_data():
    # A caller that forgets to pass show_colocation must fail closed, not open.
    layout, mock_coloc = _build_layout(show_colocation=None)
    txt = str(layout)
    assert "Click a rack to inspect" in txt
    assert "fm-coloc-panel" not in txt
    assert "BOYNER" not in txt
    mock_coloc.assert_not_called()
