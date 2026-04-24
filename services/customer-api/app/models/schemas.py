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
