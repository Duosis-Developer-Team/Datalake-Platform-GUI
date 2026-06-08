"""NetBox/Loki read-only configuration helpers."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from app.services.dc_service import DatabaseService

router = APIRouter()


def get_db(request: Request) -> DatabaseService:
    return request.app.state.db


@router.get("/netbox/device-roles", response_model=list[dict[str, Any]])
def list_device_roles(db: DatabaseService = Depends(get_db)):
    """Distinct active device roles from discovery_netbox_inventory_device."""
    return db.get_netbox_device_roles()
