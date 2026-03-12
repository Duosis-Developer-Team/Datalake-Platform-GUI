from typing import List

from fastapi import APIRouter, Depends, Request

from app.core.time_filter import TimeFilter
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
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
):
    return db.get_customer_resources(customer_name, tf.to_dict())
