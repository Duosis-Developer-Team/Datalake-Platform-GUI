"""Colocation rack-occupancy + CRM customer-footprint endpoints (DC 'Kolokasyon' tab)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.services.colocation_matching_service import ColocationMatchingService

router = APIRouter()


def _colocation_service(request: Request) -> ColocationMatchingService:
    svc = request.app.state.db
    webui = request.app.state.webui
    return ColocationMatchingService(customer_service=svc, webui=webui)


@router.get("/crm/colocation/{dc_code}")
def get_colocation(
    dc_code: str,
    colocation: ColocationMatchingService = Depends(_colocation_service),
) -> dict:
    return colocation.get_colocation(dc_code)
