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


# ---------------------------------------------------------------------------
# Network > SAN (Brocade) + Storage (IBM) - DC scoped
# ---------------------------------------------------------------------------


@router.get("/datacenters/{dc_code}/san/switches", response_model=list[str])
def san_switches(dc_code: str, tf: TimeFilter = Depends(), db: DatabaseService = Depends(get_db)):
    return db.get_san_switches(dc_code, tf.to_dict())


@router.get("/datacenters/{dc_code}/san/port-usage", response_model=dict[str, Any])
def san_port_usage(dc_code: str, tf: TimeFilter = Depends(), db: DatabaseService = Depends(get_db)):
    return db.get_san_port_usage(dc_code, tf.to_dict())


@router.get("/datacenters/{dc_code}/san/health", response_model=list[dict[str, Any]])
def san_health(dc_code: str, tf: TimeFilter = Depends(), db: DatabaseService = Depends(get_db)):
    return db.get_san_health_alerts(dc_code, tf.to_dict())


@router.get("/datacenters/{dc_code}/san/traffic-trend", response_model=list[dict[str, Any]])
def san_traffic_trend(dc_code: str, tf: TimeFilter = Depends(), db: DatabaseService = Depends(get_db)):
    return db.get_san_traffic_trend(dc_code, tf.to_dict())


@router.get("/datacenters/{dc_code}/san/bottleneck", response_model=dict[str, Any])
def san_bottleneck(dc_code: str, tf: TimeFilter = Depends(), db: DatabaseService = Depends(get_db)):
    return db.get_san_bottleneck(dc_code, tf.to_dict())


@router.get("/datacenters/{dc_code}/storage/capacity", response_model=dict[str, Any])
def storage_capacity(dc_code: str, tf: TimeFilter = Depends(), db: DatabaseService = Depends(get_db)):
    return db.get_storage_capacity(dc_code, tf.to_dict())


@router.get("/datacenters/{dc_code}/storage/performance", response_model=dict[str, Any])
def storage_performance(dc_code: str, tf: TimeFilter = Depends(), db: DatabaseService = Depends(get_db)):
    return db.get_storage_performance(dc_code, tf.to_dict())


# ---------------------------------------------------------------------------
# Network Dashboard (Zabbix) + Intel Storage (Zabbix) - DC scoped
# ---------------------------------------------------------------------------


@router.get("/datacenters/{dc_code}/network/filters", response_model=dict[str, Any])
def network_filters(dc_code: str, tf: TimeFilter = Depends(), db: DatabaseService = Depends(get_db)):
    return db.get_network_filters(dc_code, tf.to_dict())


@router.get("/datacenters/{dc_code}/network/port-summary", response_model=dict[str, Any])
def network_port_summary(
    dc_code: str,
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
    manufacturer: Optional[str] = Query(None),
    device_role: Optional[str] = Query(None),
    device_name: Optional[str] = Query(None),
):
    return db.get_network_port_summary(
        dc_code,
        tf.to_dict(),
        manufacturer=manufacturer,
        device_role=device_role,
        device_name=device_name,
    )


@router.get("/datacenters/{dc_code}/network/95th-percentile", response_model=dict[str, Any])
def network_95th_percentile(
    dc_code: str,
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
    top_n: int = Query(20, ge=1, le=100),
    manufacturer: Optional[str] = Query(None),
    device_role: Optional[str] = Query(None),
    device_name: Optional[str] = Query(None),
):
    return db.get_network_95th_percentile(
        dc_code,
        tf.to_dict(),
        manufacturer=manufacturer,
        device_role=device_role,
        device_name=device_name,
        top_n=top_n,
    )


@router.get("/datacenters/{dc_code}/network/interface-table", response_model=dict[str, Any])
def network_interface_table(
    dc_code: str,
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query("", description="Interface name/alias contains filter"),
    manufacturer: Optional[str] = Query(None),
    device_role: Optional[str] = Query(None),
    device_name: Optional[str] = Query(None),
):
    return db.get_network_interface_table(
        dc_code,
        tf.to_dict(),
        manufacturer=manufacturer,
        device_role=device_role,
        device_name=device_name,
        page=page,
        page_size=page_size,
        search=search,
    )


@router.get("/datacenters/{dc_code}/zabbix-storage/capacity", response_model=dict[str, Any])
def zabbix_storage_capacity(dc_code: str, tf: TimeFilter = Depends(), db: DatabaseService = Depends(get_db)):
    return db.get_zabbix_storage_capacity(dc_code, tf.to_dict())


@router.get("/datacenters/{dc_code}/zabbix-storage/trend", response_model=dict[str, Any])
def zabbix_storage_trend(dc_code: str, tf: TimeFilter = Depends(), db: DatabaseService = Depends(get_db)):
    return db.get_zabbix_storage_trend(dc_code, tf.to_dict())


@router.get("/datacenters/{dc_code}/zabbix-storage/disk-health", response_model=dict[str, Any])
def zabbix_storage_disk_health(dc_code: str, tf: TimeFilter = Depends(), db: DatabaseService = Depends(get_db)):
    return db.get_zabbix_disk_health(dc_code, tf.to_dict())
