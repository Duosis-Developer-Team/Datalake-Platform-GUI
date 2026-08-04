"""Colocation rack-occupancy + CRM customer-footprint endpoints (DC 'Colocation' tab)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.services.colocation_matching_service import ColocationMatchingService
from app.services.colocation_role_rule_service import get_role_rule_service

router = APIRouter()


def _colocation_service(request: Request) -> ColocationMatchingService:
    svc = request.app.state.db
    webui = request.app.state.webui
    return ColocationMatchingService(
        customer_service=svc,
        webui=webui,
        # App-scoped, not per-request: this factory runs on every colocation
        # call and the rule service owns a 30s memo.
        role_rules_service=get_role_rule_service(request.app),
    )


@router.get("/crm/colocation/{dc_code}")
def get_colocation(
    dc_code: str,
    colocation: ColocationMatchingService = Depends(_colocation_service),
) -> dict:
    return colocation.get_colocation(dc_code)
