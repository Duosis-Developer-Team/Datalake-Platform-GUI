from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from app.models.schemas import GlobalOverview
from app.services.db_service import DatabaseService

router = APIRouter()


def get_db(request: Request) -> DatabaseService:
    return request.app.state.db


@router.get("/dashboard/overview", response_model=GlobalOverview)
def dashboard_overview(
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: DatabaseService = Depends(get_db),
):
    time_range = {"start": start, "end": end} if (start and end) else None
    return db.get_global_dashboard(time_range)
