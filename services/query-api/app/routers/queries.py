from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app.models.schemas import QueryResult
from app.services.query_service import QueryService

router = APIRouter()


def get_db(request: Request) -> QueryService:
    return request.app.state.db


@router.get("/queries/{query_key}", response_model=QueryResult)
def run_registered_query(
    query_key: str,
    params: str = Query(""),
    db: QueryService = Depends(get_db),
):
    return db.execute_registered_query(query_key, params)
