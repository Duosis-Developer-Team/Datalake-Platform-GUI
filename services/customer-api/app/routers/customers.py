from typing import Any, List

from fastapi import APIRouter, Depends, Header, Request

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


@router.get("/customers/{customer_name}/s3/vaults", response_model=dict[str, Any])
def customer_s3_vaults(
    customer_name: str,
    tf: TimeFilter = Depends(),
    db: CustomerService = Depends(get_db),
):
    return db.get_customer_s3_vaults(customer_name, tf.to_dict())
