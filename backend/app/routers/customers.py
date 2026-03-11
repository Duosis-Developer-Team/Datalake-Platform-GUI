from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request

from app.models.schemas import CustomerResources
from app.services.db_service import DatabaseService

router = APIRouter()


def get_db(request: Request) -> DatabaseService:
    return request.app.state.db


@router.get("/customers", response_model=List[str])
def list_customers(db: DatabaseService = Depends(get_db)):
    return db.get_customer_list()


@router.get("/customers/{customer_name}/resources", response_model=CustomerResources)
def customer_resources(
    customer_name: str,
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: DatabaseService = Depends(get_db),
):
    time_range = {"start": start, "end": end} if (start and end) else None
    return db.get_customer_resources(customer_name, time_range)
