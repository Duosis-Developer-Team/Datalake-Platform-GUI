from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request

from app.models.schemas import DataCenterDetail, DataCenterSummary
from app.services.db_service import DatabaseService

router = APIRouter()


def get_db(request: Request) -> DatabaseService:
    return request.app.state.db


@router.get("/datacenters/summary", response_model=List[DataCenterSummary])
def list_datacenters(
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: DatabaseService = Depends(get_db),
):
    time_range = {"start": start, "end": end} if (start and end) else None
    return db.get_all_datacenters_summary(time_range)


@router.get("/datacenters/{dc_code}", response_model=DataCenterDetail)
def datacenter_detail(
    dc_code: str,
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: DatabaseService = Depends(get_db),
):
    time_range = {"start": start, "end": end} if (start and end) else None
    return db.get_dc_details(dc_code, time_range)
