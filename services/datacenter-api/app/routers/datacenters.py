from __future__ import annotations

from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.core.time_filter import TimeFilter
from app.models.schemas import DataCenterSummary, JobStatsResponse, LicensedOsSummary
from app.services.dc_service import DatabaseService
from app.services import sla_service
from app.db.queries import crm_potential as crm_q
from app.services.dc_sales_potential_v2 import compute_dc_summary, compute_sales_potential_v2
from app.services.webui_db import WebuiPool

router = APIRouter()


def get_db(request: Request) -> DatabaseService:
    return request.app.state.db


def get_webui(request: Request) -> WebuiPool:
    return request.app.state.webui


_UNIQUE_JOBS_VENDORS = ("veeam", "zerto", "netbackup")


def _split_csv(value: Optional[str]) -> Optional[List[str]]:
    return [p for p in (value or "").split(",") if p] or None


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


@router.get("/licensed-os/summary", response_model=LicensedOsSummary)
def licensed_os_summary(
    customer: str | None = Query(default=None),
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
):
    if customer:
        return db.get_licensed_os_for_customer(customer, tf.to_dict())
    return db.get_licensed_os_summary(tf.to_dict())


@router.get("/sla", response_model=dict[str, Any])
def sla_availability(tf: TimeFilter = Depends()):
    """SLA availability keyed by DC code for the given time range."""
    by_dc = sla_service.get_sla_data(tf.to_dict())
    return {"by_dc": by_dc}


@router.get("/sla/datacenter-services", response_model=dict[str, Any])
def sla_dc_services(tf: TimeFilter = Depends()):
    """Datacenter-services SLA items from AuraNotify for the given time range."""
    items = sla_service.get_dc_services_availability(tf.to_dict())
    return {"items": items}


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


@router.get("/datacenters/{dc_code}/backup/zerto/license", response_model=dict[str, Any])
def dc_zerto_license(dc_code: str, db: DatabaseService = Depends(get_db)):
    """Zerto license + per-site protected VM usage for a DC (datalake)."""
    return db.get_dc_zerto_license(dc_code)


@router.get("/datacenters/{dc_code}/backup/veeam", response_model=dict[str, Any])
def dc_veeam(dc_code: str, tf: TimeFilter = Depends(), db: DatabaseService = Depends(get_db)):
    return db.get_dc_veeam_repos(dc_code, tf.to_dict())


@router.get("/datacenters/{dc_code}/backup/nutanix", response_model=dict[str, Any])
def dc_nutanix_snapshots(dc_code: str, tf: TimeFilter = Depends(), db: DatabaseService = Depends(get_db)):
    return db.get_dc_nutanix_snapshots(dc_code, tf.to_dict())


@router.get("/datacenters/{dc_code}/backup/nutanix/table", response_model=dict[str, Any])
def dc_nutanix_snapshot_table(
    dc_code: str,
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(""),
    customers: Optional[str] = Query(None, description="comma-separated"),
    schedule_types: Optional[str] = Query(None, description="comma-separated"),
    retentions: Optional[str] = Query(None, description="comma-separated"),
    clusters: Optional[str] = Query(None, description="comma-separated"),
):
    def _split(v):
        return [p for p in (v or "").split(",") if p] or None

    return db.get_dc_nutanix_snapshot_table(
        dc_code, tf.to_dict(), page=page, page_size=page_size, search=search or "",
        customers=_split(customers), schedule_types=_split(schedule_types),
        retentions=_split(retentions), clusters=_split(clusters),
    )


@router.get("/datacenters/{dc_code}/backup/nutanix/missing", response_model=dict[str, Any])
def dc_nutanix_missing(
    dc_code: str,
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    return db.get_dc_nutanix_missing(dc_code, tf.to_dict(), page=page, page_size=page_size)


@router.post("/datacenters/{dc_code}/backup/nutanix/refresh")
def dc_nutanix_refresh(dc_code: str, db: DatabaseService = Depends(get_db)):
    return db.refresh_dc_nutanix_snapshots(dc_code)


@router.get("/customers/{customer}/backup/nutanix", response_model=dict[str, Any])
def customer_nutanix_snapshots(
    customer: str,
    tf: TimeFilter = Depends(),
    pattern: list[str] | None = Query(default=None),
    db: DatabaseService = Depends(get_db),
):
    """`pattern` (repeatable) = the customer's resolved ILIKE patterns, supplied by
    the GUI from customer-api so snapshots match by the customer's real infra name."""
    return db.get_customer_nutanix_snapshots(customer, tf.to_dict(), pattern)


@router.get("/datacenters/{dc_code}/backup/veeam/jobs", response_model=JobStatsResponse)
def dc_veeam_jobs(
    dc_code: str,
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
    granularity: str = Query("day", description="day | week | month"),
    status: Optional[str] = Query(None, description="comma-separated"),
    job_type: Optional[str] = Query(None, description="comma-separated"),
):
    return db.get_dc_veeam_jobs(
        dc_code, tf.to_dict(), granularity,
        statuses=_split_csv(status), job_types=_split_csv(job_type),
    )


@router.get("/datacenters/{dc_code}/backup/zerto/jobs", response_model=JobStatsResponse)
def dc_zerto_jobs(
    dc_code: str,
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
    granularity: str = Query("day", description="day | week | month"),
    status: Optional[str] = Query(None, description="comma-separated"),
    job_type: Optional[str] = Query(None, description="comma-separated"),
):
    return db.get_dc_zerto_jobs(
        dc_code, tf.to_dict(), granularity,
        statuses=_split_csv(status), job_types=_split_csv(job_type),
    )


@router.get("/datacenters/{dc_code}/backup/netbackup/jobs", response_model=JobStatsResponse)
def dc_netbackup_jobs(
    dc_code: str,
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
    granularity: str = Query("day", description="day | week | month"),
    status: Optional[str] = Query(None, description="comma-separated"),
    job_type: Optional[str] = Query(None, description="comma-separated"),
    policy_type: Optional[str] = Query(None, description="comma-separated"),
    category: Optional[str] = Query(None, description="image | application, comma-separated"),
):
    return db.get_dc_netbackup_jobs(
        dc_code, tf.to_dict(), granularity,
        statuses=_split_csv(status), job_types=_split_csv(job_type),
        policy_types=_split_csv(policy_type), category=category or None,
    )


@router.get("/datacenters/{dc_code}/backup/{vendor}/unique-jobs", response_model=dict[str, Any])
def dc_unique_jobs(
    dc_code: str,
    vendor: str,
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
):
    """Latest-per-identity unique-job/VPG inventory (rows + status/type totals) for a DC."""
    if vendor not in _UNIQUE_JOBS_VENDORS:
        raise HTTPException(status_code=404, detail=f"Unknown backup vendor: {vendor}")
    return db.get_dc_unique_jobs(dc_code, vendor, tf.to_dict())


@router.get("/datacenters/{dc_code}/backup/{vendor}/unique-jobs/table", response_model=dict[str, Any])
def dc_unique_jobs_table(
    dc_code: str,
    vendor: str,
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(""),
    status: Optional[str] = Query(None, description="comma-separated"),
    type: Optional[str] = Query(None, description="comma-separated"),
    policy_type: Optional[str] = Query(None, description="comma-separated"),
    category: Optional[str] = Query(None, description="image | application, comma-separated"),
    platform: Optional[str] = Query(None, description="comma-separated"),
):
    """Paged/filtered unique-job/VPG table for a DC; totals reflect the filtered set."""
    if vendor not in _UNIQUE_JOBS_VENDORS:
        raise HTTPException(status_code=404, detail=f"Unknown backup vendor: {vendor}")
    return db.get_dc_unique_jobs_table(
        dc_code, vendor, tf.to_dict(),
        page=page, page_size=page_size, search=search or "",
        statuses=_split_csv(status), types=_split_csv(type),
        policy_types=_split_csv(policy_type), categories=_split_csv(category),
        platforms=_split_csv(platform),
    )


@router.post("/datacenters/{dc_code}/backup/jobs/refresh")
def dc_backup_jobs_refresh(
    dc_code: str,
    vendor: str = Query("all", description="veeam | zerto | netbackup | all"),
):
    """
    Invalidate cached job statistics for one DC (single vendor or all three).

    Used by the 'Yenile' button on the Backup & Replication panels so users can
    force a live SQL re-run when they suspect data is stale. Returns the number
    of cache keys deleted per vendor.
    """
    from app.core.cache_backend import cache_delete_prefix

    vendors = ("veeam", "zerto", "netbackup") if vendor == "all" else (vendor,)
    deleted: dict[str, str] = {}
    for v in vendors:
        if v not in ("veeam", "zerto", "netbackup"):
            continue
        prefix = f"dc_{v}_jobs:{dc_code}:"
        cache_delete_prefix(prefix)
        # Stale-while-revalidate snapshot'larını da temizle — kullanıcı 'Yenile'
        # dediğinde gerçekten canlı SQL beklesin, eski snapshot dönmesin.
        cache_delete_prefix(f"stale:{prefix}")
        # Unique-jobs inventory cache aynı SWR şemasını kullanıyor (dc_{v}_unique_jobs);
        # onu da temizle ki tablo görünümü de canlı SQL ile yenilensin.
        unique_prefix = f"dc_{v}_unique_jobs:{dc_code}:"
        cache_delete_prefix(unique_prefix)
        cache_delete_prefix(f"stale:{unique_prefix}")
        deleted[v] = "invalidated"
    return {"status": "ok", "dc_code": dc_code, "deleted": deleted}


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


@router.get("/datacenters/{dc_code}/compute/classic/hosts", response_model=dict[str, Any])
def classic_compute_hosts(
    dc_code: str,
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
    clusters: Optional[str] = Query(None, description="Comma-separated cluster names; empty = all"),
):
    """Per-host CPU/RAM capacity, usage and sales allocation for Classic (KM) clusters."""
    selected = [c.strip() for c in clusters.split(",") if c.strip()] if clusters else None
    return db.get_classic_host_rows(dc_code, selected, tf.to_dict())


@router.get("/datacenters/{dc_code}/compute/hyperconverged/hosts", response_model=dict[str, Any])
def hyperconv_compute_hosts(
    dc_code: str,
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
    clusters: Optional[str] = Query(None, description="Comma-separated cluster names; empty = all"),
):
    """Per-host CPU/RAM/storage capacity, usage and sales allocation for Hyperconverged (Nutanix) clusters."""
    selected = [c.strip() for c in clusters.split(",") if c.strip()] if clusters else None
    return db.get_hyperconv_host_rows(dc_code, selected, tf.to_dict())


@router.get("/datacenters/{dc_code}/racks", response_model=dict[str, Any])
def dc_racks(dc_code: str, db: DatabaseService = Depends(get_db)):
    return db.get_dc_racks(dc_code)


@router.get("/datacenters/{dc_code}/racks/{rack_name}/devices", response_model=dict[str, Any])
def rack_devices(dc_code: str, rack_name: str, db: DatabaseService = Depends(get_db)):
    return db.get_rack_devices(rack_name)


@router.get("/datacenters/{dc_code}/physical-inventory", response_model=dict[str, Any])
def physical_inventory_dc(dc_code: str, db: DatabaseService = Depends(get_db)):
    return db.get_physical_inventory_dc(dc_code)


@router.get("/physical-inventory/overview/by-role", response_model=list[dict[str, Any]])
def phys_inv_overview_by_role(db: DatabaseService = Depends(get_db)):
    return db.get_physical_inventory_overview_by_role()


@router.get("/physical-inventory/customer", response_model=list[dict[str, Any]])
def phys_inv_customer(
    customer: str | None = None,
    db: DatabaseService = Depends(get_db),
    webui: WebuiPool = Depends(get_webui),
):
    """Customer-scoped physical device list for Customer View."""
    return db.get_physical_inventory_customer(customer, webui=webui)


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


@router.get("/datacenters/{dc_code}/storage/datastores", response_model=dict[str, Any])
def storage_datastores(dc_code: str, tf: TimeFilter = Depends(), db: DatabaseService = Depends(get_db)):
    """VMware datastores for a DC with host-mount mapping + VMFS/NAS inventory detail."""
    return db.get_datastore_mapping(dc_code, tf.to_dict())


# ---------------------------------------------------------------------------
# Network Dashboard (Zabbix) + Intel Storage (Zabbix) - DC scoped
# ---------------------------------------------------------------------------


@router.get("/datacenters/{dc_code}/network/filters", response_model=dict[str, Any])
def network_filters(
    dc_code: str,
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
    interface_scope: Optional[str] = Query(
        None,
        description="Interface scope: backbone, leaf, spine, management, router_uplink",
    ),
):
    return db.get_network_filters(dc_code, tf.to_dict(), interface_scope=interface_scope)


@router.get("/datacenters/{dc_code}/network/port-summary", response_model=dict[str, Any])
def network_port_summary(
    dc_code: str,
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
    manufacturer: Optional[str] = Query(None),
    device_role: Optional[str] = Query(None),
    device_name: Optional[str] = Query(None),
    interface_scope: Optional[str] = Query(
        None,
        description="Interface scope: backbone, leaf, spine, management, router_uplink",
    ),
):
    return db.get_network_port_summary(
        dc_code,
        tf.to_dict(),
        manufacturer=manufacturer,
        device_role=device_role,
        device_name=device_name,
        interface_scope=interface_scope,
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
    interface_scope: Optional[str] = Query(
        None,
        description="Interface scope: backbone, leaf, spine, management, shared, router_uplink",
    ),
):
    return db.get_network_95th_percentile(
        dc_code,
        tf.to_dict(),
        manufacturer=manufacturer,
        device_role=device_role,
        device_name=device_name,
        top_n=top_n,
        interface_scope=interface_scope,
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
    interface_scope: Optional[str] = Query(
        None,
        description="Interface scope: backbone, leaf, spine, management, shared, router_uplink",
    ),
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
        interface_scope=interface_scope,
    )


@router.get("/datacenters/{dc_code}/network/interface-export", response_model=dict[str, Any])
def network_interface_export(
    dc_code: str,
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
    search: Optional[str] = Query("", description="Interface name/alias contains filter"),
    manufacturer: Optional[str] = Query(None),
    device_role: Optional[str] = Query(None),
    device_name: Optional[str] = Query(None),
    interface_scope: Optional[str] = Query(
        None,
        description="Interface scope: backbone, leaf, spine, management, router_uplink, overview",
    ),
):
    return db.get_network_interface_export(
        dc_code,
        tf.to_dict(),
        manufacturer=manufacturer,
        device_role=device_role,
        device_name=device_name,
        search=search,
        interface_scope=interface_scope,
    )


@router.get("/datacenters/{dc_code}/network/firewall-summary", response_model=dict[str, Any])
def network_firewall_summary(
    dc_code: str,
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
):
    return db.get_network_firewall_summary(dc_code, tf.to_dict())


@router.get("/datacenters/{dc_code}/network/load-balancer-summary", response_model=dict[str, Any])
def network_load_balancer_summary(
    dc_code: str,
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
):
    return db.get_network_load_balancer_summary(dc_code, tf.to_dict())


@router.get("/datacenters/{dc_code}/zabbix-storage/capacity", response_model=dict[str, Any])
def zabbix_storage_capacity(
    dc_code: str,
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
    host: Optional[str] = Query(None, description="Optional Zabbix storage host filter"),
):
    return db.get_zabbix_storage_capacity(dc_code, tf.to_dict(), host=host)


@router.get("/datacenters/{dc_code}/zabbix-storage/trend", response_model=dict[str, Any])
def zabbix_storage_trend(
    dc_code: str,
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
    host: Optional[str] = Query(None, description="Optional Zabbix storage host filter"),
):
    return db.get_zabbix_storage_trend(dc_code, tf.to_dict(), host=host)

@router.get("/datacenters/{dc_code}/zabbix-storage/devices", response_model=List[dict[str, Any]])
def zabbix_storage_devices(
    dc_code: str,
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
):
    return db.get_zabbix_storage_devices(dc_code, tf.to_dict())


@router.get("/datacenters/{dc_code}/zabbix-storage/disk-list", response_model=dict[str, Any])
def zabbix_storage_disk_list(
    dc_code: str,
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
    host: Optional[str] = Query(None, description="Selected Zabbix storage host"),
):
    return db.get_zabbix_disk_list(dc_code, tf.to_dict(), host=host)


@router.get("/datacenters/{dc_code}/zabbix-storage/disk-trend", response_model=dict[str, Any])
def zabbix_storage_disk_trend(
    dc_code: str,
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
    host: Optional[str] = Query(None, description="Selected Zabbix storage host"),
    disk: Optional[str] = Query(None, description="Selected disk name"),
):
    return db.get_zabbix_disk_trend(dc_code, tf.to_dict(), host=host, disk_name=disk)


@router.get("/datacenters/{dc_code}/zabbix-storage/disk-health", response_model=dict[str, Any])
def zabbix_storage_disk_health(dc_code: str, tf: TimeFilter = Depends(), db: DatabaseService = Depends(get_db)):
    return db.get_zabbix_disk_health(dc_code, tf.to_dict())


@router.get("/datacenters/{dc_code}/sales-potential", response_model=dict[str, Any])
def dc_sales_potential(
    dc_code: str,
    db: DatabaseService = Depends(get_db),
    webui: WebuiPool = Depends(get_webui),
):
    """
    Sales potential for a datacenter (legacy v1): idle capacity × standard catalog unit prices.
    Also returns YTD billing for customers present in this DC. Customer alias resolution
    runs against the webui DB (gui_crm_customer_alias).
    """
    dc_pattern = f"%{dc_code}%"
    try:
        with db._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    crm_q.DC_SALES_POTENTIAL,
                    (dc_pattern, dc_pattern, dc_pattern, dc_pattern, dc_code, dc_pattern, dc_pattern),
                )
                cols = [d[0] for d in cur.description]
                detail_rows = [dict(zip(cols, row)) for row in cur.fetchall()]

                # Resolve account ids for the DC via webui alias and run summary query
                from app.services.dc_sales_potential_v2 import _resolve_account_ids_for_dc
                account_ids = _resolve_account_ids_for_dc(cur, webui, dc_pattern)
                summary = compute_dc_summary(cur, dc_code, account_ids)
    except Exception:
        detail_rows = []
        summary = {}

    return {
        "dc_code": dc_code,
        "summary": summary,
        "catalog_detail": detail_rows,
    }


@router.get("/datacenters/{dc_code}/sales-potential/v2", response_model=dict[str, Any])
def dc_sales_potential_v2(
    dc_code: str,
    db: DatabaseService = Depends(get_db),
    webui: WebuiPool = Depends(get_webui),
):
    """
    DEPRECATED in favour of customer-api ``/api/v1/crm/sellable-potential/by-panel?dc_code=...``
    (see ADR-0014). The new pipeline uses gui_panel_definition + per-environment
    resource ratios + unit conversions to deliver constrained sellable + TL
    potential without coupling Nutanix-only capacity to every resource family.

    The legacy v2 response shape is preserved for backward compatibility while
    the GUI migrates to the inline Sellable Potential KPI blocks (Faz 6).

    Realized-sales-based sellable headroom with Nutanix capacity proxy.
    Sellable ceiling per resource type comes from gui_crm_threshold_config (webui-db).
    See ADR-0010 / ADR-0012.
    """
    payload: dict[str, Any] = {"dc_code": dc_code}
    try:
        with db._get_connection() as conn:
            with conn.cursor() as cur:
                payload.update(compute_sales_potential_v2(cur, dc_code, webui=webui))
                payload["dc_customer_summary"] = compute_dc_summary(
                    cur, dc_code, payload.get("resolved_account_ids") or []
                )
    except Exception:
        payload.setdefault("general_remaining_pct", 0.0)
        payload.setdefault("per_resource", {})
        payload.setdefault("per_category", [])
        payload["dc_customer_summary"] = {}
    return payload
