import os
import logging
import time
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool as pg_pool
from psycopg2 import OperationalError
from psycopg2.pool import PoolError

from src.queries import nutanix as nq, vmware as vq, ibm as iq, energy as eq
from src.queries import loki as lq, customer as cq, intel_dc as idq
from src.services import cache_service as cache
from src.services import query_overrides as qo
from src.utils.time_range import default_time_range, time_range_to_bounds, cache_time_ranges

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


def _EMPTY_DC(dc_code: str) -> dict:
    """Return a zeroed-out DC details dict for when the DB is unreachable."""
    return {
        "meta": {"name": dc_code, "location": DC_LOCATIONS.get(dc_code, "Unknown Data Center")},
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
    ) -> dict:
        """Apply unit normalization and build the standard DC detail dictionary."""
        nutanix_mem     = nutanix_mem     or (0, 0)
        nutanix_storage = nutanix_storage or (0, 0)
        nutanix_cpu     = nutanix_cpu     or (0, 0)
        vmware_counts   = vmware_counts   or (0, 0, 0)
        vmware_mem      = vmware_mem      or (0, 0)
        vmware_storage  = vmware_storage  or (0, 0)
        vmware_cpu      = vmware_cpu      or (0, 0)
        power_mem       = power_mem       or (0, 0)
        power_cpu       = power_cpu       or (0, 0, 0)

        # Memory → GB (coerce to float for DB Decimal)
        n_mem_cap_gb  = float(nutanix_mem[0] or 0) * 1024
        n_mem_used_gb = float(nutanix_mem[1] or 0) * 1024
        v_mem_cap_gb  = float(vmware_mem[0] or 0) / (1024 ** 3)
        v_mem_used_gb = float(vmware_mem[1] or 0) / (1024 ** 3)

        # Storage → TB
        n_stor_cap_tb  = float(nutanix_storage[0] or 0)
        n_stor_used_tb = float(nutanix_storage[1] or 0)
        v_stor_cap_tb  = float(vmware_storage[0] or 0) / (1024 ** 4)
        v_stor_used_tb = float(vmware_storage[1] or 0) / (1024 ** 4)

        # CPU → GHz
        n_cpu_cap_ghz  = float(nutanix_cpu[0] or 0)
        n_cpu_used_ghz = float(nutanix_cpu[1] or 0)
        v_cpu_cap_ghz  = float(vmware_cpu[0] or 0) / 1_000_000_000
        v_cpu_used_ghz = float(vmware_cpu[1] or 0) / 1_000_000_000

        # Energy → kW (IBM + vCenter only; Loki/racks not used)
        total_energy_kw = (float(ibm_w or 0) + float(vcenter_w or 0)) / 1000.0
        # Total energy for billing (kWh in report period)
        total_energy_kwh = float(ibm_kwh or 0) + float(vcenter_kwh or 0)

        return {
            "meta": {
                "name": dc_code,
                "location": DC_LOCATIONS.get(dc_code, "Unknown Data Center"),
            },
            "intel": {
                "clusters": int(vmware_counts[0] or 0),
                "hosts": int((nutanix_host_count or 0) + (vmware_counts[1] or 0)),
                # VM count is taken from VMware only; Nutanix VM metrics are
                # already included in vmware_counts via the deduplicated view
                # used by the reporting layer, so we avoid double counting here.
                "vms": int(vmware_counts[2] or 0),
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
                "vmware": {"clusters": int(vmware_counts[0] or 0), "hosts": int(vmware_counts[1] or 0), "vms": int(vmware_counts[2] or 0)},
                "ibm": {"hosts": int(power_hosts or 0), "vios": int(power_vios or 0), "lpars": int(power_lpar_count or 0)},
            },
        }

    # ------------------------------------------------------------------
    # Intel DC-level helpers (VMware + Nutanix, Python-side dedup)
    # ------------------------------------------------------------------

    def _get_intel_dc_metrics(self, cursor, dc_code: str, start_ts, end_ts) -> dict:
        """Fetch raw VMware & Nutanix VM lists and compute deduplicated Intel metrics in Python.

        Returns dict with keys: vm_count, vmware_only, nutanix_count, overlap.
        Two lightweight SELECTs replace the former heavy CTE query, keeping the
        DB load minimal while all deduplication happens here.
        """
        vmware_rows = self._run_rows(
            cursor, idq.VMWARE_VMS_FOR_DC, (dc_code, start_ts, end_ts),
        )
        nutanix_rows = self._run_rows(
            cursor, idq.NUTANIX_VMS_FOR_DC, (dc_code, start_ts, end_ts),
        )

        vmware_names = {r[0] for r in vmware_rows if r and r[0]}
        nutanix_names = {r[0] for r in nutanix_rows if r and r[0]}

        all_unique = vmware_names | nutanix_names
        overlap = vmware_names & nutanix_names

        return {
            "vm_count": len(all_unique),
            "vmware_only": len(vmware_names - nutanix_names),
            "nutanix_count": len(nutanix_names),
            "overlap": len(overlap),
        }

    def _get_intel_dc_vm_total(self, cursor, dc_code: str, start_ts, end_ts) -> int:
        """Convenience wrapper: returns deduplicated VM total for a DC."""
        return self._get_intel_dc_metrics(cursor, dc_code, start_ts, end_ts)["vm_count"]

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
                    # Intel: VMware + Nutanix VM-level deduplicated total for this DC
                    intel_vms_total = self._get_intel_dc_vm_total(cur, dc_code, start_ts, end_ts)

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
                    )
                    # Override Intel VM count with deduplicated VMware+Nutanix total
                    try:
                        result["intel"]["vms"] = int(intel_vms_total)
                    except (TypeError, ValueError, KeyError):
                        pass
        except OperationalError as exc:
            logger.error("DB unavailable for get_dc_details(%s): %s", dc_code, exc)
            return _EMPTY_DC(dc_code)

        cache.set(cache_key, result)
        return result

    # ------------------------------------------------------------------
    # Batch fetch (internal) — used by get_all_datacenters_summary
    # ------------------------------------------------------------------

    def _fetch_all_batch(self, cursor, dc_list: list[str], start_ts, end_ts) -> dict[str, dict]:
        """
        Execute all batch queries in one connection and map results back to DC codes.
        start_ts, end_ts: time range for report (all time-series queries filtered).
        Nutanix: match by cluster_name LIKE '%dc%'. VMware/vCenter: match by datacenter ILIKE '%dc%'.
        """
        logger.info(
            "Batch fetch: starting for %d DCs, range %s -> %s",
            len(dc_list),
            start_ts,
            end_ts,
        )
        # Patterns for LIKE/ILIKE: one per DC (e.g. ['%AZ11%', '%DC11%', ...])
        pattern_list = [f"%{dc}%" for dc in dc_list]
        # Nutanix — params (dc_list, pattern_list, start_ts, end_ts); returns (dc_code, ...)
        logger.info("Batch fetch: Nutanix START")
        t0 = time.perf_counter()
        n_host_rows  = self._run_rows(cursor, nq.BATCH_HOST_COUNT, (dc_list, pattern_list, start_ts, end_ts))
        n_vm_rows    = self._run_rows(cursor, nq.BATCH_VM_COUNT, (dc_list, pattern_list, start_ts, end_ts))
        n_mem_rows   = self._run_rows(cursor, nq.BATCH_MEMORY,     (dc_list, pattern_list, start_ts, end_ts))
        n_stor_rows  = self._run_rows(cursor, nq.BATCH_STORAGE,    (dc_list, pattern_list, start_ts, end_ts))
        n_cpu_rows   = self._run_rows(cursor, nq.BATCH_CPU,        (dc_list, pattern_list, start_ts, end_ts))
        n_platform_rows = self._run_rows(cursor, nq.BATCH_PLATFORM_COUNT, (dc_list, pattern_list, start_ts, end_ts))
        logger.info("Batch fetch: Nutanix DONE in %.2fs", time.perf_counter() - t0)

        # VMware — params (dc_list, pattern_list, start_ts, end_ts); returns (dc_code, ...)
        logger.info("Batch fetch: VMware START")
        t0 = time.perf_counter()
        v_cnt_rows   = self._run_rows(cursor, vq.BATCH_COUNTS,  (dc_list, pattern_list, start_ts, end_ts))
        v_mem_rows   = self._run_rows(cursor, vq.BATCH_MEMORY,  (dc_list, pattern_list, start_ts, end_ts))
        v_stor_rows  = self._run_rows(cursor, vq.BATCH_STORAGE, (dc_list, pattern_list, start_ts, end_ts))
        v_cpu_rows   = self._run_rows(cursor, vq.BATCH_CPU,     (dc_list, pattern_list, start_ts, end_ts))
        v_platform_rows = self._run_rows(cursor, vq.BATCH_PLATFORM_COUNT, (dc_list, pattern_list, start_ts, end_ts))
        logger.info("Batch fetch: VMware DONE in %.2fs", time.perf_counter() - t0)

        # IBM — params (start_ts, end_ts, dc_list); returns (dc_code, ...)
        logger.info("Batch fetch: IBM START")
        t0 = time.perf_counter()
        t_q = time.perf_counter()
        ibm_rows = self._run_rows(cursor, iq.BATCH_HOST_COUNT, (start_ts, end_ts, dc_list))
        logger.info(
            "Batch fetch: IBM HOST_COUNT took %.2fs (rows=%d)",
            time.perf_counter() - t_q,
            len(ibm_rows),
        )
        t_q = time.perf_counter()
        logger.info("Batch fetch: IBM VIOS_COUNT START")
        ibm_vios_rows = self._run_rows(cursor, iq.BATCH_VIOS_COUNT, (start_ts, end_ts, dc_list))
        logger.info(
            "Batch fetch: IBM VIOS_COUNT took %.2fs (rows=%d)",
            time.perf_counter() - t_q,
            len(ibm_vios_rows),
        )
        t_q = time.perf_counter()
        logger.info("Batch fetch: IBM LPAR_COUNT START")
        ibm_lpar_rows = self._run_rows(cursor, iq.BATCH_LPAR_COUNT, (start_ts, end_ts, dc_list))
        logger.info(
            "Batch fetch: IBM LPAR_COUNT took %.2fs (rows=%d)",
            time.perf_counter() - t_q,
            len(ibm_lpar_rows),
        )
        t_q = time.perf_counter()
        logger.info("Batch fetch: IBM MEMORY START")
        ibm_mem_rows = self._run_rows(cursor, iq.BATCH_MEMORY, (start_ts, end_ts, dc_list))
        logger.info(
            "Batch fetch: IBM MEMORY took %.2fs (rows=%d)",
            time.perf_counter() - t_q,
            len(ibm_mem_rows),
        )
        t_q = time.perf_counter()
        logger.info("Batch fetch: IBM CPU START")
        ibm_cpu_rows = self._run_rows(cursor, iq.BATCH_CPU, (start_ts, end_ts, dc_list))
        logger.info(
            "Batch fetch: IBM CPU took %.2fs (rows=%d)",
            time.perf_counter() - t_q,
            len(ibm_cpu_rows),
        )
        logger.info("Batch fetch: IBM total time %.2fs", time.perf_counter() - t0)

        # Energy — IBM/vCenter only; vCenter params (dc_list, pattern_list, start_ts, end_ts); IBM (start_ts, end_ts, dc_list)
        logger.info("Batch fetch: Energy START")
        t0 = time.perf_counter()
        t_q = time.perf_counter()
        logger.info("Batch fetch: Energy IBM_METRICS START")
        ibm_e_rows = self._run_rows(cursor, eq.BATCH_IBM, (start_ts, end_ts, dc_list))
        logger.info(
            "Batch fetch: Energy IBM_METRICS took %.2fs (rows=%d)",
            time.perf_counter() - t_q,
            len(ibm_e_rows),
        )
        t_q = time.perf_counter()
        logger.info("Batch fetch: Energy VCENTER_METRICS START")
        vcenter_rows = self._run_rows(cursor, eq.BATCH_VCENTER, (dc_list, pattern_list, start_ts, end_ts))
        logger.info(
            "Batch fetch: Energy VCENTER_METRICS took %.2fs (rows=%d)",
            time.perf_counter() - t_q,
            len(vcenter_rows),
        )
        t_q = time.perf_counter()
        logger.info("Batch fetch: Energy IBM_KWH START")
        ibm_kwh_rows = self._run_rows(cursor, eq.BATCH_IBM_KWH, (start_ts, end_ts, dc_list))
        logger.info(
            "Batch fetch: Energy IBM_KWH took %.2fs (rows=%d)",
            time.perf_counter() - t_q,
            len(ibm_kwh_rows),
        )
        t_q = time.perf_counter()
        logger.info("Batch fetch: Energy VCENTER_KWH START")
        vcenter_kwh_rows = self._run_rows(cursor, eq.BATCH_VCENTER_KWH, (dc_list, pattern_list, start_ts, end_ts))
        logger.info(
            "Batch fetch: Energy VCENTER_KWH took %.2fs (rows=%d)",
            time.perf_counter() - t_q,
            len(vcenter_kwh_rows),
        )
        logger.info("Batch fetch: Energy total time %.2fs", time.perf_counter() - t0)

        # --- Map batch rows back to DC codes ---
        # Nutanix/VMware/IBM may store DC with different case or trailing spaces than loki_locations.
        # We map batch keys to the canonical dc_list entry so per-DC cards get the right data.

        def _canonical_dc(raw_key) -> str | None:
            """Map raw key from DB (e.g. datacenter_name, dc) to the canonical DC code in dc_list.
            Tries: exact match on dc_list, case-insensitive on dc_list, then location name (DC_LOCATIONS
            value) match so Nutanix rows keyed by e.g. 'Azerbaycan' map to DC code 'AZ11'.
            """
            if raw_key is None or not str(raw_key).strip():
                return None
            s = str(raw_key).strip()
            for dc in dc_list:
                if dc == s:
                    return dc
            for dc in dc_list:
                if dc.strip().upper() == s.upper():
                    return dc
            # Nutanix (and similar) may use location name instead of DC code (e.g. Azerbaycan vs AZ11)
            for dc in dc_list:
                loc = DC_LOCATIONS.get(dc)
                if loc and str(loc).strip().upper() == s.upper():
                    return dc
            return None

        def _match_dc(name: str) -> str | None:
            """Find which DC code appears in a string (substring; used for free-text)."""
            if not name:
                return None
            upper = name.upper()
            for dc in dc_list:
                if dc.upper() in upper:
                    return dc
            return None

        def _index_by_dc(rows, col_idx: int = 0) -> dict[str, tuple]:
            """First row per DC: {dc_code: row}."""
            out: dict[str, tuple] = {}
            for row in rows:
                if not row or len(row) <= col_idx:
                    continue
                dc = _match_dc(str(row[col_idx]))
                if dc and dc not in out:
                    out[dc] = row
            return out

        def _index_exact(rows, col_idx: int = 0) -> dict[str, tuple]:
            """Index by first column, but map key to canonical dc from dc_list (strip + case-insensitive).
            Ensures Nutanix/VMware batch rows match dc_list even if DB has different case or spaces.
            """
            out: dict[str, tuple] = {}
            for row in rows:
                if not row or len(row) <= col_idx or row[col_idx] is None:
                    continue
                dc = _canonical_dc(row[col_idx])
                if dc is not None and dc not in out:
                    out[dc] = row
            return out

        def _sum_by_dc(rows, value_col: int, col_idx: int = 0) -> dict[str, float]:
            """Sum numeric column per DC (e.g. energy watts, IBM hosts)."""
            out: dict[str, float] = {}
            for row in rows:
                if not row or len(row) <= max(col_idx, value_col):
                    continue
                dc = _match_dc(str(row[col_idx]))
                if dc:
                    out[dc] = out.get(dc, 0) + float(row[value_col] or 0)
            return out

        # Nutanix batch results use datacenter_name as exact key (col 0)
        n_host  = _index_exact(n_host_rows)
        n_vms   = _index_exact(n_vm_rows)
        n_mem   = _index_exact(n_mem_rows)
        n_stor  = _index_exact(n_stor_rows)
        n_cpu   = _index_exact(n_cpu_rows)

        # VMware batch returns (dc, ...); use exact match
        v_cnt   = _index_exact(v_cnt_rows)
        v_mem   = _index_exact(v_mem_rows)
        v_stor  = _index_exact(v_stor_rows)
        v_cpu   = _index_exact(v_cpu_rows)

        # IBM batch returns (dc_code, ...); use exact match
        ibm_h       = {row[0]: (row[1] if len(row) > 1 else 0) for row in ibm_rows if row and row[0]}
        ibm_vios    = {row[0]: (row[1] if len(row) > 1 else 0) for row in ibm_vios_rows if row and row[0]}
        ibm_lpar    = {row[0]: (row[1] if len(row) > 1 else 0) for row in ibm_lpar_rows if row and row[0]}
        ibm_mem     = {row[0]: (row[1], row[2]) for row in ibm_mem_rows if row and len(row) > 2}
        ibm_cpu_map = {row[0]: (row[1], row[2], row[3]) for row in ibm_cpu_rows if row and len(row) > 3}

        # Energy: batch returns (dc_code, avg_power_watts) or (dc_code, total_kwh)
        ibm_e   = {row[0]: float(row[1] or 0) for row in ibm_e_rows if row and len(row) >= 2 and row[0]}
        vctr_e  = {row[0]: float(row[1] or 0) for row in vcenter_rows if row and len(row) >= 2 and row[0]}
        ibm_kwh_map   = {row[0]: float(row[1] or 0) for row in ibm_kwh_rows if row and len(row) >= 2 and row[0]}
        vctr_kwh_map  = {row[0]: float(row[1] or 0) for row in vcenter_kwh_rows if row and len(row) >= 2 and row[0]}

        # Platform count per DC = Nutanix clusters + VMware hypervisors + IBM (0 or 1 per DC; servername = hosts)
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
        # IBM: at most one platform per DC (hosts are identified by servername)
        ibm_platform = {dc: (1 if (ibm_h.get(dc, 0) or 0) > 0 else 0) for dc in dc_list}
        platform_counts: dict[str, int] = {
            dc: int(n_platform.get(dc, 0) or 0) + int(v_platform.get(dc, 0) or 0) + int(ibm_platform.get(dc, 0) or 0)
            for dc in dc_list
        }

        results: dict[str, dict] = {}
        for dc in dc_list:
            nh_row   = n_host.get(dc)
            nv_row   = n_vms.get(dc)
            nm_row   = n_mem.get(dc)
            ns_row   = n_stor.get(dc)
            nc_row   = n_cpu.get(dc)
            vc_row   = v_cnt.get(dc)
            vm_row   = v_mem.get(dc)
            vs_row   = v_stor.get(dc)
            vcpu_row = v_cpu.get(dc)
            power_mem_tup = ibm_mem.get(dc, (0.0, 0.0))
            power_cpu_tup = ibm_cpu_map.get(dc, (0.0, 0.0, 0.0))

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
                ibm_kwh=ibm_kwh_map.get(dc, 0.0),
                vcenter_kwh=vctr_kwh_map.get(dc, 0.0),
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
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    t_batch_start = time.perf_counter()
                    all_dc_data, platform_counts = self._fetch_all_batch(cur, dc_list, start_ts, end_ts)
                    logger.info(
                        "Summary rebuild: batch queries finished in %.2fs.",
                        time.perf_counter() - t_batch_start,
                    )
                    # Precompute Intel VM totals per DC using VMware+Nutanix deduplicated query
                    t_intel_start = time.perf_counter()
                    intel_vm_totals: dict[str, int] = {}
                    for dc in dc_list:
                        intel_vm_totals[dc] = self._get_intel_dc_vm_total(cur, dc, start_ts, end_ts)
                    logger.info(
                        "Summary rebuild: Intel DC VM totals computed for %d DCs in %.2fs.",
                        len(dc_list),
                        time.perf_counter() - t_intel_start,
                    )
            logger.info("Batch fetch complete, aggregating per-DC...")
        except OperationalError as exc:
            logger.error("DB unavailable for get_all_datacenters_summary: %s", exc)
            all_dc_data = {dc: _EMPTY_DC(dc) for dc in dc_list}
            platform_counts = {dc: 0 for dc in dc_list}
            intel_vm_totals = {dc: 0 for dc in dc_list}

        summary_list = []
        for dc in dc_list:
            d = all_dc_data.get(dc, _EMPTY_DC(dc))
            intel = d["intel"]
            power = d["power"]

            # Override Intel VM count with deduplicated VMware+Nutanix total for this DC
            try:
                intel["vms"] = int(intel_vm_totals.get(dc, intel.get("vms", 0)))
            except (TypeError, ValueError):
                pass

            # Compute combined host and VM counts (Intel + IBM/Power)
            host_count = (intel["hosts"] or 0) + (power["hosts"] or 0)
            vm_count = (intel["vms"] or 0) + (power.get("vms", 0) or 0)

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
                    "total_cpu": f"{cpu_used:,} / {cpu_cap:,} GHz",
                    "used_cpu_pct": round((cpu_used / cpu_cap * 100) if cpu_cap > 0 else 0, 1),
                    "total_ram": f"{ram_used:,} / {ram_cap:,} GB",
                    "used_ram_pct": round((ram_used / ram_cap * 100) if ram_cap > 0 else 0, 1),
                    "total_storage": f"{stor_used:,} / {stor_cap:,} TB",
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
            return {
                "totals": {
                    "vms_total": 0,
                    "intel_vms_total": 0,
                    "power_lpar_total": 0,
                    "cpu_total": 0.0,
                    "intel_cpu_total": 0.0,
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
            "power_lpar_total": power_lpars,
            "cpu_total": intel_cpu_total + power_cpu,
            "intel_cpu_total": intel_cpu_total,
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
            self._rebuild_summary(tr)
            self.get_global_overview(tr)
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

    @property
    def dc_list(self) -> list[str]:
        """Expose current dynamic DC list (read-only)."""
        return list(self._dc_list)
