from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from app.core.time_filter import TimeFilter
from app.models.schemas import (
    CustomerCatalogResponse,
    CustomerOverviewResponse,
    CustomerResources,
    CustomerVipUpdate,
    CustomerVipUpdateResponse,
)
from app.services.customer_service import CustomerService

router = APIRouter()


def get_db(request: Request) -> CustomerService:
    return request.app.state.db


@router.get("/customers", response_model=List[str])
def list_customers(db: CustomerService = Depends(get_db)):
    return db.get_customer_list()


@router.get("/customers/catalog", response_model=CustomerCatalogResponse)
def customer_catalog(db: CustomerService = Depends(get_db)):
    """CRM project customers with mapping/VIP/cache metadata for the /customers page."""
    return db.get_customer_catalog()


@router.get("/customers/overview", response_model=CustomerOverviewResponse)
def customer_overview(db: CustomerService = Depends(get_db)):
    """CRM aggregate KPIs and service sales distribution for the /customers page."""
    return db.get_customer_overview()


@router.put("/customers/{crm_accountid}/vip", response_model=CustomerVipUpdateResponse)
def set_customer_vip(
    crm_accountid: str,
    body: CustomerVipUpdate,
    db: CustomerService = Depends(get_db),
    x_api_user: str | None = Header(default=None, alias="X-API-User"),
):
    """Toggle VIP flag; VIP customers are cache-pinned for warm/refresh."""
    return db.set_customer_vip(
        crm_accountid,
        is_vip=bool(body.is_vip),
        updated_by=x_api_user,
    )


# NOTE: must be declared BEFORE the /{customer_name}/resources route below,
# otherwise "unmapped" is captured as a customer_name path param.
@router.get("/customers/unmapped/resources", response_model=dict[str, Any])
def unmapped_resources(
    tf: TimeFilter = Depends(),
    db: CustomerService = Depends(get_db),
):
    """Resources (Phase 1: VMs) that match no customer — the Eşleşmeyen Veriler bucket."""
    return db.get_unmapped_resources(tf.to_dict())


@router.get("/customers/{customer_name}/resources", response_model=CustomerResources)
def customer_resources(
    customer_name: str,
    tf: TimeFilter = Depends(),
    db: CustomerService = Depends(get_db),
):
    return db.get_customer_resources(customer_name, tf.to_dict())


@router.get("/customers/{customer_name}/deleted-machines", response_model=dict[str, Any])
def customer_deleted_machines(
    customer_name: str,
    db: CustomerService = Depends(get_db),
):
    """All-time deleted VMs for a customer (3 dates), read from the registry."""
    return db.get_deleted_machines(customer_name)


@router.get("/customers/{customer_name}/infra-patterns", response_model=dict[str, Any])
def customer_infra_patterns(
    customer_name: str,
    db: CustomerService = Depends(get_db),
):
    """Resolved ILIKE patterns for a customer's infra (for datacenter-api matching)."""
    return db.get_infra_patterns(customer_name)


@router.get("/customers/{customer_name}/s3/vaults", response_model=dict[str, Any])
def customer_s3_vaults(
    customer_name: str,
    tf: TimeFilter = Depends(),
    db: CustomerService = Depends(get_db),
):
    return db.get_customer_s3_vaults(customer_name, tf.to_dict())


_UNIQUE_JOBS_VENDORS = ("veeam", "zerto", "netbackup")


def _split_csv(value: Optional[str]) -> Optional[List[str]]:
    return [p for p in (value or "").split(",") if p] or None


@router.get("/customers/{customer_name}/backup/{vendor}/unique-jobs", response_model=dict[str, Any])
def customer_unique_jobs(
    customer_name: str,
    vendor: str,
    tf: TimeFilter = Depends(),
    db: CustomerService = Depends(get_db),
):
    """Latest-per-identity unique-job/VPG inventory (rows + status/type totals)
    for a customer, matched via the customer's resolved backup ILIKE patterns."""
    if vendor not in _UNIQUE_JOBS_VENDORS:
        raise HTTPException(status_code=404, detail=f"Unknown backup vendor: {vendor}")
    return db.get_customer_unique_jobs(customer_name, vendor, tf.to_dict())


@router.get("/customers/{customer_name}/backup/{vendor}/unique-jobs/table", response_model=dict[str, Any])
def customer_unique_jobs_table(
    customer_name: str,
    vendor: str,
    tf: TimeFilter = Depends(),
    db: CustomerService = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(""),
    status: Optional[str] = Query(None, description="comma-separated"),
    type: Optional[str] = Query(None, description="comma-separated"),
    policy_type: Optional[str] = Query(None, description="comma-separated"),
    category: Optional[str] = Query(None, description="image | application, comma-separated"),
    platform: Optional[str] = Query(None, description="comma-separated"),
):
    """Paged/filtered unique-job/VPG table for a customer; totals reflect the filtered set."""
    if vendor not in _UNIQUE_JOBS_VENDORS:
        raise HTTPException(status_code=404, detail=f"Unknown backup vendor: {vendor}")
    return db.get_customer_unique_jobs_table(
        customer_name, vendor, tf.to_dict(),
        page=page, page_size=page_size, search=search or "",
        statuses=_split_csv(status), types=_split_csv(type),
        policy_types=_split_csv(policy_type), categories=_split_csv(category),
        platforms=_split_csv(platform),
    )
