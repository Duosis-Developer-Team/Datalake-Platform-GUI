"""
ITSM (ServiceCore) endpoints for the customer-api microservice.

Routes:
  GET /customers/{customer_name}/itsm/summary
  GET /customers/{customer_name}/itsm/extremes
  GET /customers/{customer_name}/itsm/tickets
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.core.time_filter import TimeFilter
from app.models.schemas import ITSMExtremes, ITSMSummary, ITSMTicket
from app.services.itsm_service import ITSMService
from typing import List

router = APIRouter()


def get_itsm_service(request: Request) -> ITSMService:
    return request.app.state.itsm


@router.get("/customers/{customer_name}/itsm/summary", response_model=ITSMSummary)
def itsm_summary(
    customer_name: str,
    tf: TimeFilter = Depends(),
    svc: ITSMService = Depends(get_itsm_service),
):
    """ITSM KPI aggregates for the customer: counts, resolution stats, SLA breach, distributions."""
    return svc.get_summary(customer_name, tf.to_dict())


@router.get("/customers/{customer_name}/itsm/extremes", response_model=ITSMExtremes)
def itsm_extremes(
    customer_name: str,
    tf: TimeFilter = Depends(),
    svc: ITSMService = Depends(get_itsm_service),
):
    """
    Two extreme-case lists:
    - long_tail: closed incidents with resolution_hours > mean + 1·stddev
    - sla_breach: open tickets (incidents + SR) past target_resolution_date
    """
    return svc.get_extremes(customer_name, tf.to_dict())


@router.get("/customers/{customer_name}/itsm/tickets", response_model=List[ITSMTicket])
def itsm_tickets(
    customer_name: str,
    tf: TimeFilter = Depends(),
    svc: ITSMService = Depends(get_itsm_service),
):
    """All ITSM tickets (incidents + service requests) for the customer in the report period."""
    return svc.get_tickets(customer_name, tf.to_dict())
