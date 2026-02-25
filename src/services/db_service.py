import os
import logging
import time
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool as pg_pool
from psycopg2 import OperationalError

from src.queries import nutanix as nq, vmware as vq, ibm as iq, energy as eq
from src.queries import loki as lq, customer as cq
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
    "DC13": "Istanbul",
    "ICT11": "Almanya",
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
        "energy": {"total_kw": 0.0, "ibm_kw": 0.0, "vcenter_kw": 0.0},
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
                maxconn=8,
                host=self._db_host,
                port=self._db_port,
                dbname=self._db_name,
                user=self._db_user,
                password=self._db_pass,
            )
            logger.info("DB connection pool initialized (min=2, max=8).")
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

        return {
            "meta": {
                "name": dc_code,
                "location": DC_LOCATIONS.get(dc_code, "Unknown Data Center"),
            },
            "intel": {
                "clusters": int(vmware_counts[0] or 0),
                "hosts": int((nutanix_host_count or 0) + (vmware_counts[1] or 0)),
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
            },
            "platforms": {
                "nutanix": {"hosts": int(nutanix_host_count or 0), "vms": int(nutanix_vms or 0)},
                "vmware": {"clusters": int(vmware_counts[0] or 0), "hosts": int(vmware_counts[1] or 0), "vms": int(vmware_counts[2] or 0)},
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
                    )
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
        """
        # Nutanix — params (dc_list, start_ts, end_ts)
        t0 = time.perf_counter()
        n_host_rows  = self._run_rows(cursor, nq.BATCH_HOST_COUNT, (dc_list, start_ts, end_ts))
        n_vm_rows    = self._run_rows(cursor, nq.BATCH_VM_COUNT, (dc_list, start_ts, end_ts))
        n_mem_rows   = self._run_rows(cursor, nq.BATCH_MEMORY,     (dc_list, start_ts, end_ts))
        n_stor_rows  = self._run_rows(cursor, nq.BATCH_STORAGE,    (dc_list, start_ts, end_ts))
        n_cpu_rows   = self._run_rows(cursor, nq.BATCH_CPU,        (dc_list, start_ts, end_ts))
        logger.info("Batch fetch: Nutanix done in %.2fs", time.perf_counter() - t0)

        # VMware — params (dc_list, start_ts, end_ts); returns (dc, ...)
        t0 = time.perf_counter()
        v_cnt_rows   = self._run_rows(cursor, vq.BATCH_COUNTS,  (dc_list, start_ts, end_ts))
        v_mem_rows   = self._run_rows(cursor, vq.BATCH_MEMORY,  (dc_list, start_ts, end_ts))
        v_stor_rows  = self._run_rows(cursor, vq.BATCH_STORAGE, (dc_list, start_ts, end_ts))
        v_cpu_rows   = self._run_rows(cursor, vq.BATCH_CPU,     (dc_list, start_ts, end_ts))
        logger.info("Batch fetch: VMware done in %.2fs", time.perf_counter() - t0)

        # IBM — params (start_ts, end_ts, dc_list); returns (dc_code, ...)
        t0 = time.perf_counter()
        ibm_rows     = self._run_rows(cursor, iq.BATCH_HOST_COUNT, (start_ts, end_ts, dc_list))
        ibm_vios_rows = self._run_rows(cursor, iq.BATCH_VIOS_COUNT, (start_ts, end_ts, dc_list))
        ibm_lpar_rows = self._run_rows(cursor, iq.BATCH_LPAR_COUNT, (start_ts, end_ts, dc_list))
        ibm_mem_rows  = self._run_rows(cursor, iq.BATCH_MEMORY, (start_ts, end_ts, dc_list))
        ibm_cpu_rows  = self._run_rows(cursor, iq.BATCH_CPU, (start_ts, end_ts, dc_list))
        logger.info("Batch fetch: IBM done in %.2fs", time.perf_counter() - t0)

        # Energy — IBM/vCenter only; params (dc_list, start_ts, end_ts) for vCenter; (start_ts, end_ts, dc_list) for IBM
        t0 = time.perf_counter()
        ibm_e_rows   = self._run_rows(cursor, eq.BATCH_IBM, (start_ts, end_ts, dc_list))
        vcenter_rows = self._run_rows(cursor, eq.BATCH_VCENTER, (dc_list, start_ts, end_ts))
        logger.info("Batch fetch: Energy done in %.2fs", time.perf_counter() - t0)

        # --- Map batch rows back to DC codes ---

        def _match_dc(name: str) -> str | None:
            """Find which DC code appears in a string."""
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
            """Exact key match: {row[col_idx]: row}. Used for datacenter_name batches."""
            return {row[col_idx]: row for row in rows if row and len(row) > col_idx and row[col_idx]}

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

        # Energy: batch returns (dc_code, avg_power_watts)
        ibm_e   = {row[0]: float(row[1] or 0) for row in ibm_e_rows if row and len(row) >= 2 and row[0]}
        vctr_e  = {row[0]: float(row[1] or 0) for row in vcenter_rows if row and len(row) >= 2 and row[0]}

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
            )

        return results

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

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    all_dc_data = self._fetch_all_batch(cur, dc_list, start_ts, end_ts)
            logger.info("Batch fetch complete, aggregating per-DC...")
        except OperationalError as exc:
            logger.error("DB unavailable for get_all_datacenters_summary: %s", exc)
            all_dc_data = {dc: _EMPTY_DC(dc) for dc in dc_list}

        summary_list = []
        for dc in dc_list:
            d = all_dc_data.get(dc, _EMPTY_DC(dc))
            intel = d["intel"]
            power = d["power"]

            cpu_cap   = intel["cpu_cap"]       or 0
            cpu_used  = intel["cpu_used"]      or 0
            ram_cap   = intel["ram_cap"]       or 0
            ram_used  = intel["ram_used"]      or 0
            stor_cap  = intel["storage_cap"]   or 0
            stor_used = intel["storage_used"]  or 0

            # Platform count: 1 if any Intel (Nutanix/VMware), 1 if any IBM Power
            has_intel = (intel["clusters"] > 0 or intel["hosts"] > 0 or intel["vms"] > 0)
            has_ibm = (power["hosts"] > 0 or power["vios"] > 0 or power["lpar_count"] > 0)
            platform_count = (1 if has_intel else 0) + (1 if has_ibm else 0)

            summary_list.append({
                "id": dc,
                "name": dc,
                "location": d["meta"]["location"],
                "status": "Healthy",
                "platform_count": platform_count,
                "cluster_count": intel["clusters"],
                "host_count": intel["hosts"] + power["hosts"],
                "vm_count": intel["vms"] + power["vms"],
                "stats": {
                    "total_cpu": f"{cpu_used:,} / {cpu_cap:,} GHz",
                    "used_cpu_pct": round((cpu_used / cpu_cap * 100) if cpu_cap > 0 else 0, 1),
                    "total_ram": f"{ram_used:,} / {ram_cap:,} GB",
                    "used_ram_pct": round((ram_used / ram_cap * 100) if ram_cap > 0 else 0, 1),
                    "total_storage": f"{stor_used:,} / {stor_cap:,} TB",
                    "used_storage_pct": round((stor_used / stor_cap * 100) if stor_cap > 0 else 0, 1),
                    "last_updated": "Live",
                    "total_energy_kw": d["energy"]["total_kw"],
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
            "total_clusters": sum(s["cluster_count"] for s in summary_list),
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
        logger.info("Rebuilt summary for %d DCs.", len(summary_list))
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

    def get_customer_resources(self, customer_pattern: str, time_range: dict | None = None) -> dict:
        """Return resource totals and per-DC breakdown for a customer (e.g. ILIKE '%boyner%') for the given time range."""
        tr = time_range or default_time_range()
        cache_key = f"customer:{customer_pattern}:{tr.get('start','')}:{tr.get('end','')}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        pattern = f"%{customer_pattern.strip()}%" if customer_pattern else "%"
        start_ts, end_ts = time_range_to_bounds(tr)
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    nutanix_tot = self._run_row(cur, cq.NUTANIX_TOTALS, (pattern, start_ts, end_ts))
                    nutanix_by_dc = self._run_rows(cur, cq.NUTANIX_BY_DC, (pattern, start_ts, end_ts))
                    vmware_tot = self._run_row(cur, cq.VMWARE_TOTALS, (pattern, start_ts, end_ts))
                    vmware_by_dc = self._run_rows(cur, cq.VMWARE_BY_DC, (pattern, start_ts, end_ts))
                    ibm_lpar = self._run_value(cur, cq.IBM_LPAR_TOTALS, (pattern, start_ts, end_ts))
                    ibm_vios = self._run_value(cur, cq.IBM_VIOS_TOTALS, (pattern, pattern, start_ts, end_ts))
                    ibm_host = self._run_value(cur, cq.IBM_HOST_TOTALS, (pattern, start_ts, end_ts))
                    vcenter_host = self._run_value(cur, cq.VCENTER_HOST_TOTALS, (pattern, start_ts, end_ts))
        except OperationalError as exc:
            logger.warning("get_customer_resources failed: %s", exc)
            return {
                "totals": {"hosts": 0, "vms": 0, "dcs_used": 0},
                "by_platform": {"nutanix": {}, "vmware": {}, "ibm": {}, "vcenter": {}},
                "by_dc": [],
            }
        nh = int(nutanix_tot[0] or 0) if nutanix_tot else 0
        nv = int(nutanix_tot[1] or 0) if nutanix_tot and len(nutanix_tot) > 1 else 0
        vc = int(vmware_tot[0] or 0) if vmware_tot else 0
        vh = int(vmware_tot[1] or 0) if vmware_tot and len(vmware_tot) > 1 else 0
        vv = int(vmware_tot[2] or 0) if vmware_tot and len(vmware_tot) > 2 else 0
        dcs_used = set()
        for row in nutanix_by_dc:
            if row[0]:
                dcs_used.add(str(row[0]))
        for row in vmware_by_dc:
            if row[0]:
                dcs_used.add(str(row[0]))
        result = {
            "totals": {
                "hosts": nh + vh + ibm_host + vcenter_host,
                "vms": nv + vv + ibm_lpar,
                "dcs_used": len(dcs_used),
            },
            "by_platform": {
                "nutanix": {"hosts": nh, "vms": nv},
                "vmware": {"clusters": vc, "hosts": vh, "vms": vv},
                "ibm": {"hosts": ibm_host, "vios": ibm_vios, "lpars": ibm_lpar},
                "vcenter": {"hosts": vcenter_host},
            },
            "by_dc": [{"dc": r[0], "hosts": r[1], "vms": r[2]} for r in nutanix_by_dc] if nutanix_by_dc else [],
        }
        cache.set(cache_key, result)
        return result

    def get_customer_list(self) -> list[str]:
        """Return list of customer names for selector (beta: Boyner only)."""
        return ["Boyner"]

    # ------------------------------------------------------------------
    # Cache warming / background refresh API
    # ------------------------------------------------------------------

    def warm_cache(self) -> None:
        """
        Pre-load all data into cache at app startup for the three fixed ranges:
        last 7 days, last 30 days, and previous calendar month.
        Called once immediately so the first user request is served from cache.
        """
        logger.info("Warming cache at startup (last 7d, last 30d, previous month)…")
        try:
            for tr in cache_time_ranges():
                self._rebuild_summary(tr)
                self.get_global_overview(tr)
            logger.info("Cache warm-up complete.")
        except Exception as exc:
            logger.warning("Cache warm-up failed (DB may be unavailable): %s", exc)

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
