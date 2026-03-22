from __future__ import annotations

from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Query, Request

from app.core.time_filter import TimeFilter
from app.models.schemas import DataCenterSummary
from app.services.dc_service import DatabaseService
from app.services import sla_service

router = APIRouter()


def get_db(request: Request) -> DatabaseService:
    return request.app.state.db


@router.get("/datacenters/summary", response_model=List[DataCenterSummary])
def list_datacenters(
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
):
    return db.get_all_datacenters_summary(tf.to_dict())


@router.get("/datacenters/{dc_code}", response_model=dict[str, Any])
def datacenter_detail(
    dc_code: str,
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
):
    """Full DC payload including classic/hyperconv compute split (not in legacy Pydantic schema)."""
    return db.get_dc_details(dc_code, tf.to_dict())


@router.get("/sla", response_model=dict[str, Any])
def sla_availability(tf: TimeFilter = Depends()):
    """SLA availability keyed by DC code for the given time range."""
    by_dc = sla_service.get_sla_data(tf.to_dict())
    return {"by_dc": by_dc}


@router.get("/datacenters/{dc_code}/s3/pools", response_model=dict[str, Any])
def dc_s3_pools(
    dc_code: str,
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
):
    return db.get_dc_s3_pools(dc_code, tf.to_dict())


@router.get("/datacenters/{dc_code}/backup/netbackup", response_model=dict[str, Any])
def dc_netbackup(dc_code: str, tf: TimeFilter = Depends(), db: DatabaseService = Depends(get_db)):
    return db.get_dc_netbackup_pools(dc_code, tf.to_dict())


@router.get("/datacenters/{dc_code}/backup/zerto", response_model=dict[str, Any])
def dc_zerto(dc_code: str, tf: TimeFilter = Depends(), db: DatabaseService = Depends(get_db)):
    return db.get_dc_zerto_sites(dc_code, tf.to_dict())


@router.get("/datacenters/{dc_code}/backup/veeam", response_model=dict[str, Any])
def dc_veeam(dc_code: str, tf: TimeFilter = Depends(), db: DatabaseService = Depends(get_db)):
    return db.get_dc_veeam_repos(dc_code, tf.to_dict())


@router.get("/datacenters/{dc_code}/clusters/classic", response_model=list[str])
def classic_clusters(dc_code: str, tf: TimeFilter = Depends(), db: DatabaseService = Depends(get_db)):
    return db.get_classic_cluster_list(dc_code, tf.to_dict())


@router.get("/datacenters/{dc_code}/clusters/hyperconverged", response_model=list[str])
def hyperconv_clusters(dc_code: str, tf: TimeFilter = Depends(), db: DatabaseService = Depends(get_db)):
    return db.get_hyperconv_cluster_list(dc_code, tf.to_dict())


@router.get("/datacenters/{dc_code}/compute/classic", response_model=dict[str, Any])
def classic_compute_filtered(
    dc_code: str,
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
    clusters: Optional[str] = Query(None, description="Comma-separated cluster names; empty = all"),
):
    selected = [c.strip() for c in clusters.split(",") if c.strip()] if clusters else None
    return db.get_classic_metrics_filtered(dc_code, selected, tf.to_dict())


@router.get("/datacenters/{dc_code}/compute/hyperconverged", response_model=dict[str, Any])
def hyperconv_compute_filtered(
    dc_code: str,
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
    clusters: Optional[str] = Query(None, description="Comma-separated cluster names; empty = all"),
):
    selected = [c.strip() for c in clusters.split(",") if c.strip()] if clusters else None
    return db.get_hyperconv_metrics_filtered(dc_code, selected, tf.to_dict())


@router.get("/datacenters/{dc_code}/physical-inventory", response_model=dict[str, Any])
def physical_inventory_dc(dc_code: str, db: DatabaseService = Depends(get_db)):
    return db.get_physical_inventory_dc(dc_code)


@router.get("/physical-inventory/overview/by-role", response_model=list[dict[str, Any]])
def phys_inv_overview_by_role(db: DatabaseService = Depends(get_db)):
    return db.get_physical_inventory_overview_by_role()


@router.get("/physical-inventory/customer", response_model=list[dict[str, Any]])
def phys_inv_customer(db: DatabaseService = Depends(get_db)):
    """Boyner tenant physical device list for Customer View."""
    return db.get_physical_inventory_customer()


@router.get("/physical-inventory/overview/manufacturer", response_model=list[dict[str, Any]])
def phys_inv_overview_manufacturer(role: str, db: DatabaseService = Depends(get_db)):
    return db.get_physical_inventory_overview_manufacturer(role)


@router.get("/physical-inventory/overview/location", response_model=list[dict[str, Any]])
def phys_inv_overview_location(role: str, manufacturer: str, db: DatabaseService = Depends(get_db)):
    return db.get_physical_inventory_overview_location(role, manufacturer)
