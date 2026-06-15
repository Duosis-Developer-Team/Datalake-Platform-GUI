"""Domain catalog customer/CRM metric coverage."""

from __future__ import annotations

from app.catalog import domain_catalog
from app.services import tool_orchestrator as orch
from app.services import tool_registry


def test_customer_sales_metric_maps_to_sales_tools():
    md = domain_catalog.match("Boyner satış özeti ve aktif sipariş")
    assert md is not None
    assert md.key == "customer_sales_summary"
    assert "get_customer_sales_summary" in md.primary_tools


def test_customer_itsm_metric_maps_to_itsm_tools():
    md = domain_catalog.match("müşteri ITSM ticket özeti")
    assert md is not None
    assert md.key == "customer_itsm_risk"
    assert "get_customer_itsm_summary" in md.primary_tools


def test_orchestrator_selects_sales_tools_for_customer():
    picks = orch.select_tools(
        "Boyner müşterisi aktif sipariş ve satış",
        None,
    )
    names = [p.tool for p in picks]
    assert "get_customer_sales_summary" in names
    assert "get_customer_sales_active_orders" in names


def test_registry_exposes_new_customer_tools():
    for name in (
        "get_customer_catalog",
        "get_customer_sales_summary",
        "get_customer_sales_active_orders",
        "get_customer_efficiency_by_category",
        "get_customer_resource_compliance",
    ):
        assert tool_registry.get_tool(name) is not None
