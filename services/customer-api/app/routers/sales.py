"""
CRM Sales endpoints for the customer-api microservice.

Routes:
  GET /customers/{customer_name}/sales/summary
  GET /customers/{customer_name}/sales/items
  GET /customers/{customer_name}/sales/efficiency
  GET /customers/{customer_name}/sales/efficiency-by-category
  GET /customers/{customer_name}/sales/catalog-valuation
  GET /crm/aliases
  PUT /crm/aliases/{crm_accountid}
  GET /crm/product-categories
  PUT /crm/product-categories/{productid}
"""
from __future__ import annotations

from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Request

from app.models.schemas import (
    CatalogValuationRow,
    CustomerAlias,
    CustomerAliasUpdate,
    ProductCategoryAliasRow,
    ProductCategoryAliasUpdate,
    SalesEfficiencyByCategoryRow,
    SalesEfficiencyRow,
    SalesLineItem,
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
    """Realized sales-order line items (fulfilled/invoiced) for a customer."""
    return svc.get_sales_items(customer_name)


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


@router.get("/customers/{customer_name}/sales/catalog-valuation", response_model=List[CatalogValuationRow])
def catalog_valuation(
    customer_name: str,
    svc: SalesService = Depends(get_sales_service),
):
    """Standard TL catalog prices for all active products — basis for datacenter valuation."""
    return svc.get_catalog_valuation(customer_name)


# ---------------------------------------------------------------------------
# Customer alias management
# ---------------------------------------------------------------------------

@router.get("/crm/aliases", response_model=List[CustomerAlias])
def list_aliases(svc: SalesService = Depends(get_sales_service)):
    """Return all CRM → platform customer alias mappings."""
    return svc.get_all_aliases()


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


# ---------------------------------------------------------------------------
# Product category alias (GUI + collectors)
# ---------------------------------------------------------------------------


@router.get("/crm/product-categories", response_model=List[ProductCategoryAliasRow])
def list_product_categories(svc: SalesService = Depends(get_sales_service)):
    """All CRM product → category GUI bindings (manual rows preserved on re-seed)."""
    return svc.list_product_category_aliases()


@router.put("/crm/product-categories/{productid}", response_model=dict)
def update_product_category(
    productid: str,
    body: ProductCategoryAliasUpdate,
    svc: SalesService = Depends(get_sales_service),
):
    """Update category mapping for one product (sets source = manual)."""
    n = svc.update_product_category_alias(
        productid,
        category_code=body.category_code,
        category_label=body.category_label,
        gui_tab_binding=body.gui_tab_binding,
        resource_unit=body.resource_unit,
        notes=body.notes,
    )
    if n <= 0:
        raise HTTPException(status_code=404, detail="productid not found")
    return {"status": "ok", "productid": productid, "rows_updated": n}
