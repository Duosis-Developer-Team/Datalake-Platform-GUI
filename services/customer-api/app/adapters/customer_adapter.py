from __future__ import annotations

import logging
from typing import Callable

from psycopg2 import OperationalError
from psycopg2.pool import PoolError

from app.db.queries import customer as cq
from app.utils.time_range import default_time_range, time_range_to_bounds

logger = logging.getLogger(__name__)


class CustomerAdapter:
    def __init__(
        self,
        get_connection: Callable,
        run_value: Callable,
        run_row: Callable,
        run_rows: Callable,
    ):
        self._get_connection = get_connection
        self._run_value = run_value
        self._run_row = run_row
        self._run_rows = run_rows

    def fetch(
        self,
        customer_name: str,
        time_range: dict,
        managed_nutanix_clusters: list[str] | None = None,
        pure_nutanix_clusters: list[str] | None = None,
    ) -> dict:
        tr = time_range or default_time_range()
        name = (customer_name or "").strip()
        # Broader ILIKE: customer name anywhere in VM name (matches datacenter-api)
        vm_pattern = f"%{name}%" if name else "%"
        lpar_pattern = f"%{name}%" if name else "%"
        veeam_pattern = f"%{name}%" if name else "%"
        storage_like_pattern = f"%{name}%" if name else "%"
        netbackup_workload_pattern = f"%{name}%" if name else "%"
        zerto_name_like = f"%{name}%" if name else "%"

        managed = list(managed_nutanix_clusters or [])
        pure = list(pure_nutanix_clusters or [])

        start_ts, end_ts = time_range_to_bounds(tr)

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    intel_vm_counts = self._run_row(
                        cur,
                        cq.CUSTOMER_INTEL_VM_COUNTS,
                        (vm_pattern, start_ts, end_ts, vm_pattern, start_ts, end_ts),
                    )
                    vmware_vms = int(intel_vm_counts[0] or 0) if intel_vm_counts else 0
                    nutanix_vms = int(intel_vm_counts[1] or 0) if intel_vm_counts else 0
                    intel_vms_total = int(intel_vm_counts[2] or 0) if intel_vm_counts else 0

                    cpu_row = self._run_row(
                        cur,
                        cq.CUSTOMER_INTEL_CPU_TOTALS,
                        (vm_pattern, start_ts, end_ts, vm_pattern, start_ts, end_ts),
                    )
                    intel_cpu_vmware = float(cpu_row[0] or 0.0) if cpu_row else 0.0
                    intel_cpu_nutanix = float(cpu_row[1] or 0.0) if cpu_row else 0.0
                    intel_cpu_total = float(cpu_row[2] or 0.0) if cpu_row else 0.0

                    mem_row = self._run_row(
                        cur,
                        cq.CUSTOMER_INTEL_MEMORY_TOTALS,
                        (vm_pattern, start_ts, end_ts, vm_pattern, start_ts, end_ts),
                    )
                    intel_mem_vmware = float(mem_row[0] or 0.0) if mem_row else 0.0
                    intel_mem_nutanix = float(mem_row[1] or 0.0) if mem_row else 0.0
                    intel_mem_total = float(mem_row[2] or 0.0) if mem_row else 0.0

                    disk_row = self._run_row(
                        cur,
                        cq.CUSTOMER_INTEL_DISK_TOTALS,
                        (vm_pattern, start_ts, end_ts, vm_pattern, start_ts, end_ts),
                    )
                    intel_disk_vmware = float(disk_row[0] or 0.0) if disk_row else 0.0
                    intel_disk_nutanix = float(disk_row[1] or 0.0) if disk_row else 0.0
                    intel_disk_total = float(disk_row[2] or 0.0) if disk_row else 0.0

                    intel_vm_detail_rows = self._run_rows(
                        cur,
                        cq.CUSTOMER_INTEL_VM_DETAIL_LIST,
                        (vm_pattern, start_ts, end_ts, vm_pattern, start_ts, end_ts),
                    )
                    intel_vm_list = [
                        {
                            "name": r[0],
                            "source": r[1],
                            "cpu": float(r[2] or 0.0),
                            "memory_gb": float(r[3] or 0.0),
                            "disk_gb": float(r[4] or 0.0),
                        }
                        for r in (intel_vm_detail_rows or [])
                        if r and r[0]
                    ]

                    # --- Classic Compute (KM clusters) ---
                    classic_vm_count = int(
                        self._run_value(cur, cq.CUSTOMER_CLASSIC_VM_COUNT, (vm_pattern, start_ts, end_ts)) or 0
                    )
                    classic_res = self._run_row(
                        cur, cq.CUSTOMER_CLASSIC_RESOURCE_TOTALS, (vm_pattern, start_ts, end_ts)
                    )
                    classic_cpu = float(classic_res[0] or 0.0) if classic_res else 0.0
                    classic_mem_gb = float(classic_res[1] or 0.0) if classic_res else 0.0
                    classic_disk_gb = float(classic_res[2] or 0.0) if classic_res else 0.0

                    classic_vm_rows = self._run_rows(
                        cur, cq.CUSTOMER_CLASSIC_VM_LIST, (vm_pattern, start_ts, end_ts)
                    )
                    classic_vm_list = [
                        {
                            "name": r[0],
                            "source": r[1],
                            "cluster": r[2],
                            "cpu": float(r[3] or 0.0),
                            "memory_gb": float(r[4] or 0.0),
                            "disk_gb": float(r[5] or 0.0),
                        }
                        for r in (classic_vm_rows or [])
                        if r and r[0]
                    ]

                    # --- Hyperconverged (non-KM VMware + Nutanix on VMware-managed clusters only) ---
                    hc_params = (
                        vm_pattern,
                        start_ts,
                        end_ts,
                        vm_pattern,
                        start_ts,
                        end_ts,
                        managed,
                        start_ts,
                        end_ts,
                    )
                    hc_count_row = self._run_row(cur, cq.CUSTOMER_HYPERCONV_VM_COUNT, hc_params)
                    hc_vmware_only = int(hc_count_row[0] or 0) if hc_count_row else 0
                    hc_nutanix = int(hc_count_row[1] or 0) if hc_count_row else 0
                    hc_total = int(hc_count_row[2] or 0) if hc_count_row else 0

                    hc_res = self._run_row(cur, cq.CUSTOMER_HYPERCONV_RESOURCE_TOTALS, hc_params)
                    hc_cpu = float(hc_res[0] or 0.0) if hc_res else 0.0
                    hc_mem_gb = float(hc_res[1] or 0.0) if hc_res else 0.0
                    hc_disk_gb = float(hc_res[2] or 0.0) if hc_res else 0.0

                    hc_vm_rows = self._run_rows(cur, cq.CUSTOMER_HYPERCONV_VM_LIST, hc_params)
                    hc_vm_list = [
                        {
                            "name": r[0],
                            "source": r[1],
                            "cluster": r[2],
                            "cpu": float(r[3] or 0.0),
                            "memory_gb": float(r[4] or 0.0),
                            "disk_gb": float(r[5] or 0.0),
                        }
                        for r in (hc_vm_rows or [])
                        if r and r[0]
                    ]

                    # --- Pure Nutanix (AHV-only clusters) ---
                    pure_params = (pure, start_ts, end_ts, vm_pattern, start_ts, end_ts)
                    pure_vm_count = int(
                        self._run_value(cur, cq.CUSTOMER_PURE_NUTANIX_VM_COUNT, pure_params) or 0
                    )
                    pure_res = self._run_row(cur, cq.CUSTOMER_PURE_NUTANIX_RESOURCE_TOTALS, pure_params)
                    pure_cpu = float(pure_res[0] or 0.0) if pure_res else 0.0
                    pure_mem_gb = float(pure_res[1] or 0.0) if pure_res else 0.0
                    pure_disk_gb = float(pure_res[2] or 0.0) if pure_res else 0.0

                    pure_vm_rows = self._run_rows(cur, cq.CUSTOMER_PURE_NUTANIX_VM_LIST, pure_params)
                    pure_vm_list = [
                        {
                            "name": r[0],
                            "source": r[1],
                            "cluster": r[2],
                            "cpu": float(r[3] or 0.0),
                            "memory_gb": float(r[4] or 0.0),
                            "disk_gb": float(r[5] or 0.0),
                        }
                        for r in (pure_vm_rows or [])
                        if r and r[0]
                    ]

                    power_cpu = float(
                        self._run_value(cur, cq.CUSTOMER_POWER_CPU_TOTAL, (lpar_pattern, start_ts, end_ts)) or 0.0
                    )
                    power_lpars = int(
                        self._run_value(cur, cq.IBM_LPAR_TOTALS, (lpar_pattern, start_ts, end_ts)) or 0
                    )
                    power_memory = float(
                        self._run_value(cur, cq.CUSTOMER_POWER_MEMORY_TOTAL, (lpar_pattern, start_ts, end_ts))
                        or 0.0
                    )
                    power_lpar_detail_rows = self._run_rows(
                        cur, cq.CUSTOMER_POWER_LPAR_DETAIL_LIST, (lpar_pattern, start_ts, end_ts)
                    )
                    power_vm_list = [
                        {
                            "name": r[0],
                            "source": r[1],
                            "cpu": float(r[2] or 0.0),
                            "memory_gb": float(r[3] or 0.0),
                            "state": r[4],
                        }
                        for r in (power_lpar_detail_rows or [])
                        if r and r[0]
                    ]

                    veeam_defined_sessions = int(
                        self._run_value(cur, cq.CUSTOMER_VEEAM_DEFINED_SESSIONS, (veeam_pattern,)) or 0
                    )
                    veeam_type_rows = self._run_rows(
                        cur, cq.CUSTOMER_VEEAM_SESSION_TYPES, (veeam_pattern,)
                    )
                    veeam_types = [
                        {"type": r[0], "count": int(r[1] or 0)}
                        for r in (veeam_type_rows or [])
                        if r and r[0] is not None
                    ]
                    veeam_platform_rows = self._run_rows(
                        cur, cq.CUSTOMER_VEEAM_SESSION_PLATFORMS, (veeam_pattern,)
                    )
                    veeam_platforms = [
                        {"platform": r[0], "count": int(r[1] or 0)}
                        for r in (veeam_platform_rows or [])
                        if r and r[0] is not None
                    ]

                    netbackup_summary_row = self._run_row(
                        cur,
                        cq.CUSTOMER_NETBACKUP_BACKUP_SUMMARY,
                        (netbackup_workload_pattern, start_ts, end_ts),
                    )
                    netbackup_pre_dedup_gib = (
                        float(netbackup_summary_row[0] or 0.0) if netbackup_summary_row else 0.0
                    )
                    netbackup_post_dedup_gib = (
                        float(netbackup_summary_row[1] or 0.0) if netbackup_summary_row else 0.0
                    )
                    netbackup_dedup_factor = (
                        netbackup_summary_row[2] if netbackup_summary_row and netbackup_summary_row[2] else "1x"
                    )

                    zerto_protected_vms = int(
                        self._run_value(
                            cur,
                            cq.CUSTOMER_ZERTO_PROTECTED_VMS,
                            (start_ts, end_ts, zerto_name_like),
                        )
                        or 0
                    )

                    zerto_provisioned_rows = self._run_rows(
                        cur,
                        cq.CUSTOMER_ZERTO_PROVISIONED_STORAGE,
                        (zerto_name_like,),
                    )
                    zerto_vpgs = [
                        {
                            "name": r[0],
                            "provisioned_storage_gib": float(r[1] or 0.0),
                        }
                        for r in (zerto_provisioned_rows or [])
                        if r and r[0]
                    ]
                    zerto_provisioned_total_gib = sum(v["provisioned_storage_gib"] for v in zerto_vpgs)

                    storage_volume_gb = 0.0
                    try:
                        storage_volume_gb = float(
                            self._run_value(
                                cur,
                                cq.CUSTOMER_STORAGE_VOLUME_CAPACITY,
                                (storage_like_pattern, start_ts, end_ts),
                            )
                            or 0.0
                        )
                    except Exception as exc:
                        logger.warning("CUSTOMER_STORAGE_VOLUME_CAPACITY failed: %s", exc)

        except (OperationalError, PoolError) as exc:
            logger.warning("CustomerAdapter.fetch failed: %s", exc)
            return self._empty_result()

        assets = {
            "intel": {
                "vms": {"vmware": vmware_vms, "nutanix": nutanix_vms, "total": intel_vms_total},
                "cpu": {
                    "vmware": intel_cpu_vmware,
                    "nutanix": intel_cpu_nutanix,
                    "total": intel_cpu_total,
                },
                "memory_gb": {
                    "vmware": intel_mem_vmware,
                    "nutanix": intel_mem_nutanix,
                    "total": intel_mem_total,
                },
                "disk_gb": {
                    "vmware": intel_disk_vmware,
                    "nutanix": intel_disk_nutanix,
                    "total": intel_disk_total,
                },
                "vm_list": intel_vm_list,
            },
            "classic": {
                "vm_count": classic_vm_count,
                "cpu_total": classic_cpu,
                "memory_gb": classic_mem_gb,
                "disk_gb": classic_disk_gb,
                "vm_list": classic_vm_list,
            },
            "hyperconv": {
                "vm_count": hc_total,
                "vmware_only": hc_vmware_only,
                "nutanix_count": hc_nutanix,
                "managed_nutanix_clusters": len(managed),
                "cpu_total": hc_cpu,
                "memory_gb": hc_mem_gb,
                "disk_gb": hc_disk_gb,
                "vm_list": hc_vm_list,
            },
            "pure_nutanix": {
                "vm_count": pure_vm_count,
                "cpu_total": pure_cpu,
                "memory_gb": pure_mem_gb,
                "disk_gb": pure_disk_gb,
                "vm_list": pure_vm_list,
                "cluster_count": len(pure),
            },
            "power": {
                "cpu_total": power_cpu,
                "lpar_count": power_lpars,
                "memory_total_gb": power_memory,
                "vm_list": power_vm_list,
            },
            "backup": {
                "veeam": {
                    "defined_sessions": veeam_defined_sessions,
                    "session_types": veeam_types,
                    "platforms": veeam_platforms,
                },
                "zerto": {
                    "protected_total_vms": zerto_protected_vms,
                    "provisioned_storage_gib_total": zerto_provisioned_total_gib,
                    "vpgs": zerto_vpgs,
                },
                "storage": {
                    "total_volume_capacity_gb": storage_volume_gb,
                },
                "netbackup": {
                    "pre_dedup_size_gib": netbackup_pre_dedup_gib,
                    "post_dedup_size_gib": netbackup_post_dedup_gib,
                    "deduplication_factor": netbackup_dedup_factor,
                },
            },
        }

        totals = {
            "vms_total": intel_vms_total + power_lpars,
            "intel_vms_total": intel_vms_total,
            "classic_vms_total": classic_vm_count,
            "hyperconv_vms_total": hc_total,
            "pure_nutanix_vms_total": pure_vm_count,
            "power_lpar_total": power_lpars,
            "cpu_total": intel_cpu_total + power_cpu,
            "intel_cpu_total": intel_cpu_total,
            "classic_cpu_total": classic_cpu,
            "hyperconv_cpu_total": hc_cpu,
            "pure_nutanix_cpu_total": pure_cpu,
            "power_cpu_total": power_cpu,
            "backup": {
                "veeam_defined_sessions": veeam_defined_sessions,
                "zerto_protected_vms": zerto_protected_vms,
                "storage_volume_gb": storage_volume_gb,
                "netbackup_pre_dedup_gib": netbackup_pre_dedup_gib,
                "netbackup_post_dedup_gib": netbackup_post_dedup_gib,
                "zerto_provisioned_gib": zerto_provisioned_total_gib,
            },
        }

        return {"totals": totals, "assets": assets}

    def _empty_result(self) -> dict:
        _empty_compute = {
            "vm_count": 0,
            "cpu_total": 0.0,
            "memory_gb": 0.0,
            "disk_gb": 0.0,
            "vm_list": [],
        }
        return {
            "totals": {
                "vms_total": 0,
                "intel_vms_total": 0,
                "classic_vms_total": 0,
                "hyperconv_vms_total": 0,
                "pure_nutanix_vms_total": 0,
                "power_lpar_total": 0,
                "cpu_total": 0.0,
                "intel_cpu_total": 0.0,
                "classic_cpu_total": 0.0,
                "hyperconv_cpu_total": 0.0,
                "pure_nutanix_cpu_total": 0.0,
                "power_cpu_total": 0.0,
                "backup": {
                    "veeam_defined_sessions": 0,
                    "zerto_protected_vms": 0,
                    "storage_volume_gb": 0.0,
                    "netbackup_pre_dedup_gib": 0.0,
                    "netbackup_post_dedup_gib": 0.0,
                    "zerto_provisioned_gib": 0.0,
                },
            },
            "assets": {
                "intel": {
                    "vms": {"vmware": 0, "nutanix": 0, "total": 0},
                    "cpu": {"vmware": 0.0, "nutanix": 0.0, "total": 0.0},
                    "memory_gb": {"vmware": 0.0, "nutanix": 0.0, "total": 0.0},
                    "disk_gb": {"vmware": 0.0, "nutanix": 0.0, "total": 0.0},
                    "vm_list": [],
                },
                "classic": {**_empty_compute},
                "hyperconv": {
                    **_empty_compute,
                    "vmware_only": 0,
                    "nutanix_count": 0,
                    "managed_nutanix_clusters": 0,
                },
                "pure_nutanix": {**_empty_compute, "cluster_count": 0},
                "power": {
                    "cpu_total": 0.0,
                    "lpar_count": 0,
                    "memory_total_gb": 0.0,
                    "vm_list": [],
                },
                "backup": {
                    "veeam": {
                        "defined_sessions": 0,
                        "session_types": [],
                        "platforms": [],
                    },
                    "zerto": {
                        "protected_total_vms": 0,
                        "provisioned_storage_gib_total": 0.0,
                        "vpgs": [],
                    },
                    "storage": {
                        "total_volume_capacity_gb": 0.0,
                    },
                    "netbackup": {
                        "pre_dedup_size_gib": 0.0,
                        "post_dedup_size_gib": 0.0,
                        "deduplication_factor": "1x",
                    },
                },
            },
        }
