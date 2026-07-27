"""Colocation per-U price resolution: webui override wins over the CRM price
level; an unresolved price is None (never 0.0), because 0 reads as 'no
opportunity' while None reads as 'price unknown'."""
from unittest.mock import MagicMock

from app.services.colocation_price_service import (
    COLOCATION_PRODUCT_ID,
    potential_tl,
    resolve_colocation_unit_price,
)


def _webui(rows):
    w = MagicMock()
    w.is_available = True
    w.run_rows.return_value = rows
    return w


def _cursor(rows):
    cur = MagicMock()
    cur.fetchall.return_value = rows
    return cur


def test_override_wins_over_crm_price_level():
    cur = _cursor([(10430.84,)])
    webui = _webui([{"unit_price_tl": 9000.0}])

    price, source = resolve_colocation_unit_price(cur, webui)

    assert price == 9000.0
    assert source == "override"


def test_falls_back_to_crm_price_level_when_no_override():
    cur = _cursor([(10430.84,)])
    webui = _webui([])

    price, source = resolve_colocation_unit_price(cur, webui)

    assert price == 10430.84
    assert source == "crm"


def test_unresolved_price_is_none_not_zero():
    cur = _cursor([])
    webui = _webui([])

    price, source = resolve_colocation_unit_price(cur, webui)

    assert price is None
    assert source == "unavailable"


def test_webui_unavailable_falls_through_to_crm():
    cur = _cursor([(10430.84,)])
    webui = MagicMock()
    webui.is_available = False

    price, source = resolve_colocation_unit_price(cur, webui)

    assert price == 10430.84
    assert source == "crm"


def test_webui_failure_does_not_break_resolution():
    cur = _cursor([(10430.84,)])
    webui = MagicMock()
    webui.is_available = True
    webui.run_rows.side_effect = RuntimeError("webui down")

    price, source = resolve_colocation_unit_price(cur, webui)

    assert price == 10430.84
    assert source == "crm"


def test_datalake_failure_yields_unavailable():
    cur = MagicMock()
    cur.execute.side_effect = RuntimeError("datalake down")
    webui = _webui([])

    price, source = resolve_colocation_unit_price(cur, webui)

    assert price is None
    assert source == "unavailable"


def test_zero_override_is_honoured_as_zero_not_treated_as_missing():
    # A deliberate 0.0 override means "free"; it must not silently fall through.
    cur = _cursor([(10430.84,)])
    webui = _webui([{"unit_price_tl": 0.0}])

    price, source = resolve_colocation_unit_price(cur, webui)

    assert price == 0.0
    assert source == "override"


def test_product_id_is_the_per_u_colocation_product():
    assert COLOCATION_PRODUCT_ID == "ee635018-5c6d-f011-b4cc-6045bd93381c"


def test_potential_tl_multiplies_u_by_price():
    assert potential_tl(85, 10430.84) == 85 * 10430.84


def test_potential_tl_is_none_when_price_is_none():
    assert potential_tl(85, None) is None


def test_potential_tl_handles_zero_and_missing_u():
    assert potential_tl(0, 10430.84) == 0.0
    assert potential_tl(None, 10430.84) == 0.0
