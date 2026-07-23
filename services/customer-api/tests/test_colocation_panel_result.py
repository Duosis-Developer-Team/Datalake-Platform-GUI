"""dc_hosting_u yields sellable = max(capacity*0.80 - used, 0), unit U, not
ratio-bound (resource_kind='other'). Uses the canned-total fixture pattern
mirrored from `_build_service()` in test_sellable_service.py."""
from unittest.mock import MagicMock

from app.services.sellable_service import SellableService
from shared.sellable.models import InfraSource, PanelDefinition
from shared.sellable.computation import apply_threshold


def _service() -> SellableService:
    customer = MagicMock()
    webui = MagicMock()
    webui.is_available = True
    customer._pool = MagicMock()
    config = MagicMock()
    currency = MagicMock()
    tagging = MagicMock()

    return SellableService(
        customer_service=customer,
        webui=webui,
        config_service=config,
        currency_service=currency,
        tagging_service=tagging,
    )


def test_dc_hosting_u_sellable_formula():
    svc = _service()
    panel = PanelDefinition(
        panel_key="dc_hosting_u", label="DC Barındırma — U", family="dc_hosting",
        resource_kind="other", display_unit="U",
    )
    infra = InfraSource(
        panel_key="dc_hosting_u", dc_code="*",
        source_table="__colocation_occupancy__", total_column="capacity_u",
        allocated_table="__colocation_occupancy__", allocated_column="used_u",
    )
    # Patch every loader so we don't touch the DB (mirrors _build_service()).
    svc.list_panel_defs = lambda: [panel]
    svc.list_unit_conversions = lambda: []
    svc.list_ratios = lambda: []
    svc.get_threshold = lambda pk, kind, dc: 80.0
    svc.get_unit_price_tl = lambda pk: (0.0, False)
    svc.get_infra_source = lambda pk, dc="*": infra
    svc._query_total_allocated = lambda src, dc: (3616.0, 1817.0)  # DC13 verified aggregate
    svc._compute_ytd_sales_tl = lambda: 0.0
    svc._count_unmapped_products = lambda: 0

    result = {p.panel_key: p for p in svc.compute_all_panels(dc_code="DC13")}["dc_hosting_u"]

    expected = apply_threshold(3616.0, 1817.0, 80.0)  # 3616*0.8 - 1817 = 1075.8
    assert round(result.sellable_raw, 1) == round(expected, 1)
    assert result.sellable_constrained == result.sellable_raw  # not ratio-bound
    assert result.display_unit == "U"
    assert result.has_infra_source is True
