from __future__ import annotations

import logging
import time

from app.services import cache_service as cache
from app.utils.time_range import default_time_range, time_range_to_bounds

logger = logging.getLogger(__name__)

_FALLBACK_DC_LIST = ["AZ11", "DC11", "DC12", "DC13", "DC14", "DC15", "DC16", "DC17", "ICT11"]

DC_LOCATIONS: dict[str, str] = {
    "AZ11": "Azerbaycan",
    "DC11": "Istanbul",
    "DC12": "İzmir",
    "DC13": "Istanbul",
    "DC14": "Ankara",
    "DC15": "Istanbul",
    "DC16": "Ankara",
    "DC17": "Istanbul",
    "DC18": "Istanbul",
    "ICT11": "Almanya",
    "UZ11": "Özbekistan",
}


def empty_dc(dc_code: str) -> dict:
    return {
        "meta": {"name": dc_code, "location": DC_LOCATIONS.get(dc_code, "Unknown Data Center")},
        "intel": {
            "clusters": 0,
            "hosts": 0,
            "vms": 0,
            "cpu_cap": 0.0,
            "cpu_used": 0.0,
            "ram_cap": 0.0,
            "ram_used": 0.0,
            "storage_cap": 0.0,
            "storage_used": 0.0,
        },
        "power": {
            "hosts": 0,
            "vms": 0,
            "vios": 0,
            "lpar_count": 0,
            "cpu": 0,
            "cpu_total_procunits": 0.0,
            "cpu_total_cores": 0.0,
            "cpu_available_procunits": 0.0,
            "cpu_available_cores": 0.0,
            "cpu_used": 0.0,
            "cpu_assigned": 0.0,
            "ram": 0,
            "memory_total": 0.0,
            "memory_available": 0.0,
            "memory_assigned": 0.0,
        },
        "energy": {"total_kw": 0.0, "ibm_kw": 0.0, "vcenter_kw": 0.0, "total_kwh": 0.0, "ibm_kwh": 0.0, "vcenter_kwh": 0.0},
        "platforms": {
            "nutanix": {"hosts": 0, "vms": 0},
            "vmware": {"clusters": 0, "hosts": 0, "vms": 0},
            "ibm": {"hosts": 0, "vios": 0, "lpars": 0},
        },
    }


def aggregate_dc(
    dc_code: str,
    nutanix_host_count,
    nutanix_vms,
    nutanix_mem,
    nutanix_storage,
    nutanix_cpu,
    vmware_counts,
    vmware_mem,
    vmware_storage,
    vmware_cpu,
    power_hosts,
    power_vios,
    power_lpar_count,
    power_mem,
    power_cpu,
    ibm_w,
    vcenter_w,
    ibm_kwh=None,
    vcenter_kwh=None,
) -> dict:
    nutanix_mem = nutanix_mem or (0, 0)
    nutanix_storage = nutanix_storage or (0, 0)
    nutanix_cpu = nutanix_cpu or (0, 0)
    vmware_counts = vmware_counts or (0, 0, 0)
    vmware_mem = vmware_mem or (0, 0)
    vmware_storage = vmware_storage or (0, 0)
    vmware_cpu = vmware_cpu or (0, 0)
    power_mem = power_mem or (0, 0, 0)
    power_cpu = power_cpu or (0, 0, 0, 0)
    n_mem_cap_gb = float(nutanix_mem[0] or 0) * 1024
    n_mem_used_gb = float(nutanix_mem[1] or 0) * 1024
    v_mem_cap_gb = float(vmware_mem[0] or 0) / (1024 ** 3)
    v_mem_used_gb = float(vmware_mem[1] or 0) / (1024 ** 3)
    n_stor_cap_tb = float(nutanix_storage[0] or 0)
    n_stor_used_tb = float(nutanix_storage[1] or 0)
    v_stor_cap_tb = float(vmware_storage[0] or 0) / (1024 ** 4)
    v_stor_used_tb = float(vmware_storage[1] or 0) / (1024 ** 4)
    n_cpu_cap_ghz = float(nutanix_cpu[0] or 0)
    n_cpu_used_ghz = float(nutanix_cpu[1] or 0)
    v_cpu_cap_ghz = float(vmware_cpu[0] or 0) / 1_000_000_000
    v_cpu_used_ghz = float(vmware_cpu[1] or 0) / 1_000_000_000
    total_energy_kw = (float(ibm_w or 0) + float(vcenter_w or 0)) / 1000.0
    total_energy_kwh = float(ibm_kwh or 0) + float(vcenter_kwh or 0)
    return {
        "meta": {"name": dc_code, "location": DC_LOCATIONS.get(dc_code, "Unknown Data Center")},
        "intel": {
            "clusters": int(vmware_counts[0] or 0),
            "hosts": int((nutanix_host_count or 0) + (vmware_counts[1] or 0)),
            "vms": int(nutanix_vms or 0) + int(vmware_counts[2] or 0),
            "cpu_cap": round(n_cpu_cap_ghz + v_cpu_cap_ghz, 2),
            "cpu_used": round(n_cpu_used_ghz + v_cpu_used_ghz, 2),
            "ram_cap": round(n_mem_cap_gb + v_mem_cap_gb, 2),
            "ram_used": round(n_mem_used_gb + v_mem_used_gb, 2),
            "storage_cap": round(n_stor_cap_tb + v_stor_cap_tb, 2),
            "storage_used": round(n_stor_used_tb + v_stor_used_tb, 2),
        },
        "power": {
            "hosts": int(power_hosts or 0),
            "vms": int(power_lpar_count or 0),
            "vios": int(power_vios or 0),
            "lpar_count": int(power_lpar_count or 0),
            "cpu_total_procunits": round(float(power_cpu[0] or 0), 2),
            "cpu_total_cores": round(float(power_cpu[0] or 0) * 8.0, 2),
            "cpu_available_procunits": round(float(power_cpu[1] or 0), 2),
            "cpu_available_cores": round(float(power_cpu[1] or 0) * 8.0, 2),
            "cpu_used": round(float(power_cpu[2] or 0), 2),
            "cpu_assigned": round(float(power_cpu[3] or 0), 2),
            "memory_total": round(float(power_mem[0] or 0) / 1024.0, 2),
            "memory_available": round(float(power_mem[1] or 0) / 1024.0, 2),
            "memory_assigned": round(float(power_mem[2] or 0) / 1024.0, 2),
        },
        "energy": {
            "total_kw": round(total_energy_kw, 2),
            "ibm_kw": round(float(ibm_w or 0) / 1000.0, 2),
            "vcenter_kw": round(float(vcenter_w or 0) / 1000.0, 2),
            "total_kwh": round(total_energy_kwh, 2),
            "ibm_kwh": round(float(ibm_kwh or 0), 2),
            "vcenter_kwh": round(float(vcenter_kwh or 0), 2),
        },
        "platforms": {
            "nutanix": {"hosts": int(nutanix_host_count or 0), "vms": int(nutanix_vms or 0)},
            "vmware": {"clusters": int(vmware_counts[0] or 0), "hosts": int(vmware_counts[1] or 0), "vms": int(vmware_counts[2] or 0)},
            "ibm": {"hosts": int(power_hosts or 0), "vios": int(power_vios or 0), "lpars": int(power_lpar_count or 0)},
        },
    }


def rebuild_summary(service, time_range: dict | None = None) -> list[dict]:
    tr = time_range or default_time_range()
    start_ts, end_ts = time_range_to_bounds(tr)
    service._dc_list = service._load_dc_list()
    dc_list = service._dc_list
    logger.info("Rebuilding summary for %d DCs (batch fetch + aggregate)...", len(dc_list))
    t_total_start = time.perf_counter()
    try:
        all_dc_data, platform_counts = service._fetch_all_batch(dc_list, start_ts, end_ts)
        logger.info("Summary rebuild: batch queries finished in %.2fs.", time.perf_counter() - t_total_start)
    except Exception as exc:
        if exc.__class__.__name__ != "OperationalError":
            raise
        logger.error("DB unavailable for get_all_datacenters_summary: %s", exc)
        all_dc_data = {dc: empty_dc(dc) for dc in dc_list}
        platform_counts = {dc: 0 for dc in dc_list}
    summary_list = []
    range_suffix = f"{tr.get('start','')}:{tr.get('end','')}"
    for dc in dc_list:
        d = all_dc_data.get(dc, empty_dc(dc))
        intel = d["intel"]
        power = d["power"]
        host_count = (intel["hosts"] or 0) + (power["hosts"] or 0)
        vm_count = (intel["vms"] or 0) + (power.get("vms", 0) or 0)
        cache.set(f"dc_details:{dc}:{range_suffix}", d)
        if host_count == 0 and vm_count == 0:
            continue
        cpu_cap = intel["cpu_cap"] or 0
        cpu_used = intel["cpu_used"] or 0
        ram_cap = intel["ram_cap"] or 0
        ram_used = intel["ram_used"] or 0
        stor_cap = intel["storage_cap"] or 0
        stor_used = intel["storage_used"] or 0
        summary_list.append({
            "id": dc,
            "name": dc,
            "location": d["meta"]["location"],
            "status": "Healthy",
            "platform_count": platform_counts.get(dc, 0),
            "cluster_count": intel["clusters"],
            "host_count": host_count,
            "vm_count": vm_count,
            "stats": {
                "total_cpu": f"{cpu_used:,} / {cpu_cap:,} GHz",
                "used_cpu_pct": round((cpu_used / cpu_cap * 100) if cpu_cap > 0 else 0, 1),
                "total_ram": f"{ram_used:,} / {ram_cap:,} GB",
                "used_ram_pct": round((ram_used / ram_cap * 100) if ram_cap > 0 else 0, 1),
                "total_storage": f"{stor_used:,} / {stor_cap:,} TB",
                "used_storage_pct": round((stor_used / stor_cap * 100) if stor_cap > 0 else 0, 1),
                "last_updated": "Live",
                "total_energy_kw": d["energy"]["total_kw"],
                "ibm_kw": d["energy"].get("ibm_kw", 0.0),
                "vcenter_kw": d["energy"].get("vcenter_kw", 0.0),
            },
        })
    nutanix_h = nutanix_v = vmware_c = vmware_h = vmware_v = ibm_h = ibm_v = ibm_l = 0
    cpu_cap = cpu_used = ram_cap = ram_used = stor_cap = stor_used = ei = ev = 0.0
    for d in all_dc_data.values():
        p = d.get("platforms", {})
        nutanix_h += p.get("nutanix", {}).get("hosts", 0)
        nutanix_v += p.get("nutanix", {}).get("vms", 0)
        vmware_c += p.get("vmware", {}).get("clusters", 0)
        vmware_h += p.get("vmware", {}).get("hosts", 0)
        vmware_v += p.get("vmware", {}).get("vms", 0)
        ibm_h += p.get("ibm", {}).get("hosts", 0)
        ibm_v += p.get("ibm", {}).get("vios", 0)
        ibm_l += p.get("ibm", {}).get("lpars", 0)
        i = d.get("intel", {})
        cpu_cap += float(i.get("cpu_cap", 0) or 0)
        cpu_used += float(i.get("cpu_used", 0) or 0)
        ram_cap += float(i.get("ram_cap", 0) or 0)
        ram_used += float(i.get("ram_used", 0) or 0)
        stor_cap += float(i.get("storage_cap", 0) or 0)
        stor_used += float(i.get("storage_used", 0) or 0)
        e = d.get("energy", {})
        ei += float(e.get("ibm_kw", 0) or 0)
        ev += float(e.get("vcenter_kw", 0) or 0)
    overview = {
        "dc_count": len(summary_list),
        "total_hosts": sum(s["host_count"] for s in summary_list),
        "total_vms": sum(s["vm_count"] for s in summary_list),
        "total_platforms": sum(s["platform_count"] for s in summary_list),
        "total_energy_kw": round(sum(s["stats"]["total_energy_kw"] for s in summary_list), 2),
        "total_cpu_cap": round(cpu_cap, 2),
        "total_cpu_used": round(cpu_used, 2),
        "total_ram_cap": round(ram_cap, 2),
        "total_ram_used": round(ram_used, 2),
        "total_storage_cap": round(stor_cap, 2),
        "total_storage_used": round(stor_used, 2),
    }
    cache.set(f"global_dashboard:{range_suffix}", {
        "overview": overview,
        "platforms": {
            "nutanix": {"hosts": nutanix_h, "vms": nutanix_v},
            "vmware": {"clusters": vmware_c, "hosts": vmware_h, "vms": vmware_v},
            "ibm": {"hosts": ibm_h, "vios": ibm_v, "lpars": ibm_l},
        },
        "energy_breakdown": {"ibm_kw": round(ei, 2), "vcenter_kw": round(ev, 2)},
    })
    cache.set(f"all_dc_summary:{range_suffix}", summary_list)
    logger.info("Rebuilt summary for %d DCs in %.2fs.", len(summary_list), time.perf_counter() - t_total_start)
    return summary_list
