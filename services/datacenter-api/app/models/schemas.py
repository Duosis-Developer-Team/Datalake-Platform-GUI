from __future__ import annotations

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
    site_name: str | None = None
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


class ArchitectureTotals(BaseModel):
    """Aggregated classic or hyperconverged compute capacity vs usage (home Resource Usage gauges)."""

    cpu_cap: float
    cpu_used: float
    mem_cap: float
    mem_used: float
    stor_cap: float
    stor_used: float


class IBMTotals(BaseModel):
    """Aggregated IBM Power metrics for home Resource Usage tab."""

    mem_total: float
    mem_assigned: float
    cpu_used: float
    cpu_assigned: float


class GlobalOverview(BaseModel):
    overview: GlobalStats
    platforms: DCPlatforms
    energy_breakdown: EnergyBreakdown
    classic_totals: ArchitectureTotals
    hyperconv_totals: ArchitectureTotals
    ibm_totals: IBMTotals


class HealthResponse(BaseModel):
    status: str
    db_pool: str
