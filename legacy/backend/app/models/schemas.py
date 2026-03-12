from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel


class DCStats(BaseModel):
    total_cpu: str
    used_cpu_pct: float
    total_ram: str
    used_ram_pct: float
    total_storage: str
    used_storage_pct: float
    last_updated: str
    total_energy_kw: float
    ibm_kw: float
    vcenter_kw: float


class DataCenterSummary(BaseModel):
    id: str
    name: str
    location: str
    status: str
    platform_count: int
    cluster_count: int
    host_count: int
    vm_count: int
    stats: DCStats


class DCMeta(BaseModel):
    name: str
    location: str


class DCIntel(BaseModel):
    clusters: int
    hosts: int
    vms: int
    cpu_cap: float
    cpu_used: float
    ram_cap: float
    ram_used: float
    storage_cap: float
    storage_used: float


class DCPower(BaseModel):
    hosts: int
    vms: int
    vios: int
    lpar_count: int
    cpu: int = 0
    cpu_used: float
    cpu_assigned: float
    ram: int = 0
    memory_total: float
    memory_assigned: float


class DCEnergy(BaseModel):
    total_kw: float
    ibm_kw: float
    vcenter_kw: float
    total_kwh: float
    ibm_kwh: float
    vcenter_kwh: float


class NutanixPlatform(BaseModel):
    hosts: int
    vms: int


class VMwarePlatform(BaseModel):
    clusters: int
    hosts: int
    vms: int


class IBMPlatform(BaseModel):
    hosts: int
    vios: int
    lpars: int


class DCPlatforms(BaseModel):
    nutanix: NutanixPlatform
    vmware: VMwarePlatform
    ibm: IBMPlatform


class DataCenterDetail(BaseModel):
    meta: DCMeta
    intel: DCIntel
    power: DCPower
    energy: DCEnergy
    platforms: DCPlatforms


class GlobalStats(BaseModel):
    dc_count: int
    total_hosts: int
    total_vms: int
    total_platforms: int
    total_energy_kw: float
    total_cpu_cap: float
    total_cpu_used: float
    total_ram_cap: float
    total_ram_used: float
    total_storage_cap: float
    total_storage_used: float


class EnergyBreakdown(BaseModel):
    ibm_kw: float
    vcenter_kw: float


class GlobalOverview(BaseModel):
    overview: GlobalStats
    platforms: DCPlatforms
    energy_breakdown: EnergyBreakdown


class CustomerResources(BaseModel):
    model_config = {"extra": "allow"}

    totals: dict[str, Any]
    assets: dict[str, Any]


class QueryResult(BaseModel):
    result_type: Optional[str] = None
    value: Any = None
    columns: Optional[List[str]] = None
    data: Optional[List[Any]] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    db_pool: str
