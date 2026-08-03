from __future__ import annotations

import logging
from typing import Callable

from app.db.queries import customer as cq
from app.services.customer_mapping_resolver import ResolvedSourcePatterns, dedupe_zerto_vpgs
from app.utils.time_range import default_time_range, time_range_to_bounds
from shared.backup.policy_classification import (
    load_policy_panel_mapping,
    policy_types_for_category,
)
from shared.backup.vm_role import annotate_vm_roles, sum_billable_virt_resources
from shared.licensing.os_source import with_os_family
from shared.nutanix import snapshot_helpers as nsnap
from shared.vmware.host_cpu_ghz import (
    DEFAULT_HOST_CPU_GHZ,
    NETBOX_HOST_CPU_STRINGS,
    cached_host_map,
    enrich_customer_vm_cpu_list,
    sum_cpu_real_total,
    sum_cpu_used_ghz_avg_total,
    sum_cpu_used_ghz_max_total,
)

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

    def _resolve_patterns(
        self,
        source_patterns: ResolvedSourcePatterns | None,
        source_key: str,
        fallback: str,
    ) -> list[str]:
        """Resolved patterns are final — never re-shape them here.

        shared.customer.match decided the semantics when the rule was turned into
        a pattern. Inferring intent from the pattern string (e.g. "no % means it
        needs wrapping") re-broadened exact rules back into contains, and would
        misread an escaped literal % as a wildcard.
        """
        if source_patterns:
            patterns = [p for p in source_patterns.ilike_patterns(source_key) if (p or "").strip()]
            if patterns:
                return patterns
        return [fallback]

    @staticmethod
    def session_types_from_unique_job_rows(rows: list | tuple | None) -> list[dict]:
        """Build Sessions-by-Type rows from ``CUSTOMER_VEEAM_UNIQUE_JOBS_LATEST`` tuples.

        Column index 3 is ``type`` (Backup / VSphereReplica / …). Used when
        ``raw_veeam_sessions`` has no matching rows but jobs_states does.
        """
        type_counts: dict[str, int] = {}
        for r in rows or []:
            if not r or len(r) < 4 or r[3] is None:
                continue
            job_type = str(r[3]).strip()
            if not job_type:
                continue
            type_counts[job_type] = type_counts.get(job_type, 0) + 1
        return [
            {"type": t, "count": c}
            for t, c in sorted(type_counts.items(), key=lambda item: (-item[1], item[0]))
        ]

    @staticmethod
    def partition_veeam_session_types(
        session_types: list[dict] | None,
    ) -> dict[str, list[dict]]:
        """Split Sessions-by-Type rows into replica / backup / other buckets.

        Uses ``classify_veeam_session_or_job_type`` on each row's ``type``
        (session_type primary, jobs.type fallback already merged upstream).
        """
        from shared.backup.replica_classifier import classify_veeam_session_or_job_type

        buckets: dict[str, list[dict]] = {
            "replica": [],
            "backup": [],
            "image_backup": [],
            "application_backup": [],
            "other": [],
        }
        for row in session_types or []:
            if not isinstance(row, dict):
                continue
            label = classify_veeam_session_or_job_type(str(row.get("type") or ""))
            if label == "backup":
                buckets["backup"].append(row)
                buckets["image_backup"].append(row)
            elif label == "image_backup":
                buckets["image_backup"].append(row)
                buckets["backup"].append(row)
            elif label == "application_backup":
                buckets["application_backup"].append(row)
            elif label in buckets:
                buckets[label].append(row)
            else:
                buckets["other"].append(row)
        return buckets

    def _enrich_customer_vm_list(self, cursor, vm_list: list[dict]) -> list[dict]:
        def _loader():
            return self._run_rows(cursor, NETBOX_HOST_CPU_STRINGS)

        host_map = cached_host_map(_loader, default_ghz=DEFAULT_HOST_CPU_GHZ)
        return enrich_customer_vm_cpu_list(vm_list, host_map, default_ghz=DEFAULT_HOST_CPU_GHZ)

    @staticmethod
    def _empty_resource_bucket() -> dict[str, float | int]:
        return {"vm_count": 0, "cpu": 0.0, "memory_gb": 0.0, "disk_gb": 0.0}

    @classmethod
    def _sum_replica_resources_by_role(
        cls,
        replica_vm_list: list[dict] | None,
    ) -> dict[str, dict[str, float | int]]:
        """Roll up replica/DR VM footprint by role (veeam_dr / zerto / altra / custom)."""
        roles = ("veeam_dr", "zerto", "altra_replica", "custom")
        out: dict[str, dict[str, float | int]] = {
            role: cls._empty_resource_bucket() for role in roles
        }
        totals = cls._empty_resource_bucket()
        for row in replica_vm_list or []:
            role = str(row.get("role") or "custom").strip().lower()
            if role not in out:
                role = "custom"
            bucket = out[role]
            cpu = float(row.get("cpu") or 0.0)
            mem = float(row.get("memory_gb") or 0.0)
            disk = float(row.get("disk_gb") or 0.0)
            bucket["vm_count"] = int(bucket["vm_count"]) + 1
            bucket["cpu"] = float(bucket["cpu"]) + cpu
            bucket["memory_gb"] = float(bucket["memory_gb"]) + mem
            bucket["disk_gb"] = float(bucket["disk_gb"]) + disk
            totals["vm_count"] = int(totals["vm_count"]) + 1
            totals["cpu"] = float(totals["cpu"]) + cpu
            totals["memory_gb"] = float(totals["memory_gb"]) + mem
            totals["disk_gb"] = float(totals["disk_gb"]) + disk
        for role, bucket in out.items():
            out[role] = {
                "vm_count": int(bucket["vm_count"]),
                "cpu": round(float(bucket["cpu"]), 3),
                "memory_gb": round(float(bucket["memory_gb"]), 3),
                "disk_gb": round(float(bucket["disk_gb"]), 3),
            }
        out["totals"] = {
            "vm_count": int(totals["vm_count"]),
            "cpu": round(float(totals["cpu"]), 3),
            "memory_gb": round(float(totals["memory_gb"]), 3),
            "disk_gb": round(float(totals["disk_gb"]), 3),
        }
        return out

    @classmethod
    def _merge_replica_role_totals(
        cls,
        left: dict[str, dict[str, float | int]] | None,
        right: dict[str, dict[str, float | int]] | None,
    ) -> dict[str, dict[str, float | int]]:
        roles = ("veeam_dr", "zerto", "altra_replica", "custom", "totals")
        merged: dict[str, dict[str, float | int]] = {
            role: cls._empty_resource_bucket() for role in roles
        }
        for src in (left or {}, right or {}):
            for role in roles:
                bucket = src.get(role) or {}
                dest = merged[role]
                dest["vm_count"] = int(dest["vm_count"]) + int(bucket.get("vm_count") or 0)
                dest["cpu"] = float(dest["cpu"]) + float(bucket.get("cpu") or 0.0)
                dest["memory_gb"] = float(dest["memory_gb"]) + float(
                    bucket.get("memory_gb") or 0.0
                )
                dest["disk_gb"] = float(dest["disk_gb"]) + float(bucket.get("disk_gb") or 0.0)
        for role, bucket in merged.items():
            merged[role] = {
                "vm_count": int(bucket["vm_count"]),
                "cpu": round(float(bucket["cpu"]), 3),
                "memory_gb": round(float(bucket["memory_gb"]), 3),
                "disk_gb": round(float(bucket["disk_gb"]), 3),
            }
        return merged

    @staticmethod
    def _apply_vm_roles_and_billable_totals(
        vm_list: list[dict],
        *,
        zerto_names: list[str] | None = None,
    ) -> tuple[list[dict], list[dict], dict[str, float | int], dict[str, dict[str, float | int]]]:
        """Annotate VM roles; split billable vs replica; return role replica totals.

        Returns ``(billable_vm_list, replica_vm_list, billable_totals, replica_by_role)``.
        """
        annotated = annotate_vm_roles(vm_list, zerto_names=zerto_names)
        billable = [r for r in annotated if r.get("virt_billable") is not False]
        replicas = [r for r in annotated if r.get("virt_billable") is False]
        totals = sum_billable_virt_resources(annotated)
        replica_by_role = CustomerAdapter._sum_replica_resources_by_role(replicas)
        return billable, replicas, totals, replica_by_role

    def fetch(
        self,
        customer_name: str,
        time_range: dict,
        managed_nutanix_clusters: list[str] | None = None,
        pure_nutanix_clusters: list[str] | None = None,
        infra_search_name: str | None = None,
        source_patterns: ResolvedSourcePatterns | None = None,
    ) -> dict:
        tr = time_range or default_time_range()
        search = (infra_search_name or customer_name or "").strip()
        fallback = f"%{search}%" if search else "%"

        vm_patterns = self._resolve_patterns(source_patterns, "virtualization", fallback)
        vm_pattern = vm_patterns[0]
        lpar_pattern = vm_pattern
        veeam_patterns = self._resolve_patterns(source_patterns, "backup_veeam", fallback)
        storage_patterns = self._resolve_patterns(source_patterns, "storage_ibm", fallback)
        storage_like_pattern = storage_patterns[0]
        netbackup_patterns = self._resolve_patterns(source_patterns, "backup_netbackup", fallback)
        # COLUMN ASYMMETRY — summary/unique-jobs match workloaddisplayname (ILIKE ANY
        # over all enabled backup_netbackup patterns). Unmapped classifier decides on
        # policyname. The two sides key on different columns; fixing attribution is a
        # product decision (see Unmapped alias lessons).
        nutanix_snap_patterns = self._resolve_patterns(source_patterns, "backup_nutanix", fallback)
        zerto_patterns = self._resolve_patterns(source_patterns, "backup_zerto", fallback)

        managed = list(managed_nutanix_clusters or [])
        pure = list(pure_nutanix_clusters or [])

        start_ts, end_ts = time_range_to_bounds(tr)

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

                classic_deleted_rows = self._run_rows(
                    cur, cq.CUSTOMER_CLASSIC_DELETED_VM_NAMES, (vm_pattern, start_ts, end_ts)
                )
                classic_deleted_vm_list = [str(r[0]) for r in (classic_deleted_rows or []) if r and r[0]]

                # VM CPU usage percent (VMware cpu_usage_*_mhz is 0-100%%; Nutanix /10000 in SQL).
                classic_vm_rows = self._run_rows(
                    cur,
                    cq.CUSTOMER_CLASSIC_VM_LIST,
                    (vm_pattern, start_ts, end_ts, vm_pattern, start_ts, end_ts),
                )
                classic_vm_list = [
                    with_os_family({
                        "name": r[0],
                        "source": r[1],
                        "cluster": r[2],
                        "vmhost": r[3],
                        "cpu": float(r[4] or 0.0),
                        "cpu_pct_min": float(r[5] or 0.0),
                        "cpu_pct_avg": float(r[6] or 0.0),
                        "cpu_pct_max": float(r[7] or 0.0),
                        "cpu_mhz_min": float(r[5] or 0.0),
                        "cpu_mhz_avg": float(r[6] or 0.0),
                        "cpu_mhz_max": float(r[7] or 0.0),
                        "memory_gb": float(r[8] or 0.0),
                        "mem_pct_min": float(r[9] or 0.0),
                        "mem_pct_avg": float(r[10] or 0.0),
                        "mem_pct_max": float(r[11] or 0.0),
                        "disk_gb": float(r[12] or 0.0),
                        "disk_used_min_gb": float(r[13] or 0.0),
                        "disk_used_max_gb": float(r[14] or 0.0),
                        "guest_os": r[15],
                    })
                    for r in (classic_vm_rows or [])
                    if r and r[0]
                ]
                classic_vm_list = self._enrich_customer_vm_list(cur, classic_vm_list)
                zerto_name_rows = self._run_rows(
                    cur,
                    cq.CUSTOMER_ZERTO_VM_NAMES,
                    (start_ts, end_ts, zerto_patterns, start_ts, end_ts),
                )
                zerto_names = [str(r[0]) for r in (zerto_name_rows or []) if r and r[0]]
                classic_vm_list, classic_replica_vm_list, classic_virt, classic_replica_totals = (
                    self._apply_vm_roles_and_billable_totals(
                        classic_vm_list, zerto_names=zerto_names
                    )
                )
                classic_vm_count = int(classic_virt.get("vm_count") or 0)
                classic_cpu = float(classic_virt.get("cpu") or 0.0)
                classic_mem_gb = float(classic_virt.get("memory_gb") or 0.0)
                classic_disk_gb = float(classic_virt.get("disk_gb") or 0.0)
                billable_classic = classic_vm_list
                classic_cpu_real = sum_cpu_real_total(billable_classic)
                classic_cpu_used_avg = sum_cpu_used_ghz_avg_total(billable_classic)
                classic_cpu_used_max = sum_cpu_used_ghz_max_total(billable_classic)

                # --- Hyperconverged (non-KM VMware + all Nutanix, filtered by vm_name only) ---
                hc_params = (
                    vm_pattern,
                    start_ts,
                    end_ts,
                    vm_pattern,
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

                hc_deleted_rows = self._run_rows(cur, cq.CUSTOMER_HYPERCONV_DELETED_VM_NAMES, hc_params)
                hc_deleted_vm_list = [str(r[0]) for r in (hc_deleted_rows or []) if r and r[0]]

                hc_list_params = (
                    vm_pattern,
                    start_ts,
                    end_ts,
                    vm_pattern,
                    start_ts,
                    end_ts,
                    vm_pattern,   # netbox_os guest-OS fallback CTE
                    vm_pattern,
                    start_ts,
                    end_ts,
                    vm_pattern,
                    start_ts,
                    end_ts,
                )
                hc_vm_rows = self._run_rows(cur, cq.CUSTOMER_HYPERCONV_VM_LIST, hc_list_params)
                hc_vm_list = [
                    with_os_family({
                        "name": r[0],
                        "source": r[1],
                        "cluster": r[2],
                        "vmhost": r[3],
                        "cpu": float(r[4] or 0.0),
                        "cpu_pct_min": float(r[5] or 0.0),
                        "cpu_pct_avg": float(r[6] or 0.0),
                        "cpu_pct_max": float(r[7] or 0.0),
                        "cpu_mhz_min": float(r[5] or 0.0),
                        "cpu_mhz_avg": float(r[6] or 0.0),
                        "cpu_mhz_max": float(r[7] or 0.0),
                        "memory_gb": float(r[8] or 0.0),
                        "mem_pct_min": float(r[9] or 0.0),
                        "mem_pct_avg": float(r[10] or 0.0),
                        "mem_pct_max": float(r[11] or 0.0),
                        "disk_gb": float(r[12] or 0.0),
                        "disk_used_min_gb": float(r[13] or 0.0),
                        "disk_used_max_gb": float(r[14] or 0.0),
                        "guest_os": r[15],
                    })
                    for r in (hc_vm_rows or [])
                    if r and r[0]
                ]
                hc_vm_list = self._enrich_customer_vm_list(cur, hc_vm_list)
                hc_vm_list, hc_replica_vm_list, hc_virt, hc_replica_totals = self._apply_vm_roles_and_billable_totals(
                    hc_vm_list, zerto_names=zerto_names
                )
                hc_total = int(hc_virt.get("vm_count") or 0)
                hc_cpu = float(hc_virt.get("cpu") or 0.0)
                hc_mem_gb = float(hc_virt.get("memory_gb") or 0.0)
                hc_disk_gb = float(hc_virt.get("disk_gb") or 0.0)
                billable_hc = hc_vm_list
                hc_cpu_real = sum_cpu_real_total(billable_hc)
                hc_cpu_used_avg = sum_cpu_used_ghz_avg_total(billable_hc)
                hc_cpu_used_max = sum_cpu_used_ghz_max_total(billable_hc)

                # --- Pure Nutanix (AHV-only clusters, cluster lookup uses latest — no time filter) ---
                pure_params = (pure, vm_pattern, start_ts, end_ts)
                pure_vm_count = int(
                    self._run_value(cur, cq.CUSTOMER_PURE_NUTANIX_VM_COUNT, pure_params) or 0
                )
                pure_res = self._run_row(cur, cq.CUSTOMER_PURE_NUTANIX_RESOURCE_TOTALS, pure_params)
                pure_cpu = float(pure_res[0] or 0.0) if pure_res else 0.0
                pure_mem_gb = float(pure_res[1] or 0.0) if pure_res else 0.0
                pure_disk_gb = float(pure_res[2] or 0.0) if pure_res else 0.0

                pure_deleted_rows = self._run_rows(
                    cur, cq.CUSTOMER_PURE_NUTANIX_DELETED_VM_NAMES, pure_params
                )
                pure_deleted_vm_list = [str(r[0]) for r in (pure_deleted_rows or []) if r and r[0]]

                pure_list_params = (
                    pure,
                    vm_pattern,
                    start_ts,
                    end_ts,
                    vm_pattern,
                    start_ts,
                    end_ts,
                    vm_pattern,   # netbox_os guest-OS fallback CTE
                )
                pure_vm_rows = self._run_rows(cur, cq.CUSTOMER_PURE_NUTANIX_VM_LIST, pure_list_params)
                pure_vm_list = [
                    with_os_family({
                        "name": r[0],
                        "source": r[1],
                        "cluster": r[2],
                        "cpu": float(r[3] or 0.0),
                        "cpu_pct_min": float(r[4] or 0.0),
                        "cpu_pct_avg": float(r[5] or 0.0),
                        "cpu_pct_max": float(r[6] or 0.0),
                        "cpu_mhz_min": float(r[4] or 0.0),
                        "cpu_mhz_avg": float(r[5] or 0.0),
                        "cpu_mhz_max": float(r[6] or 0.0),
                        "memory_gb": float(r[7] or 0.0),
                        "mem_pct_min": float(r[8] or 0.0),
                        "mem_pct_avg": float(r[9] or 0.0),
                        "mem_pct_max": float(r[10] or 0.0),
                        "disk_gb": float(r[11] or 0.0),
                        "disk_used_min_gb": float(r[12] or 0.0),
                        "disk_used_max_gb": float(r[13] or 0.0),
                        "guest_os": r[14],
                    })
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
                power_deleted_rows = self._run_rows(
                    cur, cq.CUSTOMER_POWER_DELETED_LPAR_NAMES, (lpar_pattern, start_ts, end_ts)
                )
                power_deleted_vm_list = [str(r[0]) for r in (power_deleted_rows or []) if r and r[0]]

                power_lpar_detail_rows = self._run_rows(
                    cur,
                    cq.CUSTOMER_POWER_LPAR_DETAIL_LIST,
                    (
                        lpar_pattern,
                        start_ts,
                        end_ts,
                        lpar_pattern,
                        start_ts,
                        end_ts,
                        start_ts,
                        end_ts,
                        start_ts,
                        end_ts,
                    ),
                )
                power_vm_list = [
                    with_os_family({
                        "name": r[0],
                        "lpar_name": r[1],
                        "source": r[2],
                        "cpu": float(r[3] or 0.0),
                        "cpu_pct_min": float(r[4] or 0.0),
                        "cpu_pct_avg": float(r[5] or 0.0),
                        "cpu_pct_max": float(r[6] or 0.0),
                        "memory_gb": float(r[7] or 0.0),
                        "mem_pct_min": float(r[8] or 0.0),
                        "mem_pct_avg": float(r[9] or 0.0),
                        "mem_pct_max": float(r[10] or 0.0),
                        "disk_gb": float(r[11] or 0.0),
                        "disk_used_min_gb": float(r[12] or 0.0),
                        "disk_used_max_gb": float(r[13] or 0.0),
                        "state": r[14],
                        "guest_os": r[15],
                    })
                    for r in (power_lpar_detail_rows or [])
                    if r and r[0]
                ]
                power_disk_total = sum(float(row.get("disk_gb") or 0.0) for row in power_vm_list)

                veeam_defined_sessions = int(
                    self._run_value(cur, cq.CUSTOMER_VEEAM_DEFINED_SESSIONS, (veeam_patterns,)) or 0
                )
                veeam_type_rows = self._run_rows(
                    cur, cq.CUSTOMER_VEEAM_SESSION_TYPES, (veeam_patterns,)
                )
                veeam_types = [
                    {"type": str(r[0]).strip() or "Unknown", "count": int(r[1] or 0)}
                    for r in (veeam_type_rows or [])
                    if r and r[0] is not None
                ]
                veeam_platform_rows = self._run_rows(
                    cur, cq.CUSTOMER_VEEAM_SESSION_PLATFORMS, (veeam_patterns,)
                )
                veeam_platforms = [
                    {"platform": str(r[0]).strip() or "Unknown", "count": int(r[1] or 0)}
                    for r in (veeam_platform_rows or [])
                    if r and r[0] is not None
                ]
                if not veeam_types:
                    try:
                        unique_job_rows = self._run_rows(
                            cur,
                            cq.CUSTOMER_VEEAM_UNIQUE_JOBS_LATEST,
                            (veeam_patterns, start_ts, end_ts),
                        )
                        veeam_types = self.session_types_from_unique_job_rows(
                            unique_job_rows or []
                        )
                    except Exception as exc:
                        from app.services.customer_service import _is_fatal_db_error

                        if _is_fatal_db_error(exc):
                            raise
                        logger.warning(
                            "Veeam session_types fallback from unique jobs failed: %s",
                            exc,
                        )
                # Sessions table can be empty while jobs_states still has rows —
                # keep the Sessions by Type KPI in sync with the fallback inventory.
                if veeam_defined_sessions == 0 and veeam_types:
                    veeam_defined_sessions = sum(int(t.get("count") or 0) for t in veeam_types)

                veeam_type_buckets = self.partition_veeam_session_types(veeam_types)

                netbackup_summary_row = self._run_row(
                    cur,
                    cq.CUSTOMER_NETBACKUP_BACKUP_SUMMARY,
                    (netbackup_patterns, start_ts, end_ts),
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

                mapping = load_policy_panel_mapping()
                image_policy_types = [
                    str(t).strip().upper()
                    for t in (mapping.get("image_policy_types") or ["VMWARE"])
                    if str(t).strip()
                ] or ["VMWARE"]
                empty_cat = {
                    "pre_dedup_size_gib": 0.0,
                    "post_dedup_size_gib": 0.0,
                    "deduplication_factor": "1x",
                }
                netbackup_by_category = {"image": dict(empty_cat), "application": dict(empty_cat)}
                try:
                    cat_rows = self._run_rows(
                        cur,
                        cq.CUSTOMER_NETBACKUP_BACKUP_SUMMARY_BY_CATEGORY,
                        (image_policy_types, netbackup_patterns, start_ts, end_ts),
                    )
                    for r in cat_rows or []:
                        if not r or not r[0]:
                            continue
                        cat = str(r[0]).strip().lower()
                        if cat not in netbackup_by_category:
                            continue
                        netbackup_by_category[cat] = {
                            "pre_dedup_size_gib": float(r[1] or 0.0),
                            "post_dedup_size_gib": float(r[2] or 0.0),
                            "deduplication_factor": r[3] if r[3] else "1x",
                        }
                except Exception as exc:
                    from app.services.customer_service import _is_fatal_db_error

                    if _is_fatal_db_error(exc):
                        raise
                    logger.warning("CUSTOMER_NETBACKUP_BACKUP_SUMMARY_BY_CATEGORY failed: %s", exc)

                netbackup_policy_types_all: list[str] = []
                try:
                    pt_rows = self._run_rows(
                        cur,
                        cq.CUSTOMER_NETBACKUP_POLICY_TYPES,
                        (netbackup_patterns, start_ts, end_ts),
                    )
                    netbackup_policy_types_all = [
                        str(r[0]) for r in (pt_rows or []) if r and r[0] is not None
                    ]
                except Exception as exc:
                    from app.services.customer_service import _is_fatal_db_error

                    if _is_fatal_db_error(exc):
                        raise
                    logger.warning("CUSTOMER_NETBACKUP_POLICY_TYPES failed: %s", exc)

                netbackup_policy_types = {
                    "image": policy_types_for_category(
                        "image", netbackup_policy_types_all, mapping=mapping
                    ),
                    "application": policy_types_for_category(
                        "application", netbackup_policy_types_all, mapping=mapping
                    ),
                }

                nutanix_snap_rows: list[dict] = []
                nutanix_snap_totals: dict = nsnap.aggregate_snapshots([])
                nutanix_snap_as_of = ""
                try:
                    raw_snaps = self._run_rows(
                        cur,
                        cq.CUSTOMER_NUTANIX_SNAPSHOTS_BY_CUSTOMER,
                        (nutanix_snap_patterns, nutanix_snap_patterns, start_ts, end_ts),
                    )
                    nutanix_snap_rows, nutanix_snap_as_of = nsnap.enrich_snapshot_rows(
                        raw_snaps, None
                    )
                    nutanix_snap_totals = nsnap.aggregate_snapshots(nutanix_snap_rows)
                except Exception as exc:
                    from app.services.customer_service import _is_fatal_db_error

                    if _is_fatal_db_error(exc):
                        raise
                    logger.warning("CUSTOMER_NUTANIX_SNAPSHOTS_BY_CUSTOMER failed: %s", exc)

                zerto_protected_vms = int(
                    self._run_value(
                        cur,
                        cq.CUSTOMER_ZERTO_PROTECTED_VMS,
                        (start_ts, end_ts, zerto_patterns),
                    )
                    or 0
                )

                zerto_provisioned_rows = self._run_rows(
                    cur,
                    cq.CUSTOMER_ZERTO_PROVISIONED_STORAGE,
                    (zerto_patterns,),
                )
                zerto_vpgs = [
                    {
                        "name": r[0],
                        "provisioned_storage_gib": float(r[1] or 0.0),
                    }
                    for r in (zerto_provisioned_rows or [])
                    if r and r[0]
                ]
                zerto_vpgs = dedupe_zerto_vpgs(zerto_vpgs)
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
                    from app.services.customer_service import _is_fatal_db_error

                    if _is_fatal_db_error(exc):
                        raise
                    logger.warning("CUSTOMER_STORAGE_VOLUME_CAPACITY failed: %s", exc)

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
                "cpu_real_total": classic_cpu_real,
                "cpu_used_ghz_avg_total": classic_cpu_used_avg,
                "cpu_used_ghz_max_total": classic_cpu_used_max,
                "memory_gb": classic_mem_gb,
                "disk_gb": classic_disk_gb,
                "vm_list": classic_vm_list,
                "replica_vm_list": classic_replica_vm_list,
                "replica_vm_count": len(classic_replica_vm_list),
                "deleted_vm_list": classic_deleted_vm_list,
            },
            "hyperconv": {
                "vm_count": hc_total,
                "vmware_only": hc_vmware_only,
                "nutanix_count": hc_nutanix,
                "managed_nutanix_clusters": len(managed),
                "cpu_total": hc_cpu,
                "cpu_real_total": hc_cpu_real,
                "cpu_used_ghz_avg_total": hc_cpu_used_avg,
                "cpu_used_ghz_max_total": hc_cpu_used_max,
                "memory_gb": hc_mem_gb,
                "disk_gb": hc_disk_gb,
                "vm_list": hc_vm_list,
                "replica_vm_list": hc_replica_vm_list,
                "replica_vm_count": len(hc_replica_vm_list),
                "deleted_vm_list": hc_deleted_vm_list,
            },
            "pure_nutanix": {
                "vm_count": pure_vm_count,
                "cpu_total": pure_cpu,
                "memory_gb": pure_mem_gb,
                "disk_gb": pure_disk_gb,
                "vm_list": pure_vm_list,
                "cluster_count": len(pure),
                "deleted_vm_list": pure_deleted_vm_list,
            },
            "power": {
                "cpu_total": power_cpu,
                "lpar_count": power_lpars,
                "memory_total_gb": power_memory,
                "disk_total_gb": power_disk_total,
                "vm_list": power_vm_list,
                "deleted_vm_list": power_deleted_vm_list,
            },
            "backup": {
                "veeam": {
                    "defined_sessions": veeam_defined_sessions,
                    "session_types": veeam_types,
                    "session_type_buckets": veeam_type_buckets,
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
                    "image": netbackup_by_category["image"],
                    "application": netbackup_by_category["application"],
                    "policy_types": netbackup_policy_types,
                },
                "nutanix": {
                    "rows": nutanix_snap_rows,
                    "totals": nutanix_snap_totals,
                    "as_of": nutanix_snap_as_of,
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
                "replication_resources": self._merge_replica_role_totals(
                    classic_replica_totals, hc_replica_totals
                ),
            },
        }

        return {"totals": totals, "assets": assets}

    def _empty_result(self) -> dict:
        _empty_compute = {
            "vm_count": 0,
            "cpu_total": 0.0,
            "cpu_real_total": 0.0,
            "cpu_used_ghz_avg_total": 0.0,
            "cpu_used_ghz_max_total": 0.0,
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
                    "replication_resources": self._sum_replica_resources_by_role([]),
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
                "classic": {**_empty_compute, "deleted_vm_list": []},
                "hyperconv": {
                    **_empty_compute,
                    "vmware_only": 0,
                    "nutanix_count": 0,
                    "managed_nutanix_clusters": 0,
                    "deleted_vm_list": [],
                },
                "pure_nutanix": {**_empty_compute, "cluster_count": 0, "deleted_vm_list": []},
                "power": {
                    "cpu_total": 0.0,
                    "lpar_count": 0,
                    "memory_total_gb": 0.0,
                    "disk_total_gb": 0.0,
                    "vm_list": [],
                    "deleted_vm_list": [],
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
                        "image": {
                            "pre_dedup_size_gib": 0.0,
                            "post_dedup_size_gib": 0.0,
                            "deduplication_factor": "1x",
                        },
                        "application": {
                            "pre_dedup_size_gib": 0.0,
                            "post_dedup_size_gib": 0.0,
                            "deduplication_factor": "1x",
                        },
                        "policy_types": {"image": [], "application": []},
                    },
                    "nutanix": {
                        "rows": [],
                        "totals": {
                            "total_snapshots": 0,
                            "total_size_bytes": 0,
                            "protected_vms": 0,
                            "missing_entities": 0,
                            "schedule_type_breakdown": {},
                            "state_breakdown": {},
                        },
                        "as_of": "",
                    },
                    "license_compliance": [],
                },
            },
        }
