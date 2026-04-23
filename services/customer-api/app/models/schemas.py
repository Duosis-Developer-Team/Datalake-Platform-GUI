from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class CustomerResources(BaseModel):
    model_config = {"extra": "allow"}

    totals: dict[str, Any]
    assets: dict[str, Any]


class HealthResponse(BaseModel):
    status: str
    db_pool: str


# ---------------------------------------------------------------------------
# CRM Sales schemas
# ---------------------------------------------------------------------------

class SalesSummary(BaseModel):
    model_config = {"extra": "allow"}

    ytd_revenue_total: float
    invoice_count: int
    currency: Optional[str]
    pipeline_value: float
    opportunity_count: int
    active_order_count: int
    active_order_value: float
    active_contract_count: int
    total_contract_value: float
    estimated_mrr: float


class SalesLineItem(BaseModel):
    model_config = {"extra": "allow"}

    source_type: str
    reference_number: Optional[str]
    date: Optional[str]
    status: Optional[str]
    product_name: Optional[str]
    productdescription: Optional[str]
    unit: Optional[str]
    quantity: Optional[float]
    unit_price: Optional[float]
    line_total: Optional[float]
    currency: Optional[str]


class SalesEfficiencyRow(BaseModel):
    model_config = {"extra": "allow"}

    product_name: Optional[str]
    unit: Optional[str]
    total_billed_qty: Optional[float]
    total_billed_amount: Optional[float]
    currency: Optional[str]
    catalog_unit_price: Optional[float]
    price_list: Optional[str]
    catalog_coverage_pct: Optional[float]


class CatalogValuationRow(BaseModel):
    model_config = {"extra": "allow"}

    product_name: Optional[str]
    unit: Optional[str]
    unit_price_tl: Optional[float]
    valuation_type: str


class CustomerAlias(BaseModel):
    crm_accountid: str
    crm_account_name: str
    canonical_customer_key: Optional[str]
    netbox_musteri_value: Optional[str]
    notes: Optional[str]
    source: str


class CustomerAliasUpdate(BaseModel):
    canonical_customer_key: Optional[str] = None
    netbox_musteri_value: Optional[str] = None
    notes: Optional[str] = None
