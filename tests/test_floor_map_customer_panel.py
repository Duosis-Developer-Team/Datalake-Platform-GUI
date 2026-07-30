# tests/test_floor_map_customer_panel.py
from types import SimpleNamespace
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
    # `internal` is emptied for this payload: its potential_tl is a
    # precomputed value on the row, independent of aggregate["unit_price_tl"]
    # -- left populated, BULUTISTAN's real "417.2 Bin TL" would satisfy (and
    # mask a failure of) the money-figure assertions below for a reason that
    # has nothing to do with what this test exists to catch (the Dedicated
    # Customers table's own price resolution).
    payload = dict(COLOC)
    payload["aggregate"] = dict(COLOC["aggregate"], unit_price_tl=None)
    payload["internal"] = []
    txt = str(fm.build_colocation_customer_panel(payload))
    assert "—" in txt
    # An unresolved price must never surface as ANY formatted money figure:
    # not fmt_tl's actual zero rendering ("0 TL" -- fmt_tl never emits
    # "0,00 TL", so asserting its absence alone could never fail), and not a
    # stale/coincidental Milyon or Bin figure either.
    for banned in ("Milyon TL", "Bin TL", "0 TL"):
        assert banned not in txt

    # Positive control: with the price resolved, BOYNER's real Allocated-U
    # potential (312 * 10430.84 = 3,254,422.08 -> "3.25 Milyon TL") DOES
    # appear, proving the assertions above catch a genuine absence of money
    # rather than the panel simply never rendering any TL figure at all.
    resolved_txt = str(fm.build_colocation_customer_panel(COLOC))
    assert "3.25 Milyon TL" in resolved_txt


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


# ── app.py: _resolve_show_colocation (fix round 1, item 1) ─────────────────
#
# The three tests above only exercise build_floor_map_layout's flag; they say
# nothing about the code that actually DECIDES the flag
# (app.py:_resolve_show_colocation). A typo'd permission code, or a flipped
# `in`/`not in`, would leave every test above green while either hiding the
# panel from every entitled user or leaking it to every unentitled one. These
# tests exercise the resolver's five branches directly.

def test_resolve_show_colocation_true_when_auth_disabled():
    import app as app_module

    with patch("src.auth.config.AUTH_DISABLED", True):
        assert app_module._resolve_show_colocation() is True


def test_resolve_show_colocation_false_when_no_resolvable_user_id():
    import app as app_module

    with patch("src.auth.config.AUTH_DISABLED", False), \
         patch("flask.has_request_context", return_value=True), \
         patch("flask.g", SimpleNamespace()):  # no auth_user_id attribute
        assert app_module._resolve_show_colocation() is False


def test_resolve_show_colocation_true_when_permission_present():
    import app as app_module

    with patch("src.auth.config.AUTH_DISABLED", False), \
         patch("flask.has_request_context", return_value=True), \
         patch("flask.g", SimpleNamespace(auth_user_id=7)), \
         patch("src.auth.permission_service.get_visible_sections",
               return_value={"sec:dc_view:colocation", "sec:dc_view:network"}):
        assert app_module._resolve_show_colocation() is True


def test_resolve_show_colocation_false_when_permission_absent():
    import app as app_module

    with patch("src.auth.config.AUTH_DISABLED", False), \
         patch("flask.has_request_context", return_value=True), \
         patch("flask.g", SimpleNamespace(auth_user_id=7)), \
         patch("src.auth.permission_service.get_visible_sections",
               return_value={"sec:dc_view:network"}):
        assert app_module._resolve_show_colocation() is False


def test_resolve_show_colocation_false_when_lookup_raises():
    import app as app_module

    with patch("src.auth.config.AUTH_DISABLED", False), \
         patch("flask.has_request_context", return_value=True), \
         patch("flask.g", SimpleNamespace(auth_user_id=7)), \
         patch("src.auth.permission_service.get_visible_sections",
               side_effect=RuntimeError("db down")):
        assert app_module._resolve_show_colocation() is False


# ── app.py: show_rack_detail tenant badges (fix round 1, item 3) ───────────
#
# show_rack_detail renders dedicated-customer name badges (no TL figures,
# but still commercial identity) into the same floor-map-rack-detail column
# Task 6 just gated. Left ungated, a user without sec:dc_view:colocation
# could learn a customer's name by clicking a rack instead of reading the
# panel -- making the panel's gate decorative. This predates Task 6
# (commit 47068045) and is not a regression introduced here, but the gate is
# closed now that the hole beside it has been identified.

def _rack_click_data(rack_name="104"):
    # Matches show_rack_detail's 8-field unpack: rack_id, name, status,
    # u_height, power, hall, rack_type, serial.
    customdata = ["R1", rack_name, "active", 47, "220V", "DH7", "Cabinet", "SN1"]
    return {"points": [{"customdata": customdata}]}


def test_show_rack_detail_omits_tenant_badges_when_resolver_denies():
    import app as app_module

    with patch.object(app_module, "api") as mock_api, \
         patch.object(app_module, "_resolve_show_colocation", return_value=False):
        mock_api.get_rack_devices.return_value = {"devices": []}
        mock_api.get_dc_racks_occupancy.return_value = {
            "racks": [{"rack_name": "104", "tenants": ["BOYNER"]}]
        }
        result = app_module.show_rack_detail(_rack_click_data(), {"dc_id": "DC13"})

    txt = str(result)
    assert "BOYNER" not in txt
    # A denied caller shouldn't even trigger the occupancy/tenant lookup.
    mock_api.get_dc_racks_occupancy.assert_not_called()


def test_show_rack_detail_shows_tenant_badges_when_resolver_allows():
    import app as app_module

    with patch.object(app_module, "api") as mock_api, \
         patch.object(app_module, "_resolve_show_colocation", return_value=True):
        mock_api.get_rack_devices.return_value = {"devices": []}
        mock_api.get_dc_racks_occupancy.return_value = {
            "racks": [{"rack_name": "104", "tenants": ["BOYNER"]}]
        }
        result = app_module.show_rack_detail(_rack_click_data(), {"dc_id": "DC13"})

    txt = str(result)
    assert "BOYNER" in txt
