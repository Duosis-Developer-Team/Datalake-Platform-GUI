from __future__ import annotations

from typing import Any, List, Optional

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


class SalesEfficiencyByCategoryRow(BaseModel):
    model_config = {"extra": "allow"}

    category_code: Optional[str] = None
    category_label: Optional[str] = None
    gui_tab_binding: Optional[str] = None
    resource_unit: Optional[str] = None
    sold_qty: float = 0.0
    sold_amount_tl: float = 0.0
    used_qty: float = 0.0
    efficiency_pct: Optional[float] = None
    allocated_vs_sold_pct: Optional[float] = None
    delta_qty: float = 0.0
    status: str = "unknown"
    usage_note: Optional[str] = None


class ProductCategoryAliasRow(BaseModel):
    model_config = {"extra": "allow"}

    productid: str
    product_name: Optional[str] = None
    category_code: Optional[str] = None
    category_label: Optional[str] = None
    gui_tab_binding: Optional[str] = None
    resource_unit: Optional[str] = None
    source: Optional[str] = None
    last_seeded_at: Optional[str] = None
    last_modified_at: Optional[str] = None
    notes: Optional[str] = None


class ProductCategoryAliasUpdate(BaseModel):
    category_code: str
    category_label: str
    gui_tab_binding: str
    resource_unit: str
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# ITSM (ServiceCore) schemas
# ---------------------------------------------------------------------------


class ITSMSummary(BaseModel):
    model_config = {"extra": "allow"}

    total_count: int = 0
    incident_count: int = 0
    sr_count: int = 0
    incident_open: int = 0
    incident_closed: int = 0
    sr_open: int = 0
    sr_closed: int = 0
    avg_resolution_hours: Optional[float] = None
    median_resolution_hours: Optional[float] = None
    p95_resolution_hours: Optional[float] = None
    stddev_resolution_hours: Optional[float] = None
    sla_breach_count: int = 0
    top_category: Optional[str] = None
    priority_distribution: List[dict[str, Any]] = []
    state_distribution: List[dict[str, Any]] = []


class ITSMTicket(BaseModel):
    model_config = {"extra": "allow"}

    source: str
    id: int
    subject: Optional[str] = None
    stage: Optional[str] = None
    state_text: Optional[str] = None
    status_name: Optional[str] = None
    priority_name: Optional[str] = None
    category_name: Optional[str] = None
    customer_user: Optional[str] = None
    agent_group_name: Optional[str] = None
    opened_at: Optional[str] = None
    target_resolution_date: Optional[str] = None
    closed_and_done_date: Optional[str] = None
    resolution_hours: Optional[float] = None
    open_age_days: Optional[float] = None


class ITSMExtremeTicket(BaseModel):
    model_config = {"extra": "allow"}

    source: str
    id: int
    subject: Optional[str] = None
    stage: Optional[str] = None
    priority_name: Optional[str] = None
    customer_user: Optional[str] = None
    agent_group_name: Optional[str] = None
    opened_at: Optional[str] = None
    target_resolution_date: Optional[str] = None
    closed_and_done_date: Optional[str] = None
    resolution_hours: Optional[float] = None
    open_age_days: Optional[float] = None
    threshold_avg: Optional[float] = None
    threshold_stddev: Optional[float] = None
    threshold_value: Optional[float] = None


class ITSMExtremes(BaseModel):
    long_tail: List[ITSMExtremeTicket] = []
    sla_breach: List[ITSMExtremeTicket] = []
