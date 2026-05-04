"""
CRM service mapping — pages registry and per-product overrides.

Routes:
  GET  /crm/service-mapping/pages
  GET  /crm/service-mapping
  PUT  /crm/service-mapping/{productid}
  DELETE /crm/service-mapping/{productid}/override
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request

from app.models.schemas import ServiceMappingPageRow, ServiceMappingRow, ServiceMappingUpsert
from app.services.sales_service import SalesService

router = APIRouter()


def get_sales_service(request: Request) -> SalesService:
    return request.app.state.sales


@router.get("/crm/service-mapping/pages", response_model=List[ServiceMappingPageRow])
def list_pages(svc: SalesService = Depends(get_sales_service)):
    """All known page_key values (labels and GUI tab hints for dropdowns)."""
    return svc.list_service_pages()


@router.get("/crm/service-mapping", response_model=List[ServiceMappingRow])
def list_mappings(svc: SalesService = Depends(get_sales_service)):
    """All CRM catalog products with effective mapping (seed + override)."""
    return svc.list_service_mappings()


@router.put("/crm/service-mapping/{productid}", response_model=dict)
def upsert_mapping(
    productid: str,
    body: ServiceMappingUpsert,
    svc: SalesService = Depends(get_sales_service),
):
    """Set or update operator override for one product."""
    try:
        svc.upsert_service_mapping_override(
            productid,
            page_key=body.page_key,
            notes=body.notes,
            updated_by="settings-ui",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "productid": productid}


@router.delete("/crm/service-mapping/{productid}/override", response_model=dict)
def delete_override(productid: str, svc: SalesService = Depends(get_sales_service)):
    """Remove override so the product falls back to YAML seed mapping."""
    n = svc.delete_service_mapping_override(productid)
    return {"status": "ok", "productid": productid, "rows_deleted": n}
