"""
CRM Sales endpoints for the customer-api microservice.

Routes:
  GET /customers/{customer_name}/sales/summary
  GET /customers/{customer_name}/sales/items
  GET /customers/{customer_name}/sales/active-orders
  GET /customers/{customer_name}/sales/active-items
  GET /customers/{customer_name}/sales/efficiency
  GET /customers/{customer_name}/sales/efficiency-by-category
  GET /customers/{customer_name}/sales/resource-compliance
  GET /customers/{customer_name}/sales/catalog-valuation
  GET /customers/{customer_name}/sales/service-breakdown
  GET /crm/aliases
  PUT /crm/aliases/{crm_accountid}
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Request

from app.models.schemas import (
    CatalogValuationRow,
    CustomerAlias,
    CustomerAliasUpdate,
    CustomerAliasWithMappings,
    CustomerServiceSalesSlice,
    CustomerSourceMappingUpdate,
    ResourceComplianceResponse,
    SalesEfficiencyByCategoryRow,
    SalesEfficiencyRow,
    SalesLineItem,
    SalesOrderHeader,
    SalesSummary,
)
from app.services.sales_service import SalesService

router = APIRouter()


def get_sales_service(request: Request) -> SalesService:
    return request.app.state.sales


@router.get("/customers/{customer_name}/sales/summary", response_model=SalesSummary)
def sales_summary(
    customer_name: str,
    svc: SalesService = Depends(get_sales_service),
):
    """YTD realized revenue, order counts, and in-progress orders (pipeline/contracts not in CRM scope)."""
    return svc.get_sales_summary(customer_name)


@router.get("/customers/{customer_name}/sales/items", response_model=List[SalesLineItem])
def sales_items(
    customer_name: str,
    svc: SalesService = Depends(get_sales_service),
):
    """Realized sales-order line items (fulfilled/invoiced) for invoiced orders display."""
    return svc.get_sales_items(customer_name)


@router.get(
    "/customers/{customer_name}/sales/active-orders",
    response_model=List[SalesOrderHeader],
)
def sales_active_orders(
    customer_name: str,
    svc: SalesService = Depends(get_sales_service),
):
    """Open CRM sales order headers (active/submitted) for a customer."""
    return svc.get_active_order_headers(customer_name)


@router.get(
    "/customers/{customer_name}/sales/active-items",
    response_model=List[SalesLineItem],
)
def sales_active_items(
    customer_name: str,
    svc: SalesService = Depends(get_sales_service),
):
    """Open CRM sales order line items (active/submitted) for a customer."""
    return svc.get_active_sales_items(customer_name)


@router.get("/customers/{customer_name}/sales/efficiency", response_model=List[SalesEfficiencyRow])
def sales_efficiency(
    customer_name: str,
    svc: SalesService = Depends(get_sales_service),
):
    """Billed capacity vs catalog unit price — coverage percentage per product."""
    return svc.get_sales_efficiency(customer_name)


@router.get(
    "/customers/{customer_name}/sales/efficiency-by-category",
    response_model=List[SalesEfficiencyByCategoryRow],
)
def sales_efficiency_by_category(
    customer_name: str,
    svc: SalesService = Depends(get_sales_service),
):
    """Realized CRM sales quantities vs observed usage, grouped by product category alias."""
    return svc.get_efficiency_by_category(customer_name)


@router.get(
    "/customers/{customer_name}/sales/resource-compliance",
    response_model=ResourceComplianceResponse,
)
def sales_resource_compliance(
    customer_name: str,
    scope: str = "virtualization",
    svc: SalesService = Depends(get_sales_service),
):
    """CRM entitlement (active + invoiced) vs infrastructure usage with overage loss."""
    return svc.get_resource_compliance(customer_name, scope=scope)


@router.get("/customers/{customer_name}/sales/catalog-valuation", response_model=List[CatalogValuationRow])
def catalog_valuation(
    customer_name: str,
    svc: SalesService = Depends(get_sales_service),
):
    """Standard TL catalog prices for all active products — basis for datacenter valuation."""
    return svc.get_catalog_valuation(customer_name)


@router.get(
    "/customers/{customer_name}/sales/service-breakdown",
    response_model=List[CustomerServiceSalesSlice],
)
def sales_service_breakdown(
    customer_name: str,
    svc: SalesService = Depends(get_sales_service),
):
    """Realized CRM sales amounts grouped by mapped service category for one customer."""
    return svc.get_service_breakdown(customer_name)


# ---------------------------------------------------------------------------
# Customer alias management
# ---------------------------------------------------------------------------

@router.get("/crm/aliases", response_model=List[CustomerAliasWithMappings])
def list_aliases(svc: SalesService = Depends(get_sales_service)):
    """Return CRM project customers with legacy alias fields and source mappings."""
    return svc.get_all_aliases()


@router.put("/crm/aliases/{crm_accountid}/source-mappings", response_model=List[dict])
def save_source_mappings(
    crm_accountid: str,
    body: CustomerSourceMappingUpdate,
    svc: SalesService = Depends(get_sales_service),
):
    """Replace all source mappings for a CRM account."""
    mappings = [m.model_dump() for m in (body.mappings or [])]
    return svc.save_source_mappings(
        crm_accountid,
        crm_account_name=body.crm_account_name or crm_accountid,
        mappings=mappings,
        notes=body.notes,
    )


@router.post("/crm/aliases/seed-boyner", response_model=dict)
def seed_boyner_mappings(svc: SalesService = Depends(get_sales_service)):
    """Idempotently seed Boyner default source mappings."""
    return svc.seed_boyner_source_mappings()


@router.put("/crm/aliases/{crm_accountid}", response_model=dict)
def update_alias(
    crm_accountid: str,
    body: CustomerAliasUpdate,
    svc: SalesService = Depends(get_sales_service),
):
    """Create or update a customer alias mapping (sets source = manual)."""
    svc.upsert_alias(
        crm_accountid=crm_accountid,
        crm_account_name=body.canonical_customer_key or crm_accountid,
        canonical_key=body.canonical_customer_key,
        netbox_value=body.netbox_musteri_value,
        notes=body.notes,
    )
    return {"status": "ok", "crm_accountid": crm_accountid}


@router.delete("/crm/aliases/{crm_accountid}", response_model=dict)
def delete_alias(
    crm_accountid: str,
    svc: SalesService = Depends(get_sales_service),
):
    """Remove a customer alias entry."""
    n = svc.delete_alias(crm_accountid)
    return {"status": "ok", "crm_accountid": crm_accountid, "rows_deleted": n}


