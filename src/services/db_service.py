import os
import logging
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool as pg_pool
from psycopg2 import OperationalError

from src.queries import nutanix as nq, vmware as vq, ibm as iq, energy as eq
from src.queries import loki as lq
from src.services import cache_service as cache

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
        "power": {"hosts": 0, "vms": 0, "cpu": 0, "ram": 0},
        "energy": {"total_kw": 0.0},
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

    def get_nutanix_host_count(self, cursor, dc_param: str) -> int:
        return self._run_value(cursor, nq.HOST_COUNT, (dc_param,))

    def get_nutanix_memory(self, cursor, dc_param: str) -> tuple | None:
        return self._run_row(cursor, nq.MEMORY, (dc_param,))

    def get_nutanix_storage(self, cursor, dc_param: str) -> tuple | None:
        return self._run_row(cursor, nq.STORAGE, (dc_param,))

    def get_nutanix_cpu(self, cursor, dc_param: str) -> tuple | None:
        return self._run_row(cursor, nq.CPU, (dc_param,))

    def get_vmware_counts(self, cursor, dc_param: str) -> tuple | None:
        return self._run_row(cursor, vq.COUNTS, (dc_param,))

    def get_vmware_memory(self, cursor, dc_param: str) -> tuple | None:
        return self._run_row(cursor, vq.MEMORY, (dc_param,))

    def get_vmware_storage(self, cursor, dc_param: str) -> tuple | None:
        return self._run_row(cursor, vq.STORAGE, (dc_param,))

    def get_vmware_cpu(self, cursor, dc_param: str) -> tuple | None:
        return self._run_row(cursor, vq.CPU, (dc_param,))

    def get_ibm_host_count(self, cursor, dc_param: str) -> int:
        return self._run_value(cursor, iq.HOST_COUNT, (dc_param,))

    def get_racks_energy(self, cursor, dc_code: str) -> float:
        try:
            val = self._run_value(cursor, eq.RACKS, (dc_code,))
            return float(val) if val else 0.0
        except Exception as exc:
            logger.warning("Racks energy query failed for %s: %s", dc_code, exc)
            return 0.0

    def get_ibm_energy(self, cursor, dc_param: str) -> float:
        return self._run_value(cursor, eq.IBM, (dc_param,))

    def get_vcenter_energy(self, cursor, dc_param: str) -> float:
        return self._run_value(cursor, eq.VCENTER, (dc_param,))

    # ------------------------------------------------------------------
    # Unit normalization & aggregation (shared by single + batch paths)
    # ------------------------------------------------------------------

    @staticmethod
    def _aggregate_dc(
        dc_code: str,
        nutanix_host_count,
        nutanix_mem,
        nutanix_storage,
        nutanix_cpu,
        vmware_counts,
        vmware_mem,
        vmware_storage,
        vmware_cpu,
        power_hosts,
        racks_w,
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

        # Memory → GB
        # Nutanix raw: TB  → × 1024
        # VMware raw : Bytes → ÷ 1024³
        n_mem_cap_gb  = (nutanix_mem[0] or 0) * 1024
        n_mem_used_gb = (nutanix_mem[1] or 0) * 1024
        v_mem_cap_gb  = (vmware_mem[0] or 0) / (1024 ** 3)
        v_mem_used_gb = (vmware_mem[1] or 0) / (1024 ** 3)

        # Storage → TB
        # Nutanix raw: TB  → no change
        # VMware raw : KB (GB × 1 MB) → ÷ 1024⁴
        n_stor_cap_tb  = (nutanix_storage[0] or 0)
        n_stor_used_tb = (nutanix_storage[1] or 0)
        v_stor_cap_tb  = (vmware_storage[0] or 0) / (1024 ** 4)
        v_stor_used_tb = (vmware_storage[1] or 0) / (1024 ** 4)

        # CPU → GHz
        # Nutanix raw: GHz → no change
        # VMware raw : Hz  → ÷ 1e9
        n_cpu_cap_ghz  = (nutanix_cpu[0] or 0)
        n_cpu_used_ghz = (nutanix_cpu[1] or 0)
        v_cpu_cap_ghz  = (vmware_cpu[0] or 0) / 1_000_000_000
        v_cpu_used_ghz = (vmware_cpu[1] or 0) / 1_000_000_000

        # Energy → kW
        total_energy_kw = (
            float(racks_w or 0) + float(ibm_w or 0) + float(vcenter_w or 0)
        ) / 1000.0

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
                "vms": 0, "cpu": 0, "ram": 0,
            },
            "energy": {
                "total_kw": round(total_energy_kw, 2),
            },
        }

    # ------------------------------------------------------------------
    # Public API — dc_view.py: single DC detail
    # ------------------------------------------------------------------

    def get_dc_details(self, dc_code: str) -> dict:
        """Return full metrics dict for a single data center. Result is TTL-cached."""
        cache_key = f"dc_details:{dc_code}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    dc_wc = f"%{dc_code}%"
                    result = self._aggregate_dc(
                        dc_code,
                        nutanix_host_count=self.get_nutanix_host_count(cur, dc_wc),
                        nutanix_mem=self.get_nutanix_memory(cur, dc_wc),
                        nutanix_storage=self.get_nutanix_storage(cur, dc_wc),
                        nutanix_cpu=self.get_nutanix_cpu(cur, dc_wc),
                        vmware_counts=self.get_vmware_counts(cur, dc_wc),
                        vmware_mem=self.get_vmware_memory(cur, dc_wc),
                        vmware_storage=self.get_vmware_storage(cur, dc_wc),
                        vmware_cpu=self.get_vmware_cpu(cur, dc_wc),
                        power_hosts=self.get_ibm_host_count(cur, dc_wc),
                        racks_w=self.get_racks_energy(cur, dc_code),
                        ibm_w=self.get_ibm_energy(cur, dc_wc),
                        vcenter_w=self.get_vcenter_energy(cur, dc_wc),
                    )
        except OperationalError as exc:
            logger.error("DB unavailable for get_dc_details(%s): %s", dc_code, exc)
            return _EMPTY_DC(dc_code)

        cache.set(cache_key, result)
        return result

    # ------------------------------------------------------------------
    # Batch fetch (internal) — used by get_all_datacenters_summary
    # ------------------------------------------------------------------

    def _fetch_all_batch(self, cursor, dc_list: list[str]) -> dict[str, dict]:
        """
        Execute all batch queries in one connection and map results back to DC codes.
        Reduces DB roundtrips from 9×10=90 → ~10.
        """
        wildcard_patterns = [f"%{dc}%" for dc in dc_list]

        # Nutanix — uses datacenter_name column (exact DC code)
        n_host_rows  = self._run_rows(cursor, nq.BATCH_HOST_COUNT, (dc_list,))
        n_mem_rows   = self._run_rows(cursor, nq.BATCH_MEMORY,     (dc_list,))
        n_stor_rows  = self._run_rows(cursor, nq.BATCH_STORAGE,    (dc_list,))
        n_cpu_rows   = self._run_rows(cursor, nq.BATCH_CPU,        (dc_list,))

        # VMware — datacenter column, ILIKE ANY(wildcard_patterns)
        v_cnt_rows   = self._run_rows(cursor, vq.BATCH_COUNTS,  (wildcard_patterns,))
        v_mem_rows   = self._run_rows(cursor, vq.BATCH_MEMORY,  (wildcard_patterns,))
        v_stor_rows  = self._run_rows(cursor, vq.BATCH_STORAGE, (wildcard_patterns,))
        v_cpu_rows   = self._run_rows(cursor, vq.BATCH_CPU,     (wildcard_patterns,))

        # IBM — server_details_servername LIKE ANY(wildcard_patterns)
        ibm_rows     = self._run_rows(cursor, iq.BATCH_HOST_COUNT, (wildcard_patterns,))

        # Energy
        rack_rows    = self._run_rows(cursor, eq.BATCH_RACKS,   (dc_list,))
        ibm_e_rows   = self._run_rows(cursor, eq.BATCH_IBM,     (wildcard_patterns,))
        vcenter_rows = self._run_rows(cursor, eq.BATCH_VCENTER, (wildcard_patterns,))

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
                dc = _match_dc(str(row[col_idx]))
                if dc and dc not in out:
                    out[dc] = row
            return out

        def _index_exact(rows, col_idx: int = 0) -> dict[str, tuple]:
            """Exact key match: {row[col_idx]: row}. Used for datacenter_name batches."""
            return {row[col_idx]: row for row in rows if row[col_idx]}

        def _sum_by_dc(rows, value_col: int, col_idx: int = 0) -> dict[str, float]:
            """Sum numeric column per DC (e.g. energy watts, IBM hosts)."""
            out: dict[str, float] = {}
            for row in rows:
                dc = _match_dc(str(row[col_idx]))
                if dc:
                    out[dc] = out.get(dc, 0) + float(row[value_col] or 0)
            return out

        # Nutanix batch results use datacenter_name as exact key (col 0)
        n_host  = _index_exact(n_host_rows)
        n_mem   = _index_exact(n_mem_rows)
        n_stor  = _index_exact(n_stor_rows)
        n_cpu   = _index_exact(n_cpu_rows)

        # VMware / IBM use wildcard-matched name
        v_cnt   = _index_by_dc(v_cnt_rows)
        v_mem   = _index_by_dc(v_mem_rows)
        v_stor  = _index_by_dc(v_stor_rows)
        v_cpu   = _index_by_dc(v_cpu_rows)
        ibm_h   = _sum_by_dc(ibm_rows, value_col=1)

        # Energy: racks by exact location_name; IBM/vCenter by wildcard
        rack_e  = {row[0]: float(row[1] or 0) for row in rack_rows if row[0]}
        ibm_e   = _sum_by_dc(ibm_e_rows, value_col=1)
        vctr_e  = _sum_by_dc(vcenter_rows, value_col=1)

        results: dict[str, dict] = {}
        for dc in dc_list:
            nh_row   = n_host.get(dc)
            nm_row   = n_mem.get(dc)
            ns_row   = n_stor.get(dc)
            nc_row   = n_cpu.get(dc)
            vc_row   = v_cnt.get(dc)
            vm_row   = v_mem.get(dc)
            vs_row   = v_stor.get(dc)
            vcpu_row = v_cpu.get(dc)

            results[dc] = self._aggregate_dc(
                dc_code=dc,
                nutanix_host_count=nh_row[1] if nh_row else 0,
                nutanix_mem=(nm_row[1], nm_row[2]) if nm_row else None,
                nutanix_storage=(ns_row[1], ns_row[2]) if ns_row else None,
                nutanix_cpu=(nc_row[1], nc_row[2]) if nc_row else None,
                vmware_counts=(vc_row[1], vc_row[2], vc_row[3]) if vc_row else None,
                vmware_mem=(vm_row[1], vm_row[2]) if vm_row else None,
                vmware_storage=(vs_row[1], vs_row[2]) if vs_row else None,
                vmware_cpu=(vcpu_row[1], vcpu_row[2]) if vcpu_row else None,
                power_hosts=ibm_h.get(dc, 0),
                racks_w=rack_e.get(dc, 0.0),
                ibm_w=ibm_e.get(dc, 0.0),
                vcenter_w=vctr_e.get(dc, 0.0),
            )

        return results

    # ------------------------------------------------------------------
    # Public API — datacenters.py: summary list
    # ------------------------------------------------------------------

    def get_all_datacenters_summary(self) -> list[dict]:
        """
        Returns summary list for all active DCs (dynamic list from loki_locations).
        Uses batch queries → ~10 DB roundtrips.
        Result is TTL-cached; background scheduler keeps it warm.
        """
        cache_key = "all_dc_summary"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        return self._rebuild_summary()

    def _rebuild_summary(self) -> list[dict]:
        """Fetch fresh data and rebuild the summary list. Also populates per-DC cache."""
        # Reload DC list on every rebuild so new DCs are picked up automatically
        self._dc_list = self._load_dc_list()
        dc_list = self._dc_list

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    all_dc_data = self._fetch_all_batch(cur, dc_list)
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

            summary_list.append({
                "id": dc,
                "name": dc,
                "location": d["meta"]["location"],
                "status": "Healthy",
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
            cache.set(f"dc_details:{dc}", d)

        cache.set("all_dc_summary", summary_list)
        logger.info("Rebuilt summary for %d DCs.", len(summary_list))
        return summary_list

    # ------------------------------------------------------------------
    # Public API — home.py: global totals
    # ------------------------------------------------------------------

    def get_global_overview(self) -> dict:
        """Return global totals. Always derived from get_all_datacenters_summary (cached)."""
        cache_key = "global_overview"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        summaries = self.get_all_datacenters_summary()
        result = {
            "total_hosts": sum(s["host_count"] for s in summaries),
            "total_vms": sum(s["vm_count"] for s in summaries),
            "total_energy_kw": round(sum(s["stats"]["total_energy_kw"] for s in summaries), 2),
            "dc_count": len(summaries),
        }
        cache.set(cache_key, result)
        return result

    # ------------------------------------------------------------------
    # Cache warming / background refresh API
    # ------------------------------------------------------------------

    def warm_cache(self) -> None:
        """
        Pre-load all data into cache at app startup.
        Called once immediately so the first user request is served from cache.
        """
        logger.info("Warming cache at startup…")
        try:
            self._rebuild_summary()
            self.get_global_overview()
            logger.info("Cache warm-up complete.")
        except Exception as exc:
            logger.warning("Cache warm-up failed (DB may be unavailable): %s", exc)

    def refresh_all_data(self) -> None:
        """
        Called by the background scheduler every 15 minutes.
        Clears and rebuilds the summary + global caches without blocking user requests.
        Per-DC caches are refreshed as a side-effect of _rebuild_summary.
        """
        logger.info("Background cache refresh started.")
        try:
            # Evict stale top-level keys so _rebuild_summary fetches fresh data
            cache.delete("all_dc_summary")
            cache.delete("global_overview")
            self._rebuild_summary()
            self.get_global_overview()
            logger.info("Background cache refresh complete.")
        except Exception as exc:
            logger.error("Background cache refresh failed: %s", exc)

    @property
    def dc_list(self) -> list[str]:
        """Expose current dynamic DC list (read-only)."""
        return list(self._dc_list)
