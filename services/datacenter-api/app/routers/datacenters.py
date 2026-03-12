from typing import List

from fastapi import APIRouter, Depends, Request

from app.core.time_filter import TimeFilter
from app.models.schemas import DataCenterDetail, DataCenterSummary
from app.services.dc_service import DatabaseService

router = APIRouter()


def get_db(request: Request) -> DatabaseService:
    return request.app.state.db


@router.get("/datacenters/summary", response_model=List[DataCenterSummary])
def list_datacenters(
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
):
    return db.get_all_datacenters_summary(tf.to_dict())


@router.get("/datacenters/{dc_code}", response_model=DataCenterDetail)
def datacenter_detail(
    dc_code: str,
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
):
    return db.get_dc_details(dc_code, tf.to_dict())
