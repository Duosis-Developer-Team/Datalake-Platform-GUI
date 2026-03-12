from fastapi import APIRouter, Depends, Request

from app.core.time_filter import TimeFilter
from app.models.schemas import GlobalOverview
from app.services.db_service import DatabaseService

router = APIRouter()


def get_db(request: Request) -> DatabaseService:
    return request.app.state.db


@router.get("/dashboard/overview", response_model=GlobalOverview)
def dashboard_overview(
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
):
    return db.get_global_dashboard(tf.to_dict())
