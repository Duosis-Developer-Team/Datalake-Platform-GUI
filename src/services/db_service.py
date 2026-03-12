import os
import re
import logging
import time
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed

import psycopg2
from psycopg2 import pool as pg_pool
from psycopg2 import OperationalError
from psycopg2.pool import PoolError

from src.queries import nutanix as nq, vmware as vq, ibm as iq, energy as eq
from src.queries import loki as lq, customer as cq, s3 as s3q
from src.services import cache_service as cache
from src.services import query_overrides as qo
from src.utils.time_range import default_time_range, time_range_to_bounds, cache_time_ranges
from src.utils.format_units import smart_cpu, smart_memory, smart_storage

_DC_CODE_RE = re.compile(r'(DC\d+|AZ\d+|ICT\d+|UZ\d+|DH\d+)', re.IGNORECASE)

logger = logging.getLogger(__name__)

# Fallback DC list used when loki_locations is unreachable.
_FALLBACK_DC_LIST = [
    "AZ11", "DC11", "DC12", "DC13", "DC14", "DC15", "DC16", "DC17", "ICT11"
]

# Known DC → human-readable location mapping (for display only; dynamic list drives logic).
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
    "ICT11": "İngiltere",
    "UZ11": "Özbekistan",
}


def _empty_compute_section() -> dict:
    """Return a zeroed-out compute-type section (classic / hyperconv)."""
    return {
        "hosts": 0, "vms": 0,
        "cpu_cap": 0.0, "cpu_used": 0.0, "cpu_pct": 0.0,
        "mem_cap": 0.0, "mem_used": 0.0, "mem_pct": 0.0,
        "stor_cap": 0.0, "stor_used": 0.0,
    }


def _EMPTY_DC(dc_code: str) -> dict:
    """Return a zeroed-out DC details dict for when the DB is unreachable."""
    return {
        "meta": {"name": dc_code, "location": DC_LOCATIONS.get(dc_code, "Unknown Data Center")},
        # New compute-type split sections (used by dc_view)
        "classic": _empty_compute_section(),
        "hyperconv": _empty_compute_section(),
        # Legacy combined Intel section (used by home.py / datacenters.py)
        "intel": {
            "clusters": 0, "hosts": 0, "vms": 0,
            "cpu_cap": 0.0, "cpu_used": 0.0,
            "ram_cap": 0.0, "ram_used": 0.0,
            "storage_cap": 0.0, "storage_used": 0.0,
        },
        "power": {
            "hosts": 0, "vms": 0, "vios": 0, "lpar_count": 0,
            "cpu": 0, "cpu_used": 0.0, "cpu_assigned": 0.0,
            "ram": 0, "memory_total": 0.0, "memory_assigned": 0.0,
        },
        "energy": {"total_kw": 0.0, "ibm_kw": 0.0, "vcenter_kw": 0.0, "total_kwh": 0.0, "ibm_kwh": 0.0, "vcenter_kwh": 0.0},
        "platforms": {
            "nutanix": {"hosts": 0, "vms": 0},
            "vmware": {"clusters": 0, "hosts": 0, "vms": 0},
            "ibm": {"hosts": 0, "vios": 0, "lpars": 0},
        },
    }


class DatabaseService:
    """
    Centralized database service with full optimization stack:

    - ThreadedConnectionPool   : reuses connections; no per-call overhead.
    - TTL Cache (cache_service): module-level 20-min expiry; fixes broken lru_cache.
    - Batch queries            : all DCs fetched in ~10 DB roundtrips instead of ~90.
    - Dynamic DC list          : resolved from loki_locations at startup; fallback to hardcoded.
    - warm_cache()             : pre-loads all data at startup so first user request is instant.
    - refresh_all_data()       : called by scheduler every 15 min to keep cache fresh.
    - Singleton-ready          : designed to be imported from src.services.shared (one instance).
    """

    def __init__(self):
        self._db_host = os.getenv("DB_HOST", "10.134.16.6")
        self._db_port = os.getenv("DB_PORT", "5000")   # Non-standard port — not 5432
        self._db_name = os.getenv("DB_NAME", "bulutlake")
        self._db_user = os.getenv("DB_USER", "datalakeui")
        self._db_pass = os.getenv("DB_PASS")
        self._pool: pg_pool.ThreadedConnectionPool | None = None
        self._dc_list: list[str] = _FALLBACK_DC_LIST.copy()
        self._init_pool()

    # ------------------------------------------------------------------
    # Connection pool
    # ------------------------------------------------------------------

    def _init_pool(self) -> None:
        """Create the connection pool. Logs a warning if DB is unreachable at startup."""
        try:
            self._pool = pg_pool.ThreadedConnectionPool(
                minconn=2,
                maxconn=16,
                host=self._db_host,
                port=self._db_port,
                dbname=self._db_name,
                user=self._db_user,
                password=self._db_pass,
            )
            logger.info("DB connection pool initialized (min=2, max=16).")
        except OperationalError as exc:
            logger.error("Failed to initialize DB pool: %s", exc)
            self._pool = None

    @contextmanager
    def _get_connection(self):
        """Context manager that borrows a connection from the pool and returns it when done."""
        if self._pool is None:
            raise OperationalError("Connection pool is not available.")
        conn = self._pool.getconn()
        try:
            yield conn
        finally:
            self._pool.putconn(conn)

    # ------------------------------------------------------------------
    # Low-level query helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _run_value(cursor, sql: str, params=None) -> float | int:
        """Execute SQL and return first column of first row, or 0."""
        try:
            cursor.execute(sql, params)
            row = cursor.fetchone()
            if row and row[0] is not None:
                return row[0]
        except Exception as exc:
            logger.warning("Query error (value): %s", exc)
            try:
                cursor.execute("ROLLBACK")
            except Exception:
                pass
        return 0

    @staticmethod
    def _run_row(cursor, sql: str, params=None) -> tuple | None:
        """Execute SQL and return the first row tuple, or None."""
        try:
            cursor.execute(sql, params)
            return cursor.fetchone()
        except Exception as exc:
            logger.warning("Query error (row): %s", exc)
            try:
                cursor.execute("ROLLBACK")
            except Exception:
                pass
        return None

    @staticmethod
    def _run_rows(cursor, sql: str, params=None) -> list[tuple]:
        """Execute SQL and return all rows."""
        try:
            cursor.execute(sql, params)
            return cursor.fetchall() or []
        except Exception as exc:
            logger.warning("Query error (rows): %s", exc)
            try:
                cursor.execute("ROLLBACK")
            except Exception:
                pass
        return []

    # ------------------------------------------------------------------
    # Query Explorer: run registered query by key and return structured result
    # ------------------------------------------------------------------

    @staticmethod
    def _prepare_params(params_style: str, user_input: str):
        """
        Convert user input string to (tuple or list) for cursor.execute.
        user_input: single value or comma-separated for array_*.
        """
        if params_style in ("array_wildcard", "array_exact"):
            parts = [p.strip() for p in user_input.split(",") if p.strip()]
            if params_style == "array_wildcard":
                return ([f"%{p}%" for p in parts],)
            return (parts,)
        if params_style == "wildcard":
            return (f"%{user_input.strip()}%",)
        if params_style == "wildcard_pair":
            p = f"%{user_input.strip()}%"
            return (p, p)
        return (user_input.strip(),)

    def execute_registered_query(self, query_key: str, params_input: str) -> dict:
        """
        Execute a query by registry key with given params (string; array params as comma-separated).
        Returns:
          - value: {"result_type": "value", "value": ...}
          - row:   {"result_type": "row", "columns": [...], "data": [...]}
          - rows:  {"result_type": "rows", "columns": [...], "data": [[...], ...]}
          - error: {"error": "message"}
        """
        entry = qo.get_merged_entry(query_key)
        if not entry:
            return {"error": f"Unknown query key: {query_key}"}
        sql = entry.get("sql")
        result_type = entry.get("result_type", "value")
        params_style = entry.get("params_style", "wildcard")
        if not sql:
            return {"error": f"No SQL for query: {query_key}"}
        try:
            params = self._prepare_params(params_style, params_input or "")
        except Exception as exc:
            return {"error": f"Invalid params: {exc}"}
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    desc = cur.description
                    columns = [d[0] for d in desc] if desc else []
                    if result_type == "value":
                        row = cur.fetchone()
                        value = row[0] if row and row[0] is not None else 0
                        return {"result_type": "value", "value": value}
                    if result_type == "row":
                        row = cur.fetchone()
                        return {"result_type": "row", "columns": columns, "data": list(row) if row else []}
                    rows = cur.fetchall()
                    return {"result_type": "rows", "columns": columns, "data": [list(r) for r in rows]}
        except OperationalError as exc:
            logger.warning("execute_registered_query %s: %s", query_key, exc)
            return {"error": f"Database error: {exc}"}
        except Exception as exc:
            logger.warning("execute_registered_query %s: %s", query_key, exc)
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Dynamic DC list from loki_locations
    # ------------------------------------------------------------------

    def _load_dc_list(self) -> list[str]:
        """
        Fetch active datacenter names from loki_locations.
        Falls back to the hardcoded list if the query fails or returns nothing.
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    # Try with status filter first
                    rows = self._run_rows(cur, lq.DC_LIST)
                    dc_names = [row[0] for row in rows if row[0]]
                    if not dc_names:
                        # Retry without status filter
                        rows = self._run_rows(cur, lq.DC_LIST_NO_STATUS)
                        dc_names = [row[0] for row in rows if row[0]]
        except OperationalError as exc:
            logger.warning("Could not load DC list from DB: %s — using fallback.", exc)
            return _FALLBACK_DC_LIST.copy()

        if dc_names:
            logger.info("Loaded %d datacenters from loki_locations: %s", len(dc_names), dc_names)
            return dc_names

        logger.warning("loki_locations returned empty DC list — using fallback.")
        return _FALLBACK_DC_LIST.copy()

    # ------------------------------------------------------------------
    # Individual query methods (single DC) — kept for dc_view.py
    # ------------------------------------------------------------------

    def get_nutanix_host_count(self, cursor, dc_param: str, start_ts, end_ts) -> int:
        return self._run_value(cursor, nq.HOST_COUNT, (dc_param, start_ts, end_ts))

    def get_nutanix_vm_count(self, cursor, dc_param: str, start_ts, end_ts) -> int:
        return self._run_value(cursor, nq.VM_COUNT, (dc_param, start_ts, end_ts))

    def get_nutanix_memory(self, cursor, dc_param: str, start_ts, end_ts) -> tuple | None:
        return self._run_row(cursor, nq.MEMORY, (dc_param, start_ts, end_ts))

    def get_nutanix_storage(self, cursor, dc_param: str, start_ts, end_ts) -> tuple | None:
        return self._run_row(cursor, nq.STORAGE, (dc_param, start_ts, end_ts))

    def get_nutanix_cpu(self, cursor, dc_param: str, start_ts, end_ts) -> tuple | None:
        return self._run_row(cursor, nq.CPU, (dc_param, start_ts, end_ts))

    def get_vmware_counts(self, cursor, dc_param: str, start_ts, end_ts) -> tuple | None:
        return self._run_row(cursor, vq.COUNTS, (dc_param, start_ts, end_ts))

    def get_vmware_memory(self, cursor, dc_param: str, start_ts, end_ts) -> tuple | None:
        return self._run_row(cursor, vq.MEMORY, (dc_param, start_ts, end_ts))

    def get_vmware_storage(self, cursor, dc_param: str, start_ts, end_ts) -> tuple | None:
        return self._run_row(cursor, vq.STORAGE, (dc_param, start_ts, end_ts))

    def get_vmware_cpu(self, cursor, dc_param: str, start_ts, end_ts) -> tuple | None:
        return self._run_row(cursor, vq.CPU, (dc_param, start_ts, end_ts))

    def get_ibm_host_count(self, cursor, dc_param: str, start_ts, end_ts) -> int:
        return self._run_value(cursor, iq.HOST_COUNT, (dc_param, start_ts, end_ts))

    def get_ibm_energy(self, cursor, dc_param: str, start_ts, end_ts) -> float:
        return self._run_value(cursor, eq.IBM, (dc_param, start_ts, end_ts))

    def get_vcenter_energy(self, cursor, dc_param: str, start_ts, end_ts) -> float:
        return self._run_value(cursor, eq.VCENTER, (dc_param, start_ts, end_ts))

    def get_ibm_kwh(self, cursor, dc_param: str, start_ts, end_ts) -> float:
        return self._run_value(cursor, eq.IBM_KWH, (dc_param, start_ts, end_ts))

    def get_vcenter_kwh(self, cursor, dc_param: str, start_ts, end_ts) -> float:
        return self._run_value(cursor, eq.VCENTER_KWH, (dc_param, start_ts, end_ts))

    def get_ibm_vios_count(self, cursor, dc_param: str, start_ts, end_ts) -> int:
        return self._run_value(cursor, iq.VIOS_COUNT, (dc_param, start_ts, end_ts))

    def get_ibm_lpar_count(self, cursor, dc_param: str, start_ts, end_ts) -> int:
        return self._run_value(cursor, iq.LPAR_COUNT, (dc_param, start_ts, end_ts))

    def get_ibm_memory(self, cursor, dc_param: str, start_ts, end_ts) -> tuple | None:
        return self._run_row(cursor, iq.MEMORY, (dc_param, start_ts, end_ts))

    def get_ibm_cpu(self, cursor, dc_param: str, start_ts, end_ts) -> tuple | None:
        return self._run_row(cursor, iq.CPU, (dc_param, start_ts, end_ts))

    # cluster_metrics — Classic / Hyperconverged split
    # dc_wc is the full ILIKE wildcard string e.g. '%DC13%'

    def get_classic_metrics(self, cursor, dc_wc: str, start_ts, end_ts) -> tuple | None:
        """Return Classic (KM) cluster aggregate row: hosts, vms, cpu_cap, cpu_used, mem_cap, mem_used, stor_cap, stor_used."""
        return self._run_row(cursor, vq.CLASSIC_METRICS, (dc_wc, start_ts, end_ts))

    def get_classic_avg30(self, cursor, dc_wc: str, start_ts, end_ts) -> tuple | None:
        """Return Classic cluster average utilization: cpu_avg_pct, mem_avg_pct."""
        return self._run_row(cursor, vq.CLASSIC_AVG30, (dc_wc, start_ts, end_ts))

    def get_hyperconv_metrics(self, cursor, dc_wc: str, start_ts, end_ts) -> tuple | None:
        """Return Hyperconverged (non-KM) cluster aggregate row."""
        return self._run_row(cursor, vq.HYPERCONV_METRICS, (dc_wc, start_ts, end_ts))

    def get_hyperconv_avg30(self, cursor, dc_wc: str, start_ts, end_ts) -> tuple | None:
        """Return Hyperconverged cluster average utilization: cpu_avg_pct, mem_avg_pct."""
        return self._run_row(cursor, vq.HYPERCONV_AVG30, (dc_wc, start_ts, end_ts))

    # ------------------------------------------------------------------
    # Unit normalization & aggregation (shared by single + batch paths)
    # ------------------------------------------------------------------

    @staticmethod
    def _aggregate_dc(
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
        classic_row=None,
        classic_avg30=None,
        hyperconv_row=None,
        hyperconv_avg30=None,
    ) -> dict:
        """Apply unit normalization and build the standard DC detail dictionary.

        classic_row / hyperconv_row — rows from CLASSIC_METRICS / HYPERCONV_METRICS:
            (hosts, vms, cpu_cap_ghz, cpu_used_ghz, mem_cap_gb, mem_used_gb, stor_cap_gb, stor_used_gb)
        classic_avg30 / hyperconv_avg30 — rows from CLASSIC_AVG30 / HYPERCONV_AVG30:
            (cpu_avg_pct, mem_avg_pct)
        """
        nutanix_mem     = nutanix_mem     or (0, 0)
        nutanix_storage = nutanix_storage or (0, 0)
        nutanix_cpu     = nutanix_cpu     or (0, 0)
        vmware_counts   = vmware_counts   or (0, 0, 0)
        vmware_mem      = vmware_mem      or (0, 0)
        vmware_storage  = vmware_storage  or (0, 0)
        vmware_cpu      = vmware_cpu      or (0, 0)
        power_mem       = power_mem       or (0, 0)
        power_cpu       = power_cpu       or (0, 0, 0)
        classic_row     = classic_row     or (0,) * 8
        classic_avg30   = classic_avg30   or (0, 0)
        hyperconv_row   = hyperconv_row   or (0,) * 8
        hyperconv_avg30 = hyperconv_avg30 or (0, 0)

        # Memory → GB (coerce to float for DB Decimal)
        n_mem_cap_gb  = float(nutanix_mem[0] or 0) * 1024
        n_mem_used_gb = float(nutanix_mem[1] or 0) * 1024
        v_mem_cap_gb  = float(vmware_mem[0] or 0)
        v_mem_used_gb = float(vmware_mem[1] or 0)

        # Storage → TB
        n_stor_cap_tb  = float(nutanix_storage[0] or 0)
        n_stor_used_tb = float(nutanix_storage[1] or 0)
        v_stor_cap_tb  = float(vmware_storage[0] or 0) / 1024.0
        v_stor_used_tb = float(vmware_storage[1] or 0) / 1024.0

        # CPU → GHz
        n_cpu_cap_ghz  = float(nutanix_cpu[0] or 0)
        n_cpu_used_ghz = float(nutanix_cpu[1] or 0)
        v_cpu_cap_ghz  = float(vmware_cpu[0] or 0) / 1_000_000_000
        v_cpu_used_ghz = float(vmware_cpu[1] or 0) / 1_000_000_000

        # Energy → kW (IBM + vCenter only; Loki/racks not used)
        total_energy_kw = (float(ibm_w or 0) + float(vcenter_w or 0)) / 1000.0
        # Total energy for billing (kWh in report period)
        total_energy_kwh = float(ibm_kwh or 0) + float(vcenter_kwh or 0)

        # Classic compute section — cluster_metrics rows (KM clusters)
        # Units: CPU in GHz, memory in GB, storage in GB (convert to TB for display key)
        cl_hosts    = int(classic_row[0] or 0)
        cl_vms      = int(classic_row[1] or 0)
        cl_cpu_cap  = round(float(classic_row[2] or 0), 2)
        cl_cpu_used = round(float(classic_row[3] or 0), 2)
        cl_mem_cap  = round(float(classic_row[4] or 0), 2)
        cl_mem_used = round(float(classic_row[5] or 0), 2)
        cl_cpu_pct  = round(float(classic_avg30[0] or 0), 1)
        cl_mem_pct  = round(float(classic_avg30[1] or 0), 1)
        # cluster_metrics.total_capacity_gb is in GB → convert to TB
        cl_stor_cap  = round(float(classic_row[6] or 0) / 1024.0, 3)
        cl_stor_used = round(float(classic_row[7] or 0) / 1024.0, 3)

        # Hyperconverged compute section — cluster_metrics non-KM (CPU/RAM) + Nutanix (storage)
        # Hosts are taken from Nutanix node count so Classic/Hyperconverged host
        # numbers are properly split by cluster type.
        hc_hosts    = int(nutanix_host_count or 0)
        hc_vms      = int(hyperconv_row[1] or 0)
        hc_cpu_cap  = round(float(hyperconv_row[2] or 0), 2)
        hc_cpu_used = round(float(hyperconv_row[3] or 0), 2)
        hc_mem_cap  = round(float(hyperconv_row[4] or 0), 2)
        hc_mem_used = round(float(hyperconv_row[5] or 0), 2)
        hc_cpu_pct  = round(float(hyperconv_avg30[0] or 0), 1)
        hc_mem_pct  = round(float(hyperconv_avg30[1] or 0), 1)
        # Storage from Nutanix (already in TB from the nutanix query)
        hc_stor_cap  = round(n_stor_cap_tb, 3)
        hc_stor_used = round(n_stor_used_tb, 3)

        return {
            "meta": {
                "name": dc_code,
                "location": DC_LOCATIONS.get(dc_code, "Unknown Data Center"),
            },
            # Compute-type split (new) — used by dc_view tabs
            "classic": {
                "hosts": cl_hosts, "vms": cl_vms,
                "cpu_cap": cl_cpu_cap, "cpu_used": cl_cpu_used, "cpu_pct": cl_cpu_pct,
                "mem_cap": cl_mem_cap, "mem_used": cl_mem_used, "mem_pct": cl_mem_pct,
                "stor_cap": cl_stor_cap, "stor_used": cl_stor_used,
            },
            "hyperconv": {
                "hosts": hc_hosts, "vms": hc_vms,
                "cpu_cap": hc_cpu_cap, "cpu_used": hc_cpu_used, "cpu_pct": hc_cpu_pct,
                "mem_cap": hc_mem_cap, "mem_used": hc_mem_used, "mem_pct": hc_mem_pct,
                "stor_cap": hc_stor_cap, "stor_used": hc_stor_used,
            },
            # Legacy combined Intel section — kept for home.py / datacenters.py
            # VM count uses cluster-level dedup: Classic (KM) VMs from VMware cluster_metrics
            # + all Nutanix VMs (covers Nutanix-only and VMware-managed Nutanix VMs once each).
            # vmware_counts[2] (datacenter_metrics.total_vm_count) is intentionally excluded here
            # because it overlaps with nutanix_vms for hyperconverged clusters.
            "intel": {
                "clusters": int(vmware_counts[0] or 0),
                "hosts": int((nutanix_host_count or 0) + (vmware_counts[1] or 0)),
                "vms": cl_vms + int(nutanix_vms or 0),
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
                "cpu_used": round(float(power_cpu[0] or 0), 2),
                "cpu_assigned": round(float(power_cpu[2] or 0), 2),
                "memory_total": round(float(power_mem[0] or 0), 2),
                "memory_assigned": round(float(power_mem[1] or 0), 2),
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
                # vmware.vms shows only Classic (KM) cluster VMs to avoid overlap with Nutanix.
                # Hyperconverged VMs on Nutanix hardware are already represented in nutanix.vms.
                "vmware": {"clusters": int(vmware_counts[0] or 0), "hosts": int(vmware_counts[1] or 0), "vms": cl_vms},
                "ibm": {"hosts": int(power_hosts or 0), "vios": int(power_vios or 0), "lpars": int(power_lpar_count or 0)},
            },
        }

    # ------------------------------------------------------------------
    # Public API — dc_view.py: single DC detail
    # ------------------------------------------------------------------

    def get_dc_details(self, dc_code: str, time_range: dict | None = None) -> dict:
        """Return full metrics dict for a single data center. Result is TTL-cached per time range."""
        tr = time_range or default_time_range()
        start_ts, end_ts = time_range_to_bounds(tr)
        cache_key = f"dc_details:{dc_code}:{tr.get('start','')}:{tr.get('end','')}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    dc_wc = f"%{dc_code}%"
                    result = self._aggregate_dc(
                        dc_code,
                        nutanix_host_count=self.get_nutanix_host_count(cur, dc_code, start_ts, end_ts),
                        nutanix_vms=self.get_nutanix_vm_count(cur, dc_code, start_ts, end_ts),
                        nutanix_mem=self.get_nutanix_memory(cur, dc_code, start_ts, end_ts),
                        nutanix_storage=self.get_nutanix_storage(cur, dc_code, start_ts, end_ts),
                        nutanix_cpu=self.get_nutanix_cpu(cur, dc_code, start_ts, end_ts),
                        vmware_counts=self.get_vmware_counts(cur, dc_code, start_ts, end_ts),
                        vmware_mem=self.get_vmware_memory(cur, dc_code, start_ts, end_ts),
                        vmware_storage=self.get_vmware_storage(cur, dc_code, start_ts, end_ts),
                        vmware_cpu=self.get_vmware_cpu(cur, dc_code, start_ts, end_ts),
                        power_hosts=self.get_ibm_host_count(cur, dc_wc, start_ts, end_ts),
                        power_vios=self.get_ibm_vios_count(cur, dc_wc, start_ts, end_ts),
                        power_lpar_count=self.get_ibm_lpar_count(cur, dc_wc, start_ts, end_ts),
                        power_mem=self.get_ibm_memory(cur, dc_wc, start_ts, end_ts),
                        power_cpu=self.get_ibm_cpu(cur, dc_wc, start_ts, end_ts),
                        ibm_w=self.get_ibm_energy(cur, dc_wc, start_ts, end_ts),
                        vcenter_w=self.get_vcenter_energy(cur, dc_code, start_ts, end_ts),
                        ibm_kwh=self.get_ibm_kwh(cur, dc_wc, start_ts, end_ts),
                        vcenter_kwh=self.get_vcenter_kwh(cur, dc_code, start_ts, end_ts),
                        # Compute-type split (Classic / Hyperconverged)
                        classic_row=self.get_classic_metrics(cur, dc_wc, start_ts, end_ts),
                        classic_avg30=self.get_classic_avg30(cur, dc_wc, start_ts, end_ts),
                        hyperconv_row=self.get_hyperconv_metrics(cur, dc_wc, start_ts, end_ts),
                        hyperconv_avg30=self.get_hyperconv_avg30(cur, dc_wc, start_ts, end_ts),
                    )
        except OperationalError as exc:
            logger.error("DB unavailable for get_dc_details(%s): %s", dc_code, exc)
            return _EMPTY_DC(dc_code)

        cache.set(cache_key, result)
        return result

    # ------------------------------------------------------------------
    # Batch fetch (internal) — used by get_all_datacenters_summary
    # ------------------------------------------------------------------

    def _fetch_all_batch(self, cursor, dc_list: list[str], start_ts, end_ts) -> tuple[dict, dict]:
        """Execute batch queries in **parallel** across separate DB connections.

        Four query groups (Nutanix, VMware, IBM, Energy) each get their own
        connection from the pool and run concurrently.  IBM queries no longer
        use ``regexp_matches`` on the server — raw rows are fetched and DC code
        extraction + aggregation happens in Python via ``_DC_CODE_RE``.
        """
        logger.info(
            "Batch fetch: starting for %d DCs, range %s -> %s",
            len(dc_list), start_ts, end_ts,
        )
        pattern_list = [f"%{dc}%" for dc in dc_list]
        dc_set_upper = {dc.upper() for dc in dc_list}

        # ---- helper: run a group of queries on its own connection ----------
        def _run_group(queries: list[tuple[str, str, tuple]]) -> dict[str, list]:
            """queries: [(label, sql, params), ...] → {label: rows}"""
            out = {}
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    for label, sql, params in queries:
                        out[label] = self._run_rows(cur, sql, params)
            return out

        nutanix_params = (dc_list, pattern_list, start_ts, end_ts)
        vmware_params  = (dc_list, pattern_list, start_ts, end_ts)
        ibm_ts_params  = (start_ts, end_ts)

        nutanix_queries = [
            ("n_host",     nq.BATCH_HOST_COUNT,    nutanix_params),
            ("n_vm",       nq.BATCH_VM_COUNT,      nutanix_params),
            ("n_mem",      nq.BATCH_MEMORY,        nutanix_params),
            ("n_stor",     nq.BATCH_STORAGE,       (start_ts, end_ts, dc_list, pattern_list)),
            ("n_cpu",      nq.BATCH_CPU,           nutanix_params),
            ("n_platform", nq.BATCH_PLATFORM_COUNT, nutanix_params),
        ]
        vmware_queries = [
            ("v_cnt",      vq.BATCH_COUNTS,           vmware_params),
            ("v_mem",      vq.BATCH_MEMORY,           vmware_params),
            ("v_stor",     vq.BATCH_STORAGE,          vmware_params),
            ("v_cpu",      vq.BATCH_CPU,              vmware_params),
            ("v_platform", vq.BATCH_PLATFORM_COUNT,   vmware_params),
            # Compute-type split queries (Classic KM / Hyperconverged non-KM)
            ("v_classic",       vq.BATCH_CLASSIC_METRICS,  vmware_params),
            ("v_classic_avg",   vq.BATCH_CLASSIC_AVG30,    vmware_params),
            ("v_hyperconv",     vq.BATCH_HYPERCONV_METRICS, vmware_params),
            ("v_hyperconv_avg", vq.BATCH_HYPERCONV_AVG30,   vmware_params),
        ]
        ibm_queries = [
            ("ibm_host_raw",   iq.BATCH_RAW_HOST,   ibm_ts_params),
            ("ibm_vios_raw",   iq.BATCH_RAW_VIOS,   ibm_ts_params),
            ("ibm_lpar_raw",   iq.BATCH_RAW_LPAR,   ibm_ts_params),
            ("ibm_mem_raw",    iq.BATCH_RAW_MEMORY,  ibm_ts_params),
            ("ibm_cpu_raw",    iq.BATCH_RAW_CPU,     ibm_ts_params),
        ]
        energy_queries = [
            ("e_ibm",      eq.BATCH_IBM,          (start_ts, end_ts, dc_list)),
            ("e_vcenter",  eq.BATCH_VCENTER,      (dc_list, pattern_list, start_ts, end_ts)),
            ("e_ibm_kwh",  eq.BATCH_IBM_KWH,      (start_ts, end_ts, dc_list)),
            ("e_vctr_kwh", eq.BATCH_VCENTER_KWH,  (dc_list, pattern_list, start_ts, end_ts)),
        ]

        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="batch") as pool:
            fut_nutanix = pool.submit(_run_group, nutanix_queries)
            fut_vmware  = pool.submit(_run_group, vmware_queries)
            fut_ibm     = pool.submit(_run_group, ibm_queries)
            fut_energy  = pool.submit(_run_group, energy_queries)

            n = fut_nutanix.result()
            v = fut_vmware.result()
            ibm_raw = fut_ibm.result()
            e = fut_energy.result()

        logger.info("Batch fetch: all groups finished in %.2fs (parallel)", time.perf_counter() - t0)

        # ---- IBM: Python-side DC code extraction & aggregation -------------
        def _extract_dc(server_name: str) -> str | None:
            if not server_name:
                return None
            m = _DC_CODE_RE.search(server_name.upper())
            if m and m.group(1) in dc_set_upper:
                return m.group(1)
            return None

        ibm_h: dict[str, int] = {}
        for row in ibm_raw["ibm_host_raw"]:
            dc = _extract_dc(row[0]) if row else None
            if dc:
                ibm_h.setdefault(dc, set()).add(row[0])  # type: ignore[arg-type]
        ibm_h = {dc: len(names) for dc, names in ibm_h.items()}  # type: ignore[assignment]

        ibm_vios: dict[str, int] = {}
        for row in ibm_raw["ibm_vios_raw"]:
            dc = _extract_dc(row[0]) if row and len(row) > 1 else None
            if dc:
                ibm_vios.setdefault(dc, set()).add(row[1])  # type: ignore[arg-type]
        ibm_vios = {dc: len(names) for dc, names in ibm_vios.items()}  # type: ignore[assignment]

        ibm_lpar: dict[str, int] = {}
        for row in ibm_raw["ibm_lpar_raw"]:
            dc = _extract_dc(row[0]) if row and len(row) > 1 else None
            if dc:
                ibm_lpar.setdefault(dc, set()).add(row[1])  # type: ignore[arg-type]
        ibm_lpar = {dc: len(names) for dc, names in ibm_lpar.items()}  # type: ignore[assignment]

        ibm_mem_hosts: dict[str, dict[str, list[tuple[float, float, object]]]] = {}
        for row in ibm_raw["ibm_mem_raw"]:
            if not row or len(row) < 4:
                continue
            server_name = row[0]
            dc = _extract_dc(server_name)
            if not dc:
                continue
            try:
                total_mem = float(row[1] or 0)
                assigned_mem = float(row[2] or 0)
            except (TypeError, ValueError):
                continue
            ts = row[3]
            dc_hosts = ibm_mem_hosts.setdefault(dc, {})
            dc_hosts.setdefault(server_name, []).append((total_mem, assigned_mem, ts))

        ibm_mem: dict[str, tuple] = {}
        for dc, hosts in ibm_mem_hosts.items():
            total_cfg = 0.0
            total_assigned = 0.0
            for server_name, samples in hosts.items():
                if not samples:
                    continue
                latest_total, latest_assigned, _ = max(samples, key=lambda v: v[2])
                total_cfg += latest_total
                total_assigned += latest_assigned
            # HMC bellek metrikleri MB cinsinden geldiği için burada GB'e çeviriyoruz.
            ibm_mem[dc] = (
                total_cfg / 1024.0,
                total_assigned / 1024.0,
            )

        ibm_cpu_acc: dict[str, list] = {}
        for row in ibm_raw["ibm_cpu_raw"]:
            if not row or len(row) < 4:
                continue
            dc = _extract_dc(row[0])
            if dc:
                ibm_cpu_acc.setdefault(dc, []).append(
                    (float(row[1] or 0), float(row[2] or 0), float(row[3] or 0))
                )
        ibm_cpu_map: dict[str, tuple] = {}
        for dc, vals in ibm_cpu_acc.items():
            n_vals = len(vals)
            ibm_cpu_map[dc] = (
                sum(v[0] for v in vals) / n_vals,
                sum(v[1] for v in vals) / n_vals,
                sum(v[2] for v in vals) / n_vals,
            )

        # ---- Map batch rows back to DC codes ----
        def _canonical_dc(raw_key) -> str | None:
            if raw_key is None or not str(raw_key).strip():
                return None
            s = str(raw_key).strip()
            for dc in dc_list:
                if dc == s:
                    return dc
            for dc in dc_list:
                if dc.strip().upper() == s.upper():
                    return dc
            for dc in dc_list:
                loc = DC_LOCATIONS.get(dc)
                if loc and str(loc).strip().upper() == s.upper():
                    return dc
            return None

        def _index_exact(rows, col_idx: int = 0) -> dict[str, tuple]:
            out: dict[str, tuple] = {}
            for row in rows:
                if not row or len(row) <= col_idx or row[col_idx] is None:
                    continue
                dc = _canonical_dc(row[col_idx])
                if dc is not None and dc not in out:
                    out[dc] = row
            return out

        n_host_rows, n_vm_rows = n["n_host"], n["n_vm"]
        n_mem_rows, n_stor_rows, n_cpu_rows = n["n_mem"], n["n_stor"], n["n_cpu"]
        n_platform_rows = n["n_platform"]

        v_cnt_rows, v_mem_rows = v["v_cnt"], v["v_mem"]
        v_stor_rows, v_cpu_rows = v["v_stor"], v["v_cpu"]
        v_platform_rows = v["v_platform"]
        v_classic_rows      = v.get("v_classic", [])
        v_classic_avg_rows  = v.get("v_classic_avg", [])
        v_hyperconv_rows    = v.get("v_hyperconv", [])
        v_hyperconv_avg_rows = v.get("v_hyperconv_avg", [])

        n_host  = _index_exact(n_host_rows)
        n_vms   = _index_exact(n_vm_rows)
        n_mem   = _index_exact(n_mem_rows)
        n_stor  = _index_exact(n_stor_rows)
        n_cpu   = _index_exact(n_cpu_rows)

        v_cnt   = _index_exact(v_cnt_rows)
        v_mem_m = _index_exact(v_mem_rows)
        v_stor  = _index_exact(v_stor_rows)
        v_cpu   = _index_exact(v_cpu_rows)
        v_classic      = _index_exact(v_classic_rows)
        v_classic_avg  = _index_exact(v_classic_avg_rows)
        v_hyperconv    = _index_exact(v_hyperconv_rows)
        v_hyperconv_avg = _index_exact(v_hyperconv_avg_rows)

        ibm_e_rows = e["e_ibm"]
        vcenter_rows = e["e_vcenter"]
        ibm_kwh_rows = e["e_ibm_kwh"]
        vcenter_kwh_rows = e["e_vctr_kwh"]

        ibm_e   = {row[0]: float(row[1] or 0) for row in ibm_e_rows if row and len(row) >= 2 and row[0]}
        vctr_e  = {row[0]: float(row[1] or 0) for row in vcenter_rows if row and len(row) >= 2 and row[0]}
        ibm_kwh_m   = {row[0]: float(row[1] or 0) for row in ibm_kwh_rows if row and len(row) >= 2 and row[0]}
        vctr_kwh_m  = {row[0]: float(row[1] or 0) for row in vcenter_kwh_rows if row and len(row) >= 2 and row[0]}

        # Platform counts
        n_platform: dict[str, int] = {}
        for row in n_platform_rows:
            if row and row[0] is not None and len(row) > 1:
                dc = _canonical_dc(row[0])
                if dc is not None:
                    n_platform[dc] = int(row[1] or 0)
        v_platform: dict[str, int] = {}
        for row in v_platform_rows:
            if row and row[0] is not None and len(row) > 1:
                dc = _canonical_dc(row[0])
                if dc is not None:
                    v_platform[dc] = int(row[1] or 0)
        ibm_platform = {dc: (1 if (ibm_h.get(dc, 0) or 0) > 0 else 0) for dc in dc_list}
        platform_counts: dict[str, int] = {
            dc: int(n_platform.get(dc, 0) or 0) + int(v_platform.get(dc, 0) or 0) + int(ibm_platform.get(dc, 0) or 0)
            for dc in dc_list
        }

        # ---- Build per-DC aggregate dicts ----
        results: dict[str, dict] = {}
        for dc in dc_list:
            nh_row   = n_host.get(dc)
            nv_row   = n_vms.get(dc)
            nm_row   = n_mem.get(dc)
            ns_row   = n_stor.get(dc)
            nc_row   = n_cpu.get(dc)
            vc_row   = v_cnt.get(dc)
            vm_row   = v_mem_m.get(dc)
            vs_row   = v_stor.get(dc)
            vcpu_row = v_cpu.get(dc)
            power_mem_tup = ibm_mem.get(dc, (0.0, 0.0))
            power_cpu_tup = ibm_cpu_map.get(dc, (0.0, 0.0, 0.0))

            # Classic / Hyperconverged rows from cluster_metrics
            vcl_row  = v_classic.get(dc)
            vcla_row = v_classic_avg.get(dc)
            vhc_row  = v_hyperconv.get(dc)
            vhca_row = v_hyperconv_avg.get(dc)

            # Batch CLASSIC_METRICS: (dc_code, hosts, vms, cpu_cap, cpu_used, mem_cap, mem_used, stor_cap, stor_used)
            cl_data = (vcl_row[1], vcl_row[2], vcl_row[3], vcl_row[4], vcl_row[5], vcl_row[6], vcl_row[7], vcl_row[8]) if (vcl_row and len(vcl_row) > 8) else None
            # Batch CLASSIC_AVG30: (dc_code, cpu_avg_pct, mem_avg_pct)
            cl_avg  = (vcla_row[1], vcla_row[2]) if (vcla_row and len(vcla_row) > 2) else None
            hc_data = (vhc_row[1], vhc_row[2], vhc_row[3], vhc_row[4], vhc_row[5], vhc_row[6], vhc_row[7], vhc_row[8]) if (vhc_row and len(vhc_row) > 8) else None
            hc_avg  = (vhca_row[1], vhca_row[2]) if (vhca_row and len(vhca_row) > 2) else None

            results[dc] = self._aggregate_dc(
                dc_code=dc,
                nutanix_host_count=nh_row[1] if (nh_row and len(nh_row) > 1) else 0,
                nutanix_vms=nv_row[1] if (nv_row and len(nv_row) > 1) else 0,
                nutanix_mem=(nm_row[1], nm_row[2]) if (nm_row and len(nm_row) > 2) else None,
                nutanix_storage=(ns_row[1], ns_row[2]) if (ns_row and len(ns_row) > 2) else None,
                nutanix_cpu=(nc_row[1], nc_row[2]) if (nc_row and len(nc_row) > 2) else None,
                vmware_counts=(vc_row[1], vc_row[2], vc_row[3]) if (vc_row and len(vc_row) > 3) else None,
                vmware_mem=(vm_row[1], vm_row[2]) if (vm_row and len(vm_row) > 2) else None,
                vmware_storage=(vs_row[1], vs_row[2]) if (vs_row and len(vs_row) > 2) else None,
                vmware_cpu=(vcpu_row[1], vcpu_row[2]) if (vcpu_row and len(vcpu_row) > 2) else None,
                power_hosts=ibm_h.get(dc, 0),
                power_vios=ibm_vios.get(dc, 0),
                power_lpar_count=ibm_lpar.get(dc, 0),
                power_mem=power_mem_tup,
                power_cpu=power_cpu_tup,
                ibm_w=ibm_e.get(dc, 0.0),
                vcenter_w=vctr_e.get(dc, 0.0),
                ibm_kwh=ibm_kwh_m.get(dc, 0.0),
                vcenter_kwh=vctr_kwh_m.get(dc, 0.0),
                classic_row=cl_data,
                classic_avg30=cl_avg,
                hyperconv_row=hc_data,
                hyperconv_avg30=hc_avg,
            )

        return results, platform_counts

    # ------------------------------------------------------------------
    # Public API — datacenters.py: summary list
    # ------------------------------------------------------------------

    def get_all_datacenters_summary(self, time_range: dict | None = None) -> list[dict]:
        """
        Returns summary list for all active DCs (dynamic list from loki_locations).
        time_range: {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"} or None for default (last 7 days).
        Result is TTL-cached per time range.
        """
        tr = time_range or default_time_range()
        cache_key = f"all_dc_summary:{tr.get('start','')}:{tr.get('end','')}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        return self._rebuild_summary(tr)

    def _rebuild_summary(self, time_range: dict | None = None) -> list[dict]:
        """Fetch fresh data and rebuild the summary list. Also populates per-DC cache for the given time range."""
        tr = time_range or default_time_range()
        start_ts, end_ts = time_range_to_bounds(tr)
        self._dc_list = self._load_dc_list()
        dc_list = self._dc_list
        logger.info("Rebuilding summary for %d DCs (batch fetch + aggregate)...", len(dc_list))

        t_total_start = time.perf_counter()
        try:
            all_dc_data, platform_counts = self._fetch_all_batch(None, dc_list, start_ts, end_ts)
            logger.info(
                "Summary rebuild: batch queries finished in %.2fs.",
                time.perf_counter() - t_total_start,
            )
        except OperationalError as exc:
            logger.error("DB unavailable for get_all_datacenters_summary: %s", exc)
            all_dc_data = {dc: _EMPTY_DC(dc) for dc in dc_list}
            platform_counts = {dc: 0 for dc in dc_list}

        summary_list = []
        for dc in dc_list:
            d = all_dc_data.get(dc, _EMPTY_DC(dc))
            intel = d["intel"]
            power = d["power"]
            classic = d.get("classic", {})
            hyperconv = d.get("hyperconv", {})

            # Compute combined host and VM counts using the same logic as dc_view:
            # - Hosts: Classic (KM) + Hyperconverged (Nutanix) + IBM/Power
            # - VMs  : Intel (deduplicated Classic + Nutanix) + IBM LPARs
            host_count = (
                (classic.get("hosts", 0) or 0)
                + (hyperconv.get("hosts", 0) or 0)
                + (power.get("hosts", 0) or 0)
            )
            vm_count = (intel.get("vms", 0) or 0) + (power.get("lpar_count", 0) or 0)

            # Skip datacenters that have no Intel/IBM resources at all
            if host_count == 0 and vm_count == 0:
                # Per-DC cache is still populated below so dc_view can render details if needed.
                cache.set(f"dc_details:{dc}:{tr.get('start','')}:{tr.get('end','')}", d)
                continue

            cpu_cap   = intel["cpu_cap"]       or 0
            cpu_used  = intel["cpu_used"]      or 0
            ram_cap   = intel["ram_cap"]       or 0
            ram_used  = intel["ram_used"]      or 0
            stor_cap  = intel["storage_cap"]   or 0
            stor_used = intel["storage_used"]  or 0

            # Platform count = Nutanix clusters + VMware hypervisors + IBM hosts in this DC
            platform_count = platform_counts.get(dc, 0)

            # Storage values are in TB here; convert to GB for formatting helpers.
            stor_cap_gb = stor_cap * 1024
            stor_used_gb = stor_used * 1024

            summary_list.append({
                "id": dc,
                "name": dc,
                "location": d["meta"]["location"],
                "status": "Healthy",
                "platform_count": platform_count,
                "cluster_count": intel["clusters"],
                "host_count": host_count,
                "vm_count": vm_count,
                "stats": {
                    "total_cpu": f"{smart_cpu(cpu_used)} / {smart_cpu(cpu_cap)}",
                    "used_cpu_pct": round((cpu_used / cpu_cap * 100) if cpu_cap > 0 else 0, 1),
                    "total_ram": f"{smart_memory(ram_used)} / {smart_memory(ram_cap)}",
                    "used_ram_pct": round((ram_used / ram_cap * 100) if ram_cap > 0 else 0, 1),
                    "total_storage": f"{smart_storage(stor_used_gb)} / {smart_storage(stor_cap_gb)}",
                    "used_storage_pct": round((stor_used / stor_cap * 100) if stor_cap > 0 else 0, 1),
                    "last_updated": "Live",
                    "total_energy_kw": d["energy"]["total_kw"],
                    "ibm_kw":          d["energy"].get("ibm_kw", 0.0),
                    "vcenter_kw":      d["energy"].get("vcenter_kw", 0.0),
                },
            })

            # Also populate per-DC cache so dc_view benefits from the batch fetch
            cache.set(f"dc_details:{dc}:{tr.get('start','')}:{tr.get('end','')}", d)

        # Build global dashboard (platform breakdown + overview) from same data
        nutanix_h = nutanix_v = vmware_c = vmware_h = vmware_v = ibm_h = ibm_v = ibm_l = 0
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
        overview = {
            "dc_count": len(summary_list),
            "total_hosts": sum(s["host_count"] for s in summary_list),
            "total_vms": sum(s["vm_count"] for s in summary_list),
            "total_platforms": sum(s["platform_count"] for s in summary_list),
            "total_energy_kw": round(sum(s["stats"]["total_energy_kw"] for s in summary_list), 2),
        }
        cpu_cap = cpu_used = ram_cap = ram_used = stor_cap = stor_used = 0.0
        for d in all_dc_data.values():
            i = d.get("intel", {})
            cpu_cap += float(i.get("cpu_cap", 0) or 0)
            cpu_used += float(i.get("cpu_used", 0) or 0)
            ram_cap += float(i.get("ram_cap", 0) or 0)
            ram_used += float(i.get("ram_used", 0) or 0)
            stor_cap += float(i.get("storage_cap", 0) or 0)
            stor_used += float(i.get("storage_used", 0) or 0)
        overview["total_cpu_cap"] = round(cpu_cap, 2)
        overview["total_cpu_used"] = round(cpu_used, 2)
        overview["total_ram_cap"] = round(ram_cap, 2)
        overview["total_ram_used"] = round(ram_used, 2)
        overview["total_storage_cap"] = round(stor_cap, 2)
        overview["total_storage_used"] = round(stor_used, 2)
        ei = ev = 0.0
        for d in all_dc_data.values():
            e = d.get("energy", {})
            ei += float(e.get("ibm_kw", 0) or 0)
            ev += float(e.get("vcenter_kw", 0) or 0)
        range_suffix = f"{tr.get('start','')}:{tr.get('end','')}"
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
        logger.info(
            "Rebuilt summary for %d DCs in %.2fs.",
            len(summary_list),
            time.perf_counter() - t_total_start,
        )
        return summary_list

    # ------------------------------------------------------------------
    # Public API — home.py: global totals
    # ------------------------------------------------------------------

    def get_global_overview(self, time_range: dict | None = None) -> dict:
        """Return global totals for the given time range. Derived from get_all_datacenters_summary (cached)."""
        tr = time_range or default_time_range()
        cache_key = f"global_overview:{tr.get('start','')}:{tr.get('end','')}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        summaries = self.get_all_datacenters_summary(tr)
        result = {
            "total_hosts": sum(s["host_count"] for s in summaries),
            "total_vms": sum(s["vm_count"] for s in summaries),
            "total_platforms": sum(s["platform_count"] for s in summaries),
            "total_energy_kw": round(sum(s["stats"]["total_energy_kw"] for s in summaries), 2),
            "dc_count": len(summaries),
        }
        cache.set(cache_key, result)
        return result

    def get_global_dashboard(self, time_range: dict | None = None) -> dict:
        """Return global overview + platform breakdown for the given time range."""
        tr = time_range or default_time_range()
        range_suffix = f"{tr.get('start','')}:{tr.get('end','')}"
        cached = cache.get(f"global_dashboard:{range_suffix}")
        if cached is not None:
            return cached
        self.get_all_datacenters_summary(tr)
        return cache.get(f"global_dashboard:{range_suffix}") or {
            "overview": self.get_global_overview(tr),
            "platforms": {"nutanix": {"hosts": 0, "vms": 0}, "vmware": {"clusters": 0, "hosts": 0, "vms": 0}, "ibm": {"hosts": 0, "vios": 0, "lpars": 0}},
            "energy_breakdown": {"ibm_kw": 0, "vcenter_kw": 0},
        }

    def get_customer_resources(self, customer_name: str, time_range: dict | None = None) -> dict:
        """
        Return customer assets for a given customer name and time range.

        Mirrors the Grafana `_DL - Datalake - Customer Assets` dashboard:
        - Intel virtualization (VMware + Nutanix) CPU/VM/memory/disk and VM list
        - Power/HANA (IBM LPAR) CPU/LPAR/memory and VM list
        - Backup (Veeam/Zerto/storage) summary metrics
        """
        tr = time_range or default_time_range()
        cache_key = f"customer_assets:{customer_name}:{tr.get('start','')}:{tr.get('end','')}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        name = (customer_name or "").strip()
        # Patterns aligned with Grafana:
        # - Intel (VMs): prefix + '-' (e.g. 'Boyner-%')
        # - Power/backup: simple prefix (e.g. 'Boyner%')
        # - Storage/NetBackup: contains customer anywhere (e.g. '%Boyner%')
        vm_pattern = f"{name}-%" if name else "%"
        lpar_pattern = f"{name}%" if name else "%"
        veeam_pattern = f"{name}%" if name else "%"
        storage_like_pattern = f"%{name}%" if name else "%"
        netbackup_workload_pattern = f"%{name}%" if name else "%"
        # Zerto uses name LIKE '$customer' || '%-%'
        zerto_name_like = f"{name}%-%" if name else "%"

        start_ts, end_ts = time_range_to_bounds(tr)

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    # Intel VM counts
                    intel_vm_counts = self._run_row(
                        cur,
                        cq.CUSTOMER_INTEL_VM_COUNTS,
                        (vm_pattern, start_ts, end_ts, vm_pattern, start_ts, end_ts),
                    )
                    vmware_vms = int(intel_vm_counts[0] or 0) if intel_vm_counts else 0
                    nutanix_vms = int(intel_vm_counts[1] or 0) if intel_vm_counts else 0
                    intel_vms_total = int(intel_vm_counts[2] or 0) if intel_vm_counts else 0

                    # Intel CPU / memory / disk totals
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

                    # Intel VM list with source and resource details
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
                    classic_cpu    = float(classic_res[0] or 0.0) if classic_res else 0.0
                    classic_mem_gb = float(classic_res[1] or 0.0) if classic_res else 0.0
                    classic_disk_gb = float(classic_res[2] or 0.0) if classic_res else 0.0

                    classic_vm_rows = self._run_rows(
                        cur, cq.CUSTOMER_CLASSIC_VM_LIST, (vm_pattern, start_ts, end_ts)
                    )
                    classic_vm_list = [
                        {
                            "name": r[0], "source": r[1], "cluster": r[2],
                            "cpu": float(r[3] or 0.0),
                            "memory_gb": float(r[4] or 0.0),
                            "disk_gb": float(r[5] or 0.0),
                        }
                        for r in (classic_vm_rows or []) if r and r[0]
                    ]

                    # --- Hyperconverged Compute (non-KM VMware + Nutanix) ---
                    hc_count_row = self._run_row(
                        cur, cq.CUSTOMER_HYPERCONV_VM_COUNT,
                        (vm_pattern, start_ts, end_ts, vm_pattern, start_ts, end_ts),
                    )
                    hc_vmware_only = int(hc_count_row[0] or 0) if hc_count_row else 0
                    hc_nutanix     = int(hc_count_row[1] or 0) if hc_count_row else 0
                    hc_total       = int(hc_count_row[2] or 0) if hc_count_row else 0

                    hc_res = self._run_row(
                        cur, cq.CUSTOMER_HYPERCONV_RESOURCE_TOTALS,
                        (vm_pattern, start_ts, end_ts, vm_pattern, start_ts, end_ts),
                    )
                    hc_cpu     = float(hc_res[0] or 0.0) if hc_res else 0.0
                    hc_mem_gb  = float(hc_res[1] or 0.0) if hc_res else 0.0
                    hc_disk_gb = float(hc_res[2] or 0.0) if hc_res else 0.0

                    hc_vm_rows = self._run_rows(
                        cur, cq.CUSTOMER_HYPERCONV_VM_LIST,
                        (vm_pattern, start_ts, end_ts, vm_pattern, start_ts, end_ts),
                    )
                    hc_vm_list = [
                        {
                            "name": r[0], "source": r[1], "cluster": r[2],
                            "cpu": float(r[3] or 0.0),
                            "memory_gb": float(r[4] or 0.0),
                            "disk_gb": float(r[5] or 0.0),
                        }
                        for r in (hc_vm_rows or []) if r and r[0]
                    ]

                    # Power / HANA (IBM LPAR)
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

                    # Backup – Veeam
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

                    # Backup – NetBackup (size and dedup summary)
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

                    # Backup – Zerto protected VMs
                    zerto_protected_vms = int(
                        self._run_value(
                            cur,
                            cq.CUSTOMER_ZERTO_PROTECTED_VMS,
                            (start_ts, end_ts, zerto_name_like),
                        )
                        or 0
                    )

                    # Backup – Zerto provisioned storage per VPG (last 30 days)
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

                    # Backup – IBM storage volume capacity (optional)
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
                    except Exception as exc:  # missing table or other non-fatal issues
                        logger.warning("CUSTOMER_STORAGE_VOLUME_CAPACITY failed: %s", exc)

        except (OperationalError, PoolError) as exc:
            logger.warning("get_customer_resources failed: %s", exc)
            _empty_compute = {"vm_count": 0, "cpu_total": 0.0, "memory_gb": 0.0, "disk_gb": 0.0, "vm_list": []}
            return {
                "totals": {
                    "vms_total": 0,
                    "intel_vms_total": 0,
                    "classic_vms_total": 0,
                    "hyperconv_vms_total": 0,
                    "power_lpar_total": 0,
                    "cpu_total": 0.0,
                    "intel_cpu_total": 0.0,
                    "classic_cpu_total": 0.0,
                    "hyperconv_cpu_total": 0.0,
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
                    "hyperconv": {**_empty_compute, "vmware_only": 0, "nutanix_count": 0},
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

        # Build final assets structure when DB call succeeds
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
            # Compute-type split (new billing sections)
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
                "cpu_total": hc_cpu,
                "memory_gb": hc_mem_gb,
                "disk_gb": hc_disk_gb,
                "vm_list": hc_vm_list,
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
            "power_lpar_total": power_lpars,
            "cpu_total": intel_cpu_total + power_cpu,
            "intel_cpu_total": intel_cpu_total,
            "classic_cpu_total": classic_cpu,
            "hyperconv_cpu_total": hc_cpu,
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

        result = {"totals": totals, "assets": assets}
        cache.set(cache_key, result)
        return result

    # ------------------------------------------------------------------
    # S3 (IBM iCOS) helpers — DC pools & customer vaults
    # ------------------------------------------------------------------

    def _fetch_dc_s3_pools(self, dc_code: str, start_ts, end_ts) -> dict:
        """
        Fetch raw S3 pool metrics for a single DC directly from the database.

        Returns a dict with:
            {
              "pools": [pool_name, ...],
              "latest": {pool_name: {...}},
              "growth": {pool_name: {...}},
              "trend": [{"bucket": ts, "pool": name, "usable_bytes": x, "used_bytes": y}, ...],
            }
        """
        pattern = f"%{dc_code}%" if dc_code else "%"

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                pool_rows = self._run_rows(
                    cur,
                    s3q.POOL_LIST,
                    (pattern, start_ts, end_ts),
                )
                pools = [r[0] for r in (pool_rows or []) if r and r[0]]
                if not pools:
                    return {"pools": [], "latest": {}, "growth": {}}

                # Latest snapshot per pool
                latest_rows = self._run_rows(
                    cur,
                    s3q.POOL_LATEST,
                    (pools, start_ts, end_ts),
                )
                latest: dict[str, dict] = {}
                for r in latest_rows or []:
                    name, usable, used, ts = r
                    if not name:
                        continue
                    latest[name] = {
                        "usable_bytes": int(usable or 0),
                        "used_bytes": int(used or 0),
                        "timestamp": ts,
                    }

                # First/last snapshot for growth
                growth_rows = self._run_rows(
                    cur,
                    s3q.POOL_FIRST_LAST,
                    (pools, start_ts, end_ts),
                )
                growth: dict[str, dict] = {}
                for r in growth_rows or []:
                    name, first_used, last_used, first_ts, last_ts = r
                    if not name:
                        continue
                    first_used_val = int(first_used or 0)
                    last_used_val = int(last_used or 0)
                    growth[name] = {
                        "first_used_bytes": first_used_val,
                        "last_used_bytes": last_used_val,
                        "delta_used_bytes": last_used_val - first_used_val,
                        "first_timestamp": first_ts,
                        "last_timestamp": last_ts,
                    }

        return {
            "pools": pools,
            "latest": latest,
            "growth": growth,
        }

    def get_dc_s3_pools(self, dc_code: str, time_range: dict | None = None) -> dict:
        """Return cached S3 pool metrics for a DC and time range."""
        tr = time_range or default_time_range()
        start_ts, end_ts = time_range_to_bounds(tr)
        cache_key = f"dc_s3_pools:{dc_code}:{tr.get('start','')}:{tr.get('end','')}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        try:
            result = self._fetch_dc_s3_pools(dc_code, start_ts, end_ts)
        except (OperationalError, PoolError) as exc:
            logger.warning("get_dc_s3_pools failed for %s: %s", dc_code, exc)
            return {"pools": [], "latest": {}, "growth": {}}

        cache.set(cache_key, result)
        return result

    def _fetch_customer_s3_vaults(self, customer_name: str, start_ts, end_ts) -> dict:
        """
        Fetch raw S3 vault metrics for a customer directly from the database.

        Returns a dict with:
            {
              "vaults": [vault_name, ...],
              "latest": {vault_name: {...}},
              "growth": {vault_name: {...}},
            }
        """
        name = (customer_name or "").strip()
        pattern = f"%{name}%" if name else "%"

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                vault_rows = self._run_rows(
                    cur,
                    s3q.VAULT_LIST,
                    (pattern, start_ts, end_ts),
                )
                vaults = [r[0] for r in (vault_rows or []) if r and r[0]]
                if not vaults:
                    return {"vaults": [], "latest": {}, "growth": {}}

                latest_rows = self._run_rows(
                    cur,
                    s3q.VAULT_LATEST,
                    (vaults, start_ts, end_ts),
                )
                latest: dict[str, dict] = {}
                for r in latest_rows or []:
                    vault_id, name_val, hard_quota, used, ts = r
                    if not name_val:
                        continue
                    latest[name_val] = {
                        "vault_id": int(vault_id or 0),
                        "hard_quota_bytes": int(hard_quota or 0),
                        "used_bytes": int(used or 0),
                        "timestamp": ts,
                    }

                growth_rows = self._run_rows(
                    cur,
                    s3q.VAULT_FIRST_LAST,
                    (vaults, start_ts, end_ts),
                )
                growth: dict[str, dict] = {}
                for r in growth_rows or []:
                    vault_id, name_val, first_used, last_used, first_ts, last_ts, hard_quota = r
                    if not name_val:
                        continue
                    first_used_val = int(first_used or 0)
                    last_used_val = int(last_used or 0)
                    growth[name_val] = {
                        "vault_id": int(vault_id or 0),
                        "first_used_bytes": first_used_val,
                        "last_used_bytes": last_used_val,
                        "delta_used_bytes": last_used_val - first_used_val,
                        "first_timestamp": first_ts,
                        "last_timestamp": last_ts,
                        "hard_quota_bytes": int(hard_quota or 0),
                    }

        return {
            "vaults": vaults,
            "latest": latest,
            "growth": growth,
        }

    def get_customer_s3_vaults(self, customer_name: str, time_range: dict | None = None) -> dict:
        """Return cached S3 vault metrics for a customer and time range."""
        tr = time_range or default_time_range()
        start_ts, end_ts = time_range_to_bounds(tr)
        cache_key = f"customer_s3:{customer_name}:{tr.get('start','')}:{tr.get('end','')}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        try:
            result = self._fetch_customer_s3_vaults(customer_name, start_ts, end_ts)
        except (OperationalError, PoolError) as exc:
            logger.warning("get_customer_s3_vaults failed for %s: %s", customer_name, exc)
            return {"vaults": [], "latest": {}, "growth": {}, "trend": []}

        cache.set(cache_key, result)
        return result

    def get_customer_list(self) -> list[str]:
        """Return list of customer names for selector (fixed to Boyner)."""
        return ["Boyner"]

    # ------------------------------------------------------------------
    # Cache warming / background refresh API
    # ------------------------------------------------------------------

    def warm_cache(self) -> None:
        """
        Pre-load last 7 days into cache at app startup.
        Called once immediately so the first user request is served from cache.
        Longer ranges (30 days, previous calendar month) are warmed in background
        by the scheduler after the app has started.
        """
        logger.info("Warming cache at startup (last 7d only)…")
        t0 = time.perf_counter()
        try:
            tr = default_time_range()
            # Datacenter-level caches
            self._rebuild_summary(tr)
            self.get_global_overview(tr)
            # Customer-level cache for Boyner so the Customer tab is instant after startup.
            try:
                self.get_customer_resources("Boyner", tr)
            except Exception as exc:
                logger.warning("Customer cache warm-up for Boyner failed: %s", exc)

            logger.info(
                "Cache warm-up complete for last 7d in %.2fs.",
                time.perf_counter() - t0,
            )
        except Exception as exc:
            logger.warning("Cache warm-up failed (DB may be unavailable): %s", exc)

    def warm_additional_ranges(self) -> None:
        """
        Warm additional fixed ranges (last 30 days, previous calendar month).
        Intended to run in background after app startup so it does not block
        the initial application launch.
        """
        logger.info("Warming additional cache ranges (30d, previous month)…")
        try:
            ranges = cache_time_ranges()[1:]  # skip 7d, warm 30d + previous month
            for tr in ranges:
                self._rebuild_summary(tr)
                self.get_global_overview(tr)
            logger.info("Additional cache warm-up complete.")
        except Exception as exc:
            logger.warning("Additional cache warm-up failed: %s", exc)

    def warm_s3_cache(self) -> None:
        """
        Warm S3 (pool/vault) cache for the default reporting range.

        This is triggered once in the background after startup so that S3 panels
        open quickly when first visited.
        """
        logger.info("Warming S3 cache for default time range…")
        try:
            tr = default_time_range()
            start_ts, end_ts = time_range_to_bounds(tr)
            for dc_code in self.dc_list:
                try:
                    key = f"dc_s3_pools:{dc_code}:{tr.get('start','')}:{tr.get('end','')}"
                    data = self._fetch_dc_s3_pools(dc_code, start_ts, end_ts)
                    cache.set(key, data)
                except Exception as exc:
                    logger.warning("warm_s3_cache failed for DC %s: %s", dc_code, exc)

            try:
                key_c = f"customer_s3:Boyner:{tr.get('start','')}:{tr.get('end','')}"
                data_c = self._fetch_customer_s3_vaults("Boyner", start_ts, end_ts)
                cache.set(key_c, data_c)
            except Exception as exc:
                logger.warning("warm_s3_cache failed for customer Boyner: %s", exc)

            logger.info("S3 cache warm-up complete for default range.")
        except Exception as exc:
            logger.warning("S3 cache warm-up failed: %s", exc)

    def refresh_all_data(self) -> None:
        """
        Called by the background scheduler every 15 minutes.
        Rebuilds cache for the three fixed ranges (last 7d, last 30d, previous month).
        Does NOT clear cache first: UI keeps showing previous cache until update completes.
        """
        logger.info("Background cache refresh started (last 7d, last 30d, previous month).")
        try:
            for tr in cache_time_ranges():
                self._rebuild_summary(tr)
                self.get_global_overview(tr)
            logger.info("Background cache refresh complete.")
        except Exception as exc:
            logger.error("Background cache refresh failed: %s", exc)

    def refresh_s3_cache(self) -> None:
        """
        Refresh S3 (pool/vault) cache for the standard reporting ranges.

        This is called by the background scheduler every 30 minutes. Cache entries
        are updated in place: existing cached values remain valid until new data
        has been fetched and written, so UI panels never see an empty gap.
        """
        logger.info("Background S3 cache refresh started.")
        try:
            for tr in cache_time_ranges():
                start_ts, end_ts = time_range_to_bounds(tr)
                for dc_code in self.dc_list:
                    try:
                        key = f"dc_s3_pools:{dc_code}:{tr.get('start','')}:{tr.get('end','')}"
                        data = self._fetch_dc_s3_pools(dc_code, start_ts, end_ts)
                        cache.set(key, data)
                    except Exception as exc:
                        logger.warning("refresh_s3_cache failed for DC %s: %s", dc_code, exc)

                # For now, customer S3 is implemented for Boyner only, aligned with customer view.
                try:
                    key_c = f"customer_s3:Boyner:{tr.get('start','')}:{tr.get('end','')}"
                    data_c = self._fetch_customer_s3_vaults("Boyner", start_ts, end_ts)
                    cache.set(key_c, data_c)
                except Exception as exc:
                    logger.warning("refresh_s3_cache failed for customer Boyner: %s", exc)

            logger.info("Background S3 cache refresh complete.")
        except Exception as exc:
            logger.error("Background S3 cache refresh failed: %s", exc)

    @property
    def dc_list(self) -> list[str]:
        """Expose current dynamic DC list (read-only)."""
        return list(self._dc_list)
