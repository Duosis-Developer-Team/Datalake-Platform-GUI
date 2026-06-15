from __future__ import annotations
import os
import re
import logging
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from psycopg2 import pool as pg_pool
from psycopg2 import OperationalError
from psycopg2.pool import PoolError

from app.db.queries import nutanix as nq, vmware as vq, virt_compute as vcq, ibm as iq, energy as eq
from app.db.queries import vmware_datastore as vdq
from app.db.queries import loki as lq, customer as cq, s3 as s3q, backup as bq
from app.db.queries import brocade as brq, ibm_storage as isq
from app.db.queries import zabbix_network as znq, zabbix_storage as zsq
from app.db.queries import discovery_rack as drq
from app.db.queries import crm_potential as crm_q
from app.db.queries import crm_network_pricing as net_price_q
from app.db.queries import netbox_config as nbq
from app.config import settings
from app.services import cache_service as cache
from app.services import query_overrides as qo
from app.utils.time_range import (
    default_time_range,
    time_range_to_bounds,
    cache_time_ranges,
    backup_jobs_warm_windows,
    BACKUP_JOBS_WARM_GRANULARITIES,
)
from app.utils.format_units import smart_cpu, smart_memory, smart_storage
from shared.customer.cache_keys import customer_assets_cache_key
from shared.network.backbone_billing import estimate_backbone_cost_tl, p95_bps_to_mbit
from shared.vmware.host_cpu_ghz import (
    DEFAULT_HOST_CPU_GHZ,
    NETBOX_HOST_CPU_STRINGS,
    aggregate_vm_allocation,
    cached_host_map,
    compute_cpu_overalloc_flags,
    enrich_customer_vm_cpu_list,
    enrich_vm_cpu_sales_fields,
    resolve_host_ghz,
    sum_cpu_real_total,
)
from shared.sellable.host_aggregate import finalize_host_payload
from app.services.netbox_viz_filter import (
    filter_devices_by_role_exclusion,
    is_role_excluded,
    load_excluded_roles,
)

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
    "ICT21": "İngiltere",
    "UZ11": "Özbekistan",
}

WARMED_CUSTOMERS: tuple[str, ...] = ("Boyner",)


def _empty_compute_section() -> dict:
    """Return a zeroed-out compute-type section (classic / hyperconv)."""
    return {
        "hosts": 0, "vms": 0,
        "cpu_cap": 0.0, "cpu_used": 0.0, "cpu_pct": 0.0,
        "cpu_pct_max": 0.0,
        "cpu_pct_min": 0.0,
        "mem_cap": 0.0, "mem_used": 0.0, "mem_pct": 0.0,
        "mem_pct_max": 0.0,
        "mem_pct_min": 0.0,
        "stor_cap": 0.0, "stor_used": 0.0,
        # VM-level allocation (storage thin-provisioned, CPU/RAM assigned)
        "stor_provisioned_gb": 0.0,
        "stor_actual_used_gb": 0.0,
        "cpu_alloc_ghz_vm":    0.0,
        "cpu_alloc_ghz_sales": 0.0,
        "mem_alloc_gb_vm":     0.0,
        "cpu_overallocated_sales": False,
        "cpu_overallocated_real": False,
        "cpu_alloc_hosts_resolved": 0,
        "cpu_alloc_hosts_fallback_default": 0,
        "cpu_util_pct": 0.0,
        "cpu_util_pct_max": 0.0,
        "mem_util_pct": 0.0,
        "mem_util_pct_max": 0.0,
        "mem_used_gb_peak": 0.0,
        "mem_cap_gb_at_peak": 0.0,
        # Potential sellable economics — CRM TL unit prices × capacity × overcommit
        "unit_prices": {"cpu_vcpu": 0.0, "ram_gb": 0.0, "storage_gb": 0.0},
        "sellable_multiplier": 3.3,
    }


def _EMPTY_DC(dc_code: str) -> dict:
    """Return a zeroed-out DC details dict for when the DB is unreachable."""
    return {
        "meta": {
            "name": dc_code,
            "location": DC_LOCATIONS.get(dc_code, "Unknown Data Center"),
            "description": "",
        },
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
            "cpu": 0,
            "cpu_total_procunits": 0.0,
            "cpu_total_cores": 0.0,
            "cpu_available_procunits": 0.0,
            "cpu_available_cores": 0.0,
            "cpu_used": 0.0, "cpu_assigned": 0.0,
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
        self._dc_site_map: dict[str, str] = {}
        self._dc_description_map: dict[str, str] = {}
        # Cache for brocade switch_host -> resolved DC code.
        # Value can be None when no resolution is possible.
        self._brocade_switch_dc_cache: dict[str, str | None] = {}
        # Cache for IBM storage storage_ip -> resolved DC code.
        # Value can be None when no resolution is possible.
        self._ibm_storage_ip_dc_cache: dict[str, str | None] = {}
        self._webui: Any | None = None
        self._init_pool()

    def attach_webui_pool(self, webui: Any | None) -> None:
        self._webui = webui

    # ------------------------------------------------------------------
    # Connection pool
    # ------------------------------------------------------------------

    def _init_pool(self) -> None:
        """Create the connection pool. Logs a warning if DB is unreachable at startup."""
        try:
            self._pool = pg_pool.ThreadedConnectionPool(
                minconn=max(1, int(settings.db_pool_minconn)),
                maxconn=max(int(settings.db_pool_minconn), int(settings.db_pool_maxconn)),
                host=self._db_host,
                port=self._db_port,
                dbname=self._db_name,
                user=self._db_user,
                password=self._db_pass,
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=5,
            )
            logger.info(
                "DB connection pool initialized (min=%s, max=%s).",
                max(1, int(settings.db_pool_minconn)),
                max(int(settings.db_pool_minconn), int(settings.db_pool_maxconn)),
            )
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
    def _sql_label(sql: str) -> str:
        """Extract a short label from SQL for logging (first meaningful keyword line)."""
        for line in sql.strip().splitlines():
            stripped = line.strip().upper()
            if stripped and not stripped.startswith("--") and not stripped.startswith("WITH"):
                return stripped[:120]
        return sql.strip()[:120]

    @staticmethod
    def _run_row(cursor, sql: str, params=None) -> tuple | None:
        """Execute SQL and return the first row tuple, or None."""
        try:
            t0 = time.perf_counter()
            cursor.execute(sql, params)
            row = cursor.fetchone()
            elapsed = (time.perf_counter() - t0) * 1000
            logger.info("SQL row (%.0fms): %s", elapsed, DatabaseService._sql_label(sql))
            return row
        except Exception as exc:
            logger.warning("Query error (row): %s | SQL: %s", exc, DatabaseService._sql_label(sql))
            try:
                cursor.execute("ROLLBACK")
            except Exception:
                pass
        return None

    @staticmethod
    def _run_rows(cursor, sql: str, params=None) -> list[tuple]:
        """Execute SQL and return all rows."""
        try:
            t0 = time.perf_counter()
            cursor.execute(sql, params)
            rows = cursor.fetchall() or []
            elapsed = (time.perf_counter() - t0) * 1000
            logger.info("SQL rows (%.0fms, %d rows): %s", elapsed, len(rows), DatabaseService._sql_label(sql))
            return rows
        except Exception as exc:
            logger.warning("Query error (rows): %s | SQL: %s", exc, DatabaseService._sql_label(sql))
            try:
                cursor.execute("ROLLBACK")
            except Exception:
                pass
        return []

    # ------------------------------------------------------------------
    # DC detection helpers for backup datasets
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_dc_from_text(value: str | None, dc_set: set[str]) -> str | None:
        """Extract a DC code (DCxx / AZxx / ICTxx / UZxx / DHxx) from arbitrary text."""
        if not value:
            return None
        match = _DC_CODE_RE.search(str(value).upper())
        if not match:
            return None
        code = match.group(1).upper()
        return code if code in dc_set else None

    def _resolve_brocade_dc(self, switch_host: str | None) -> str | None:
        """
        Resolve DC code for a brocade `switch_host`.

        Strategy:
        1) Try regex extraction from the switch_host text itself.
        2) Fallback to NetBox discovery:
           - search `discovery_netbox_inventory_device` by matching `primary_ip_address`
             and/or textual fields (name/site_name/location_name) using ILIKE.
           - extract DC code from site_name/location_name/name.

        Returned value is guaranteed to be in `self._dc_list` (DC set) when not None.
        """
        if not switch_host:
            return None

        host_key = str(switch_host).strip()
        if not host_key:
            return None

        if host_key in self._brocade_switch_dc_cache:
            return self._brocade_switch_dc_cache[host_key]

        dc_set = {dc.upper() for dc in self.dc_list}

        # 1) Direct regex detection
        match = _DC_CODE_RE.search(host_key.upper())
        if match:
            code = match.group(1).upper()
            resolved = code if code in dc_set else None
            self._brocade_switch_dc_cache[host_key] = resolved
            return resolved

        # 2) NetBox fallback: match on IP/name and then infer from site/location/name
        resolved: str | None = None
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    like = f"%{host_key}%"
                    rows = self._run_rows(
                        cur,
                        """
SELECT
    site_name,
    location_name,
    "name",
    primary_ip_address
FROM public.discovery_netbox_inventory_device
WHERE
    status_value = 'active'
    AND (
    primary_ip_address = %s
 OR primary_ip_address ILIKE %s
 OR "name" ILIKE %s
 OR location_name ILIKE %s
 OR site_name ILIKE %s
    )
ORDER BY collection_time DESC NULLS LAST
LIMIT 20
""",
                        (host_key, like, like, like, like),
                    )

            for site_name, location_name, name_val, _primary_ip in rows:
                resolved = self._extract_dc_from_text(site_name, dc_set)
                if resolved:
                    break
                resolved = self._extract_dc_from_text(location_name, dc_set)
                if resolved:
                    break
                resolved = self._extract_dc_from_text(name_val, dc_set)
                if resolved:
                    break
        except Exception as exc:
            logger.warning("Could not resolve brocade DC for %s: %s", host_key, exc)
            resolved = None

        self._brocade_switch_dc_cache[host_key] = resolved
        return resolved

    @staticmethod
    def _ip_prefix(value: str | None) -> str | None:
        """
        Return an IP prefix used for grouping hosts by location.

        For IPv4 addresses, this returns the first two octets (e.g. '10.34' for
        '10.34.17.200'). For anything else, returns None.
        """
        if not value:
            return None
        parts = str(value).split(".")
        if len(parts) < 2:
            return None
        return f"{parts[0]}.{parts[1]}"

    def _filter_rows_for_dc_by_name_and_host(
        self,
        rows: list[tuple],
        dc_code: str,
        name_index: int,
        host_index: int,
    ) -> list[tuple]:
        """
        Assign rows to DCs using name pattern and host IP prefix, then filter for dc_code.

        Strategy:
        1. Try to extract DC code from the name field using _DC_CODE_RE.
        2. For rows with a detected DC, record a mapping from IP prefix to DC.
        3. For rows without a name-based DC, fall back to the IP prefix mapping.
        4. Return only rows whose final DC assignment equals dc_code.
        """
        if not rows:
            return []

        dc_target = (dc_code or "").upper()
        if not dc_target:
            return []

        dc_set = {dc.upper() for dc in self.dc_list}
        ip_to_dc: dict[str, str] = {}
        explicit_hosts: set[str] = set()
        staged: list[tuple[str | None, tuple]] = []

        for row in rows:
            if row is None or len(row) <= max(name_index, host_index):
                continue
            name_val = row[name_index]
            host_val = row[host_index]
            dc_from_name = self._extract_dc_from_text(name_val, dc_set)
            ip_pref = self._ip_prefix(host_val)

            if dc_from_name:
                if ip_pref and ip_pref not in ip_to_dc:
                    ip_to_dc[ip_pref] = dc_from_name
                if host_val:
                    explicit_hosts.add(str(host_val))
                staged.append((dc_from_name, row))
            else:
                staged.append((None, row))

        filtered: list[tuple] = []
        for dc_hint, row in staged:
            if row is None or len(row) <= host_index:
                continue
            dc_final = dc_hint
            if not dc_final:
                # If the row shares an exact host with an explicit (name-matched) row,
                # do not auto-assign it by IP prefix. This avoids over-including
                # generic rows on the same host while still allowing prefix grouping
                # across sibling hosts (e.g., .200 → .201).
                host_val = row[host_index]
                if host_val and str(host_val) in explicit_hosts:
                    continue
                ip_pref = self._ip_prefix(row[host_index])
                if ip_pref and ip_pref in ip_to_dc:
                    dc_final = ip_to_dc[ip_pref]
            if dc_final and dc_final.upper() == dc_target:
                filtered.append(row)

        return filtered

    def _filter_rows_for_dc_by_host_pattern(
        self,
        rows: list[tuple],
        dc_code: str,
        host_index: int,
    ) -> list[tuple]:
        """
        Assign rows to DCs using only host name patterns (for Veeam).

        The host_name column may contain tokens like 'dc13' or 'ict13'. We extract
        a DC code using the same regex as other platforms and keep rows that match
        the requested dc_code. Rows without a detectable DC code are ignored.
        """
        if not rows:
            return []

        dc_target = (dc_code or "").upper()
        if not dc_target:
            return []

        dc_set = {dc.upper() for dc in self.dc_list}
        filtered: list[tuple] = []
        for row in rows:
            if row is None or len(row) <= host_index:
                continue
            host_val = row[host_index]
            dc_from_host = self._extract_dc_from_text(host_val, dc_set)
            if dc_from_host and dc_from_host.upper() == dc_target:
                filtered.append(row)

        return filtered

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
        self._dc_description_map = {}
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    rows = self._run_rows(cur, lq.DC_LIST_WITH_SITE)
                    dc_names = [row[0] for row in rows if row[0]]
                    if not dc_names:
                        rows = self._run_rows(cur, lq.DC_LIST_WITH_SITE_NO_STATUS)
                        dc_names = [row[0] for row in rows if row[0]]
                    self._dc_site_map = {row[0]: row[1] for row in rows if row[0] and row[1]}
                    desc_rows = self._run_rows(cur, lq.DC_NAME_DESCRIPTION_MAP)
                    if not desc_rows:
                        desc_rows = self._run_rows(cur, lq.DC_NAME_DESCRIPTION_MAP_NO_STATUS)
                    for row in desc_rows:
                        if row and row[0] and len(row) > 1 and row[1]:
                            self._dc_description_map[str(row[0]).strip()] = str(row[1]).strip()
        except OperationalError as exc:
            logger.warning("Could not load DC list from DB: %s — using fallback.", exc)
            return _FALLBACK_DC_LIST.copy()

        if dc_names:
            logger.info("Loaded %d datacenters from loki_locations: %s", len(dc_names), dc_names)
            return dc_names

        logger.warning("loki_locations returned empty DC list — using fallback.")
        return _FALLBACK_DC_LIST.copy()

    def _ensure_dc_description_map(self, cur) -> None:
        """Lazy-load NetBox location descriptions (name → facility description) once per process."""
        if self._dc_description_map:
            return
        try:
            rows = self._run_rows(cur, lq.DC_NAME_DESCRIPTION_MAP)
            if not rows:
                rows = self._run_rows(cur, lq.DC_NAME_DESCRIPTION_MAP_NO_STATUS)
            for row in rows:
                if row and row[0] and len(row) > 1 and row[1]:
                    self._dc_description_map[str(row[0]).strip()] = str(row[1]).strip()
        except Exception as exc:
            logger.warning("Could not load DC description map: %s", exc)

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

    def get_classic_metrics(
        self, cursor, dc_wc: str, start_ts, end_ts, *, dc_code: str | None = None
    ) -> tuple | None:
        """Return Classic (KM) cluster aggregate row with Nutanix CPU/RAM fallback."""
        dc_param = dc_code or dc_wc.strip("%")
        return self._run_row(
            cursor, vcq.CLASSIC_CPU_MEM_MERGED, (dc_wc, start_ts, end_ts, dc_param, start_ts, end_ts)
        )

    def get_classic_avg30(
        self, cursor, dc_wc: str, start_ts, end_ts, *, dc_code: str | None = None
    ) -> tuple | None:
        """Return Classic cluster utilization (merged VMware + Nutanix fallback)."""
        dc_param = dc_code or dc_wc.strip("%")
        return self._run_row(
            cursor, vcq.CLASSIC_AVG30_MERGED, (dc_wc, start_ts, end_ts, dc_param, start_ts, end_ts)
        )

    @staticmethod
    def _mem_peak_tuple(row: tuple | None) -> tuple[float, float, float]:
        if not row:
            return 0.0, 0.0, 0.0
        used = float(row[0] or 0)
        cap = float(row[1] or 0)
        pct = round(float(row[2] or 0), 1)
        return used, cap, pct

    @staticmethod
    def _apply_mem_peak_raw(section: dict, peak: tuple[float, float, float] | None) -> dict:
        if not peak:
            return section
        used, cap, pct = peak
        if used <= 0 and cap <= 0:
            return section
        return {
            **section,
            "mem_util_pct_max": pct,
            "mem_pct_max": pct,
            "mem_used_gb_peak": round(used, 2),
            "mem_cap_gb_at_peak": round(cap, 2),
        }

    def get_classic_mem_peak_raw(
        self,
        cursor,
        dc_wc: str,
        start_ts,
        end_ts,
        *,
        cluster_filter: list[str] | None = None,
    ) -> tuple[float, float, float]:
        clusters = cluster_filter or []
        if clusters:
            row = self._run_row(
                cursor, vq.CLASSIC_MEM_PEAK_RAW_FILTERED, (dc_wc, clusters, start_ts, end_ts)
            )
        else:
            row = self._run_row(cursor, vq.CLASSIC_MEM_PEAK_RAW, (dc_wc, start_ts, end_ts))
        return self._mem_peak_tuple(row)

    def get_hyperconv_mem_peak_raw(
        self,
        cursor,
        dc_wc: str,
        dc_code: str,
        start_ts,
        end_ts,
        *,
        cluster_filter: list[str] | None = None,
    ) -> tuple[float, float, float]:
        clusters = cluster_filter or []
        vmw_row = None
        ntx_row = None
        if clusters:
            vmw_row = self._run_row(
                cursor, vq.HYPERCONV_MEM_PEAK_RAW_FILTERED, (dc_wc, clusters, start_ts, end_ts)
            )
            ntx_row = self._run_row(
                cursor, nq.NUTANIX_MEM_PEAK_RAW_FILTERED, (dc_code, clusters, start_ts, end_ts)
            )
        else:
            vmw_row = self._run_row(cursor, vq.HYPERCONV_MEM_PEAK_RAW, (dc_wc, start_ts, end_ts))
            ntx_row = self._run_row(cursor, nq.NUTANIX_MEM_PEAK_RAW, (dc_code, start_ts, end_ts))
        vmw = self._mem_peak_tuple(vmw_row)
        ntx = self._mem_peak_tuple(ntx_row)
        if vmw[0] >= ntx[0]:
            return vmw
        return ntx

    def get_hyperconv_metrics(
        self, cursor, dc_wc: str, start_ts, end_ts, *, dc_code: str | None = None
    ) -> tuple | None:
        """Return Hyperconverged cluster aggregate row with Nutanix CPU/RAM fallback."""
        dc_param = dc_code or dc_wc.strip("%")
        return self._run_row(
            cursor, vcq.HYPERCONV_CPU_MEM_MERGED, (dc_wc, start_ts, end_ts, dc_param, start_ts, end_ts)
        )

    def get_hyperconv_avg30(
        self, cursor, dc_wc: str, start_ts, end_ts, *, dc_code: str | None = None
    ) -> tuple | None:
        """Return Hyperconverged cluster utilization (merged VMware + Nutanix fallback)."""
        dc_param = dc_code or dc_wc.strip("%")
        return self._run_row(
            cursor, vcq.HYPERCONV_AVG30_MERGED, (dc_wc, start_ts, end_ts, dc_param, start_ts, end_ts)
        )

    # VM-level allocation: storage (provisioned/used) + CPU/RAM allocated via NetBox host GHz
    _VMWARE_DEFAULT_GHZ_KEY = "vmware.default_host_cpu_ghz"

    def _get_default_host_cpu_ghz(self) -> float:
        """Read UI-configured fallback GHz from webui gui_crm_calc_config."""
        default = DEFAULT_HOST_CPU_GHZ
        webui = getattr(self, "_webui", None)
        if webui is None or not getattr(webui, "is_available", False):
            return default
        try:
            row = webui.run_one(
                "SELECT config_value FROM gui_crm_calc_config WHERE config_key = %s",
                (self._VMWARE_DEFAULT_GHZ_KEY,),
            )
            if row and row.get("config_value") is not None:
                parsed = float(row["config_value"])
                if parsed > 0:
                    return parsed
        except Exception as exc:
            logger.warning("Failed to read %s from webui: %s", self._VMWARE_DEFAULT_GHZ_KEY, exc)
        return default

    def _load_host_ghz_map(self, cursor) -> dict[str, float]:
        def _loader():
            return self._run_rows(cursor, vq.NETBOX_HOST_CPU_STRINGS)

        return cached_host_map(_loader, default_ghz=self._get_default_host_cpu_ghz())

    def _compute_vmware_vm_allocation(
        self,
        cursor,
        dc_wc: str,
        start_ts,
        end_ts,
        *,
        classic_km: bool,
        cluster_filter: list[str] | None = None,
    ) -> dict:
        """Aggregate VM-level CPU/RAM/storage allocation for KM or VMware hyperconv."""
        clusters = cluster_filter or []
        sql = vq.CLASSIC_VM_ALLOCATION_ROWS if classic_km else vq.HYPERCONV_VMWARE_VM_ALLOCATION_ROWS
        rows = self._run_rows(cursor, sql, (dc_wc, start_ts, end_ts, clusters, clusters))
        host_map = self._load_host_ghz_map(cursor)
        return aggregate_vm_allocation(rows, host_map, default_ghz=self._get_default_host_cpu_ghz())

    def get_classic_storage_vm(
        self,
        cursor,
        dc_wc: str,
        start_ts,
        end_ts,
        cluster_filter: list[str] | None = None,
    ) -> dict:
        return self._compute_vmware_vm_allocation(
            cursor, dc_wc, start_ts, end_ts, classic_km=True, cluster_filter=cluster_filter
        )

    def _km_datastore_storage_gb(
        self,
        cursor,
        dc_code: str,
        start_ts,
        end_ts,
    ) -> tuple[float, float]:
        """Sum KM datastore capacity/used (GB) — canonical classic storage source."""
        dc_target = (dc_code or "").upper()
        rows = self._run_rows(cursor, vdq.DATASTORE_METRICS, (dc_target, start_ts, end_ts))
        cap_bytes = sum(int(r[4] or 0) for r in (rows or []))
        used_bytes = sum(int(r[6] or 0) for r in (rows or []))
        _gb = 1024**3
        return round(cap_bytes / _gb, 2), round(used_bytes / _gb, 2)

    @staticmethod
    def _patch_classic_row_storage(classic_row: tuple | None, cap_gb: float, used_gb: float) -> tuple:
        """Replace stor_cap/stor_used slots in a classic metrics row (GB units)."""
        row = list(classic_row or (0,) * 8)
        while len(row) < 8:
            row.append(0)
        if cap_gb > 0:
            row[6] = cap_gb
            row[7] = used_gb
        return tuple(row)

    def _run_nutanix_vm_storage(
        self,
        cursor,
        dc_code: str,
        start_ts,
        end_ts,
        cluster_filter: list[str] | None = None,
    ) -> tuple:
        """Return (provisioned_gb, used_gb, vcpu_count, mem_alloc_gb) from Nutanix VM metrics."""
        clusters = cluster_filter or []
        if clusters:
            row = self._run_row(
                cursor,
                nq.NUTANIX_VM_STORAGE_FILTERED,
                (dc_code, clusters, start_ts, end_ts, start_ts, end_ts),
            )
        else:
            row = self._run_row(
                cursor, nq.NUTANIX_VM_STORAGE, (dc_code, start_ts, end_ts, start_ts, end_ts)
            )
        return row or (0.0, 0.0, 0, 0.0)

    def _compute_nutanix_vm_allocation(
        self,
        cursor,
        dc_code: str,
        start_ts,
        end_ts,
        cluster_filter: list[str] | None = None,
    ) -> dict:
        """Aggregate Nutanix VM allocation with host GHz from NetBox inventory."""
        clusters = cluster_filter or []
        if clusters:
            rows = self._run_rows(
                cursor,
                nq.NUTANIX_VM_ALLOCATION_ROWS_FILTERED,
                (dc_code, clusters, start_ts, end_ts, start_ts, end_ts),
            )
        else:
            rows = self._run_rows(
                cursor, nq.NUTANIX_VM_ALLOCATION_ROWS, (dc_code, start_ts, end_ts, start_ts, end_ts)
            )
        host_map = self._load_host_ghz_map(cursor)
        return aggregate_vm_allocation(rows, host_map, default_ghz=self._get_default_host_cpu_ghz())

    def get_hyperconv_storage_vm(
        self,
        cursor,
        dc_code: str,
        start_ts,
        end_ts,
        cluster_filter: list[str] | None = None,
    ) -> dict:
        dc_wc = f"%{dc_code}%"
        vmw = self._compute_vmware_vm_allocation(
            cursor, dc_wc, start_ts, end_ts, classic_km=False, cluster_filter=cluster_filter
        )
        ntx = self._compute_nutanix_vm_allocation(
            cursor, dc_code, start_ts, end_ts, cluster_filter
        )
        return {
            "stor_provisioned_gb": round(
                float(vmw.get("stor_provisioned_gb") or 0) + float(ntx.get("stor_provisioned_gb") or 0), 2
            ),
            "stor_actual_used_gb": round(
                float(vmw.get("stor_actual_used_gb") or 0) + float(ntx.get("stor_actual_used_gb") or 0), 2
            ),
            "cpu_alloc_ghz_vm": round(
                float(vmw.get("cpu_alloc_ghz_vm") or 0) + float(ntx.get("cpu_alloc_ghz_vm") or 0), 2
            ),
            "cpu_alloc_ghz_sales": round(
                float(vmw.get("cpu_alloc_ghz_sales") or 0) + float(ntx.get("cpu_alloc_ghz_sales") or 0), 2
            ),
            "mem_alloc_gb_vm": round(
                float(vmw.get("mem_alloc_gb_vm") or 0) + float(ntx.get("mem_alloc_gb_vm") or 0), 2
            ),
            "cpu_alloc_hosts_resolved": int(vmw.get("cpu_alloc_hosts_resolved") or 0)
            + int(ntx.get("cpu_alloc_hosts_resolved") or 0),
            "cpu_alloc_hosts_fallback_default": int(vmw.get("cpu_alloc_hosts_fallback_default") or 0)
            + int(ntx.get("cpu_alloc_hosts_fallback_default") or 0),
        }

    @staticmethod
    def _apply_cpu_overalloc_flags(section: dict) -> dict:
        """Merge cpu_overallocated_* flags into a compute section dict."""
        flags = compute_cpu_overalloc_flags(
            section.get("cpu_cap", 0),
            section.get("cpu_alloc_ghz_sales", 0),
            section.get("cpu_alloc_ghz_vm", 0),
        )
        return {**section, **flags}

    def _enrich_customer_vm_list(self, cursor, vm_list: list[dict]) -> list[dict]:
        default_ghz = self._get_default_host_cpu_ghz()

        def _loader():
            return self._run_rows(cursor, NETBOX_HOST_CPU_STRINGS)

        host_map = cached_host_map(_loader, default_ghz=default_ghz)
        return enrich_customer_vm_cpu_list(vm_list, host_map, default_ghz=default_ghz)

    # CRM unit prices (TL) per architecture — used to compute potential sellable revenue
    _SELLABLE_PRODUCT_MAP = {
        "klasik": {
            "cpu":     "Klasik Mimari Intel CPU",
            "ram":     "Klasik Mimari Intel RAM",
            "storage": "Klasik Mimari Intel Disk - SSD",
        },
        "hyperconv": {
            "cpu":     "Hyperconverged Mimari Intel CPU",
            "ram":     "Hyperconverged Mimari Intel RAM",
            "storage": "Hyperconverged Mimari Intel Disk - SSD",
        },
        # Power: yalnızca CPU fiyatlandırması. Birim CRM'de "core" geçse de 1 core = 1 GHz
        # eşdeğeri kabul edilir; Power kaynağı core olduğu için satış hesabında 3.3 ile çarpılarak GHz'e dönüştürülür.
        "power": {
            "cpu": "SAP Power HANA CPU",
        },
    }

    def get_unit_prices_tl(self, cursor, mimari: str) -> dict:
        """Return {cpu_vcpu, ram_gb, storage_gb} TL unit prices for given architecture.
        Power mapping yalnızca CPU içerir; eksik anahtarlar 0.0 döner."""
        mapping = self._SELLABLE_PRODUCT_MAP.get(mimari.lower())
        zero = {"cpu_vcpu": 0.0, "ram_gb": 0.0, "storage_gb": 0.0}
        if not mapping:
            return zero
        names = [v for v in (mapping.get("cpu"), mapping.get("ram"), mapping.get("storage")) if v]
        try:
            rows = self._run_rows(cursor, """
                SELECT p.name, ppl.amount
                FROM discovery_crm_productpricelevels ppl
                JOIN discovery_crm_products p ON p.productid = ppl.productid
                JOIN discovery_crm_pricelevels pl ON pl.pricelevelid = ppl.pricelevelid
                WHERE pl.name ILIKE '%%TL%%'
                  AND pl.statecode = 0
                  AND p.statecode  = 0
                  AND p.name = ANY(%s::text[])
            """, (names,))
        except Exception as exc:
            logger.warning("get_unit_prices_tl(%s) failed: %s", mimari, exc)
            return zero
        name_to_price = {r[0]: float(r[1] or 0) for r in (rows or [])}
        return {
            "cpu_vcpu":   round(name_to_price.get(mapping.get("cpu") or "", 0.0), 4),
            "ram_gb":     round(name_to_price.get(mapping.get("ram") or "", 0.0), 4),
            "storage_gb": round(name_to_price.get(mapping.get("storage") or "", 0.0), 4),
        }

    # ------------------------------------------------------------------
    # Cluster list and filtered metrics (for DC view cluster selector)
    # ------------------------------------------------------------------

    _COMPUTE_CACHE_FRESH_TTL = 600
    _COMPUTE_CACHE_STALE_TTL = 1800

    @staticmethod
    def _compute_cache_key(kind: str, dc_code: str, tr: dict, clusters: list[str]) -> str:
        cluster_part = ",".join(sorted(clusters))
        return f"compute:{kind}:{dc_code}:{tr.get('start', '')}:{tr.get('end', '')}:{cluster_part}"

    def _get_compute_cached(self, key: str) -> dict | None:
        val, _stale = cache.get_with_stale(key)
        return val if isinstance(val, dict) else None

    def _set_compute_cached(self, key: str, value: dict) -> None:
        cache.set_with_stale(key, value, fresh_ttl=self._COMPUTE_CACHE_FRESH_TTL, stale_ttl=self._COMPUTE_CACHE_STALE_TTL)

    def _is_full_cluster_selection(
        self,
        dc_code: str,
        selected_clusters: list[str],
        kind: str,
        time_range: dict,
    ) -> bool:
        if not selected_clusters:
            return True
        if kind == "classic":
            all_clusters = self.get_classic_cluster_list(dc_code, time_range)
        else:
            all_clusters = self.get_hyperconv_cluster_list(dc_code, time_range)
        if not all_clusters:
            return False
        return set(selected_clusters) == set(all_clusters)

    @staticmethod
    def _mem_peak_tuple(row: tuple | None) -> tuple[float, float, float]:
        if not row:
            return 0.0, 0.0, 0.0
        used = float(row[0] or 0)
        cap = float(row[1] or 0)
        pct = round(float(row[2] or 0), 1)
        return used, cap, pct

    @staticmethod
    def _apply_mem_peak_raw(section: dict, peak: tuple[float, float, float] | None) -> dict:
        if not peak:
            return section
        used, cap, pct = peak
        if used <= 0 and cap <= 0:
            return section
        return {
            **section,
            "mem_util_pct_max": pct,
            "mem_pct_max": pct,
            "mem_used_gb_peak": round(used, 2),
            "mem_cap_gb_at_peak": round(cap, 2),
        }

    @staticmethod
    def _apply_mem_avg_ts(section: dict, avg_pct: float | None) -> dict:
        if avg_pct is None or avg_pct <= 0:
            return section
        pct = round(float(avg_pct), 1)
        return {**section, "mem_util_pct": pct, "mem_pct": pct}

    def get_classic_mem_avg_ts_raw(
        self,
        cursor,
        dc_wc: str,
        start_ts,
        end_ts,
        *,
        cluster_filter: list[str] | None = None,
    ) -> float:
        clusters = cluster_filter or []
        if clusters:
            row = self._run_row(
                cursor, vq.CLASSIC_MEM_AVG_TS_RAW_FILTERED, (dc_wc, clusters, start_ts, end_ts)
            )
        else:
            row = self._run_row(cursor, vq.CLASSIC_MEM_AVG_TS_RAW, (dc_wc, start_ts, end_ts))
        return round(float((row or (0,))[0] or 0), 1)

    def get_hyperconv_mem_avg_ts_raw(
        self,
        cursor,
        dc_wc: str,
        start_ts,
        end_ts,
        *,
        cluster_filter: list[str] | None = None,
    ) -> float:
        clusters = cluster_filter or []
        if clusters:
            row = self._run_row(
                cursor, vq.HYPERCONV_MEM_AVG_TS_RAW_FILTERED, (dc_wc, clusters, start_ts, end_ts)
            )
        else:
            row = self._run_row(cursor, vq.HYPERCONV_MEM_AVG_TS_RAW, (dc_wc, start_ts, end_ts))
        return round(float((row or (0,))[0] or 0), 1)

    def _apply_classic_mem_stats(
        self,
        section: dict,
        cursor,
        dc_wc: str,
        start_ts,
        end_ts,
        *,
        cluster_filter: list[str] | None = None,
    ) -> dict:
        peak = self.get_classic_mem_peak_raw(
            cursor, dc_wc, start_ts, end_ts, cluster_filter=cluster_filter
        )
        avg_ts = self.get_classic_mem_avg_ts_raw(
            cursor, dc_wc, start_ts, end_ts, cluster_filter=cluster_filter
        )
        section = self._apply_mem_peak_raw(section, peak)
        return self._apply_mem_avg_ts(section, avg_ts)

    def _apply_hyperconv_mem_stats(
        self,
        section: dict,
        cursor,
        dc_wc: str,
        dc_code: str,
        start_ts,
        end_ts,
        *,
        cluster_filter: list[str] | None = None,
    ) -> dict:
        peak = self.get_hyperconv_mem_peak_raw(
            cursor, dc_wc, dc_code, start_ts, end_ts, cluster_filter=cluster_filter
        )
        avg_ts = self.get_hyperconv_mem_avg_ts_raw(
            cursor, dc_wc, start_ts, end_ts, cluster_filter=cluster_filter
        )
        section = self._apply_mem_peak_raw(section, peak)
        return self._apply_mem_avg_ts(section, avg_ts)

    def get_classic_cluster_list(self, dc_code: str, time_range: dict | None = None) -> list[str]:
        """Return list of Classic (KM) cluster names for the given DC and time range (cached)."""
        tr = time_range or default_time_range()
        cache_key = f"classic_clusters:{dc_code}:{tr.get('start','')}:{tr.get('end','')}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val
        start_ts, end_ts = time_range_to_bounds(tr)
        dc_wc = f"%{dc_code}%"
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    rows = self._run_rows(cur, vq.CLASSIC_CLUSTER_LIST, (dc_wc, start_ts, end_ts))
            result = [r[0] for r in (rows or []) if r and r[0]]
            cache.set(cache_key, result)
            return result
        except OperationalError as exc:
            logger.error("DB unavailable for get_classic_cluster_list(%s): %s", dc_code, exc)
            return []

    def get_hyperconv_cluster_list(self, dc_code: str, time_range: dict | None = None) -> list[str]:
        """Return list of Nutanix cluster names (hyperconverged) for the given DC and time range (cached)."""
        tr = time_range or default_time_range()
        cache_key = f"hyperconv_clusters:{dc_code}:{tr.get('start','')}:{tr.get('end','')}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val
        start_ts, end_ts = time_range_to_bounds(tr)
        dc_wc = f"%{dc_code}%"
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    rows_n = self._run_rows(cur, nq.CLUSTER_LIST, (dc_code, start_ts, end_ts))
                    rows_v = self._run_rows(cur, vq.HYPERCONV_CLUSTER_LIST, (dc_wc, start_ts, end_ts))
            names = {r[0] for r in (rows_n or []) + (rows_v or []) if r and r[0]}
            result = sorted(names)
            cache.set(cache_key, result)
            return result
        except OperationalError as exc:
            logger.error("DB unavailable for get_hyperconv_cluster_list(%s): %s", dc_code, exc)
            return []

    def get_classic_metrics_filtered(
        self, dc_code: str, selected_clusters: list[str] | None, time_range: dict | None = None
    ) -> dict:
        """Return Classic compute section dict, optionally filtered by selected clusters.
        If selected_clusters is None or empty, returns unfiltered classic metrics from get_dc_details."""
        if not selected_clusters:
            full = self.get_dc_details(dc_code, time_range)
            return full.get("classic", _empty_compute_section())

        tr = time_range or default_time_range()
        if self._is_full_cluster_selection(dc_code, selected_clusters, "classic", tr):
            full = self.get_dc_details(dc_code, tr)
            return full.get("classic", _empty_compute_section())

        cache_key = self._compute_cache_key("classic", dc_code, tr, selected_clusters)
        cached = self._get_compute_cached(cache_key)
        if cached is not None:
            return cached

        if tr.get("anchor_latest"):
            tr = self._smart_1h_tr(tr)
        start_ts, end_ts = time_range_to_bounds(tr)
        dc_wc = f"%{dc_code}%"
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    row = self._run_row(
                        cur,
                        vcq.CLASSIC_CPU_MEM_MERGED_FILTERED,
                        (
                            dc_wc,
                            selected_clusters,
                            start_ts,
                            end_ts,
                            dc_code,
                            selected_clusters,
                            start_ts,
                            end_ts,
                            selected_clusters,
                        ),
                    )
                    avg30 = self._run_row(
                        cur,
                        vcq.CLASSIC_AVG30_MERGED_FILTERED,
                        (
                            dc_wc,
                            selected_clusters,
                            start_ts,
                            end_ts,
                            dc_code,
                            selected_clusters,
                            start_ts,
                            end_ts,
                            selected_clusters,
                        ),
                    )
                    storage_vm = self.get_classic_storage_vm(
                        cur, dc_wc, start_ts, end_ts, selected_clusters
                    )
                    mem_peak = self.get_classic_mem_peak_raw(
                        cur, dc_wc, start_ts, end_ts, cluster_filter=selected_clusters
                    )
                    unit_prices = self.get_unit_prices_tl(cur, "klasik")
                    ds_cap_gb, ds_used_gb = self._km_datastore_storage_gb(
                        cur, dc_code, start_ts, end_ts
                    )
                    row = self._patch_classic_row_storage(row, ds_cap_gb, ds_used_gb)
        except OperationalError as exc:
            logger.error("DB unavailable for get_classic_metrics_filtered(%s): %s", dc_code, exc)
            return _empty_compute_section()

        row = row or (0,) * 8
        avg30 = DatabaseService._normalize_avg30_row(avg30)
        cl_hosts = int(row[0] or 0)
        cl_vms = int(row[1] or 0)
        cl_cpu_cap = round(float(row[2] or 0), 2)
        cl_cpu_used = round(float(row[3] or 0), 2)
        cl_mem_cap = round(float(row[4] or 0), 2)
        cl_mem_used = round(float(row[5] or 0), 2)
        cl_stor_cap = round(float(row[6] or 0) / 1024.0, 3)
        cl_stor_used = round(float(row[7] or 0) / 1024.0, 3)
        cl_cpu_pct = round(float(avg30[0] or 0), 1)
        cl_mem_pct = round(float(avg30[1] or 0), 1)
        if cl_cpu_pct == 0.0 and cl_cpu_cap > 0:
            cl_cpu_pct = round(100.0 * cl_cpu_used / cl_cpu_cap, 1)
        if cl_mem_pct == 0.0 and cl_mem_cap > 0:
            cl_mem_pct = round(100.0 * cl_mem_used / cl_mem_cap, 1)
        cl_cpu_pct_max = round(float(avg30[2] or 0), 1)
        cl_mem_pct_max = round(float(avg30[3] or 0), 1)
        cl_cpu_pct_min = round(float(avg30[4] or 0), 1)
        cl_mem_pct_min = round(float(avg30[5] or 0), 1)
        section = self._apply_cpu_overalloc_flags({
            "hosts": cl_hosts,
            "vms": cl_vms,
            "cpu_cap": cl_cpu_cap,
            "cpu_used": cl_cpu_used,
            "cpu_pct": cl_cpu_pct,
            "cpu_pct_max": cl_cpu_pct_max,
            "cpu_pct_min": cl_cpu_pct_min,
            "cpu_util_pct": cl_cpu_pct,
            "cpu_util_pct_max": cl_cpu_pct_max,
            "mem_cap": cl_mem_cap,
            "mem_used": cl_mem_used,
            "mem_pct": cl_mem_pct,
            "mem_pct_max": cl_mem_pct_max,
            "mem_pct_min": cl_mem_pct_min,
            "mem_util_pct": cl_mem_pct,
            "mem_util_pct_max": cl_mem_pct_max,
            "stor_cap": cl_stor_cap,
            "stor_used": cl_stor_used,
            **storage_vm,
            "unit_prices": unit_prices,
            "sellable_multiplier": 3.3,
        })
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    section = self._apply_classic_mem_stats(
                        section, cur, dc_wc, start_ts, end_ts, cluster_filter=selected_clusters
                    )
        except OperationalError:
            pass
        self._set_compute_cached(cache_key, section)
        return section

    def get_hyperconv_metrics_filtered(
        self, dc_code: str, selected_clusters: list[str] | None, time_range: dict | None = None
    ) -> dict:
        """Return Hyperconverged compute section dict, filtered by selected Nutanix clusters.
        If selected_clusters is None or empty, returns unfiltered hyperconv metrics from get_dc_details."""
        if not selected_clusters:
            full = self.get_dc_details(dc_code, time_range)
            return full.get("hyperconv", _empty_compute_section())

        tr = time_range or default_time_range()
        if self._is_full_cluster_selection(dc_code, selected_clusters, "hyperconv", tr):
            full = self.get_dc_details(dc_code, tr)
            return full.get("hyperconv", _empty_compute_section())

        cache_key = self._compute_cache_key("hyperconv", dc_code, tr, selected_clusters)
        cached = self._get_compute_cached(cache_key)
        if cached is not None:
            return cached

        start_ts, end_ts = time_range_to_bounds(tr)
        dc_wc = f"%{dc_code}%"
        mem_peak = None
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    row = self._run_row(
                        cur,
                        vcq.HYPERCONV_CPU_MEM_MERGED_FILTERED,
                        (
                            dc_wc,
                            selected_clusters,
                            start_ts,
                            end_ts,
                            dc_code,
                            selected_clusters,
                            start_ts,
                            end_ts,
                            selected_clusters,
                        ),
                    )
                    hc_avg30 = self._run_row(
                        cur,
                        vcq.HYPERCONV_AVG30_MERGED_FILTERED,
                        (
                            dc_wc,
                            selected_clusters,
                            start_ts,
                            end_ts,
                            dc_code,
                            selected_clusters,
                            start_ts,
                            end_ts,
                            selected_clusters,
                        ),
                    )
                    n_host = self._run_value(
                        cur, nq.HOST_COUNT_FILTERED, (dc_code, selected_clusters, start_ts, end_ts)
                    )
                    n_stor = self._run_row(
                        cur, nq.STORAGE_FILTERED, (dc_code, selected_clusters, start_ts, end_ts)
                    )
                    storage_vm = self.get_hyperconv_storage_vm(
                        cur, dc_code, start_ts, end_ts, selected_clusters
                    )
                    mem_peak = self.get_hyperconv_mem_peak_raw(
                        cur, dc_wc, dc_code, start_ts, end_ts, cluster_filter=selected_clusters
                    )
                    unit_prices = self.get_unit_prices_tl(cur, "hyperconv")
        except OperationalError as exc:
            logger.error("DB unavailable for get_hyperconv_metrics_filtered(%s): %s", dc_code, exc)
            return _empty_compute_section()

        row = row or (0,) * 8
        n_stor = n_stor or (0, 0)
        _bytes_per_tb = 1024**4
        stor_cap_tb = float(n_stor[0] or 0) / _bytes_per_tb
        stor_used_tb = float(n_stor[1] or 0) / _bytes_per_tb
        hc_hosts = int(n_host or 0)
        hc_vms = int(row[1] or 0)
        hc_cpu_cap = round(float(row[2] or 0), 2)
        hc_cpu_used = round(float(row[3] or 0), 2)
        hc_mem_cap = round(float(row[4] or 0), 2)
        hc_mem_used = round(float(row[5] or 0), 2)
        hc_stor_cap = round(stor_cap_tb, 3)
        hc_stor_used = round(stor_used_tb, 3)
        hc_cpu_pct_cap = round(100.0 * hc_cpu_used / hc_cpu_cap, 1) if hc_cpu_cap else 0.0
        hc_mem_pct_cap = round(100.0 * hc_mem_used / hc_mem_cap, 1) if hc_mem_cap else 0.0
        avg30 = DatabaseService._normalize_avg30_row(hc_avg30)
        hc_cpu_pct = round(float(avg30[0] or 0), 1) if (avg30[0] or avg30[2]) else hc_cpu_pct_cap
        hc_mem_pct = round(float(avg30[1] or 0), 1) if (avg30[1] or avg30[3]) else hc_mem_pct_cap
        hc_cpu_pct_max = round(float(avg30[2] or 0), 1)
        hc_mem_pct_max = round(float(avg30[3] or 0), 1)
        hc_cpu_pct_min = round(float(avg30[4] or 0), 1)
        hc_mem_pct_min = round(float(avg30[5] or 0), 1)
        if hc_cpu_pct_max <= 0 and hc_cpu_pct_cap > 0:
            hc_cpu_pct = hc_cpu_pct_cap
        if hc_mem_pct_max <= 0 and hc_mem_pct_cap > 0:
            hc_mem_pct = hc_mem_pct_cap
        section = self._apply_cpu_overalloc_flags({
            "hosts": hc_hosts,
            "vms": hc_vms,
            "cpu_cap": hc_cpu_cap,
            "cpu_used": hc_cpu_used,
            "cpu_pct": hc_cpu_pct,
            "cpu_pct_max": hc_cpu_pct_max,
            "cpu_pct_min": hc_cpu_pct_min,
            "cpu_util_pct": hc_cpu_pct,
            "cpu_util_pct_max": hc_cpu_pct_max if hc_cpu_pct_max > 0 else hc_cpu_pct_cap,
            "mem_cap": hc_mem_cap,
            "mem_used": hc_mem_used,
            "mem_pct": hc_mem_pct,
            "mem_pct_max": hc_mem_pct_max,
            "mem_pct_min": hc_mem_pct_min,
            "mem_util_pct": hc_mem_pct,
            "mem_util_pct_max": hc_mem_pct_max if hc_mem_pct_max > 0 else hc_mem_pct_cap,
            "stor_cap": hc_stor_cap,
            "stor_used": hc_stor_used,
            **storage_vm,
            "unit_prices": unit_prices,
            "sellable_multiplier": 3.3,
        })
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    section = self._apply_hyperconv_mem_stats(
                        section, cur, dc_wc, dc_code, start_ts, end_ts,
                        cluster_filter=selected_clusters,
                    )
        except OperationalError:
            pass
        self._set_compute_cached(cache_key, section)
        return section

    # ------------------------------------------------------------------
    # Host-level compute rows (DC view Hosts panel + host-based sellable)
    # ------------------------------------------------------------------

    @staticmethod
    def _host_mem_peak_map(rows) -> dict[str, tuple[float, float, float]]:
        """Index per-host RAM peak rows by short hostname."""
        out: dict[str, tuple[float, float, float]] = {}
        for r in rows or []:
            if not r or not r[0]:
                continue
            key = str(r[0]).strip().lower().split(".")[0]
            out[key] = (float(r[1] or 0), float(r[2] or 0), float(r[3] or 0))
        return out

    _BYTES_PER_GB = 1024 ** 3

    def _build_km_storage_context(self, dc_code: str, time_range: dict) -> dict[str, Any]:
        """Build host → datastore mount index from get_datastore_mapping."""
        mapping = self.get_datastore_mapping(dc_code, time_range)
        host_mounts: dict[str, list[dict[str, Any]]] = {}
        for ds in mapping.get("datastores") or []:
            moid = str(ds.get("datastore_moid") or "")
            if not moid:
                continue
            free_gb = float(ds.get("free_bytes") or 0) / self._BYTES_PER_GB
            cap_gb = float(ds.get("capacity_bytes") or 0) / self._BYTES_PER_GB
            used_gb = float(ds.get("used_bytes") or 0) / self._BYTES_PER_GB
            shared = bool(ds.get("multiple_host_access")) or int(ds.get("host_count") or 0) > 1
            backing = ds.get("backing") or (
                "ibm" if "ibm" in str(ds.get("datastore_name") or "").lower() else "intel"
            )
            mount_info = {
                "datastore_moid": moid,
                "moid": moid,
                "name": ds.get("datastore_name") or moid,
                "backing": backing,
                "cap_gb": round(cap_gb, 2),
                "free_gb": round(free_gb, 2),
                "used_gb": round(used_gb, 2),
                "used_pct": float(ds.get("used_percent") or 0.0),
                "shared": shared,
            }
            for host_entry in ds.get("hosts") or []:
                hname = str(host_entry.get("host_name") or "").strip().lower().split(".")[0]
                if hname:
                    host_mounts.setdefault(hname, []).append(dict(mount_info))
        return {"host_mounts": host_mounts}

    @staticmethod
    def _apply_km_storage_to_host(payload: dict, ctx: dict[str, Any]) -> dict:
        """Attach KM datastore mount storage fields to a host row."""
        key = str(payload.get("host") or "").strip().lower().split(".")[0]
        mounts = (ctx.get("host_mounts") or {}).get(key) or []
        if not mounts:
            return payload
        cap = sum(float(m.get("cap_gb") or 0) for m in mounts)
        used = sum(float(m.get("used_gb") or 0) for m in mounts)
        exclusive_free = sum(float(m.get("free_gb") or 0) for m in mounts if not m.get("shared"))
        total_free = sum(float(m.get("free_gb") or 0) for m in mounts)
        used_pct = max((float(m.get("used_pct") or 0.0) for m in mounts), default=0.0)
        out = dict(payload)
        out["datastore_mounts"] = mounts
        out["stor_cap_gb"] = round(cap, 2)
        out["stor_used_gb"] = round(used, 2)
        out["stor_free_gb"] = round(total_free, 2)
        out["stor_exclusive_free_gb"] = round(exclusive_free, 2)
        out["stor_used_pct"] = round(used_pct, 1)
        return out

    @staticmethod
    def _apply_host_mem_peak(payload: dict, peak: tuple[float, float, float] | None) -> dict:
        if not peak:
            return payload
        used, cap, pct = peak
        if used <= 0 and cap <= 0:
            return payload
        out = dict(payload)
        out["mem_used_gb_peak"] = round(used, 2)
        out["mem_cap_gb_at_peak"] = round(cap, 2)
        out["mem_peak_util_pct"] = round(pct, 1)
        return out

    @staticmethod
    def _host_row_payload(
        *,
        host: str,
        cluster: str,
        cpu_cap_ghz: float,
        cpu_used_ghz: float,
        mem_cap_gb: float,
        mem_used_gb: float,
        alloc: dict | None,
        ghz_per_core: float | None = None,
        is_nutanix: bool = False,
    ) -> dict:
        """Normalize a single host record. Sales CPU rule: 1 vCPU = 1 GHz."""
        alloc = alloc or {}
        vcpu_total = float(alloc.get("vcpu_total") or 0)
        default_ghz = float(ghz_per_core or DEFAULT_HOST_CPU_GHZ)
        if is_nutanix:
            host_ghz = 1.0
        else:
            host_ghz = float(ghz_per_core or default_ghz)
        cpu_alloc_ghz = vcpu_total * 1.0
        cpu_alloc_ghz_physical = vcpu_total * host_ghz
        mem_alloc_gb = float(alloc.get("mem_alloc_gb") or 0)
        cap_cores = (cpu_cap_ghz / host_ghz) if host_ghz > 0 else 0.0
        return {
            "host": host,
            "cluster": cluster,
            "vm_count": int(alloc.get("vm_count") or 0),
            "cpu_cap_ghz": round(cpu_cap_ghz, 2),
            "cpu_used_ghz": round(cpu_used_ghz, 2),
            "cpu_used_pct": round(100.0 * cpu_used_ghz / cpu_cap_ghz, 1) if cpu_cap_ghz > 0 else 0.0,
            "cpu_alloc_ghz": round(cpu_alloc_ghz, 2),
            "cpu_alloc_ghz_physical": round(cpu_alloc_ghz_physical, 2),
            "cpu_alloc_pct": round(100.0 * cpu_alloc_ghz / cpu_cap_ghz, 1) if cpu_cap_ghz > 0 else 0.0,
            "ghz_per_core": round(host_ghz, 2),
            "cpu_cap_cores": round(cap_cores, 2),
            "mem_cap_gb": round(mem_cap_gb, 2),
            "mem_used_gb": round(mem_used_gb, 2),
            "mem_used_pct": round(100.0 * mem_used_gb / mem_cap_gb, 1) if mem_cap_gb > 0 else 0.0,
            "mem_alloc_gb": round(mem_alloc_gb, 2),
            "mem_alloc_pct": round(100.0 * mem_alloc_gb / mem_cap_gb, 1) if mem_cap_gb > 0 else 0.0,
            "stor_provisioned_gb": round(float(alloc.get("stor_provisioned_gb") or 0), 2),
            "stor_used_gb": round(float(alloc.get("stor_used_gb") or 0), 2),
        }

    @staticmethod
    def _host_alloc_map(rows) -> dict[str, dict]:
        """Index per-host VM allocation rows by short hostname (lowercase, no domain)."""
        out: dict[str, dict] = {}
        for r in rows or []:
            if not r or not r[0]:
                continue
            key = str(r[0]).strip().lower().split(".")[0]
            out[key] = {
                "vm_count": int(r[1] or 0),
                "vcpu_total": float(r[2] or 0),
                "mem_alloc_gb": float(r[3] or 0),
                "stor_provisioned_gb": float(r[4] or 0),
                "stor_used_gb": float(r[5] or 0),
            }
        return out

    @staticmethod
    def _slice_host_rows_payload(full: dict | None, selected_clusters: list[str] | None) -> dict:
        """Filter a full-DC host payload to selected clusters (in-process, no SQL)."""
        hosts = (full or {}).get("hosts") or []
        if not selected_clusters:
            return finalize_host_payload({"hosts": list(hosts), "host_count": len(hosts)})
        wanted = set(selected_clusters)
        filtered = [h for h in hosts if h.get("cluster") in wanted]
        return finalize_host_payload({"hosts": filtered, "host_count": len(filtered)})

    def _fetch_classic_host_rows_all(self, dc_code: str, time_range: dict) -> dict:
        """Load all Classic (KM) hosts for a DC/time range (no cluster SQL filter)."""
        start_ts, end_ts = time_range_to_bounds(time_range)
        dc_wc = f"%{dc_code}%"
        empty_clusters: list[str] = []
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    host_rows = self._run_rows(
                        cur,
                        vq.CLASSIC_HOST_ROWS,
                        (dc_wc, empty_clusters, empty_clusters, start_ts, end_ts),
                    )
                    alloc_rows = self._run_rows(
                        cur,
                        vq.CLASSIC_HOST_VM_ALLOCATION,
                        (dc_wc, start_ts, end_ts, empty_clusters, empty_clusters),
                    )
                    peak_rows = self._run_rows(
                        cur,
                        vq.CLASSIC_HOST_MEM_PEAK,
                        (dc_wc, empty_clusters, empty_clusters, start_ts, end_ts),
                    )
                    host_map = self._load_host_ghz_map(cur)
        except OperationalError as exc:
            logger.error("DB unavailable for get_classic_host_rows(%s): %s", dc_code, exc)
            return finalize_host_payload({"hosts": [], "host_count": 0})

        alloc_map = self._host_alloc_map(alloc_rows)
        peak_map = self._host_mem_peak_map(peak_rows)
        storage_ctx = self._build_km_storage_context(dc_code, time_range)
        default_ghz = self._get_default_host_cpu_ghz()
        hosts = []
        for r in host_rows or []:
            host_name = str(r[0] or "").strip()
            if not host_name:
                continue
            ghz, _ = resolve_host_ghz(host_name, host_map, default_ghz=default_ghz)
            key = host_name.lower().split(".")[0]
            payload = self._host_row_payload(
                host=host_name,
                cluster=str(r[1] or ""),
                cpu_cap_ghz=float(r[2] or 0),
                cpu_used_ghz=float(r[3] or 0),
                mem_cap_gb=float(r[4] or 0),
                mem_used_gb=float(r[5] or 0),
                alloc=alloc_map.get(key),
                ghz_per_core=ghz,
            )
            payload = self._apply_host_mem_peak(payload, peak_map.get(key))
            payload = self._apply_km_storage_to_host(payload, storage_ctx)
            hosts.append(payload)
        hosts.sort(key=lambda h: (h["cluster"], h["host"]))
        return finalize_host_payload({"hosts": hosts, "host_count": len(hosts)})

    def get_classic_host_rows(
        self, dc_code: str, selected_clusters: list[str] | None = None, time_range: dict | None = None
    ) -> dict:
        """Per-host compute capacity/usage/allocation for Classic (KM) clusters.

        Source: vmhost_metrics (capacity/usage) + vm_metrics grouped by vmhost
        (sales allocation, 1 vCPU = 1 GHz). Full DC list cached once per dc/time;
        cluster subset is sliced in-process (P8 mirror).
        """
        tr = time_range or default_time_range()
        cache_key = f"classic_hosts_all:{dc_code}:{tr.get('start','')}:{tr.get('end','')}"
        cached_val = cache.get(cache_key)
        if cached_val is None:
            cached_val = cache.run_singleflight(
                cache_key, lambda: self._fetch_classic_host_rows_all(dc_code, tr)
            )
        clusters = sorted(c for c in (selected_clusters or []) if c)
        return self._slice_host_rows_payload(cached_val, clusters or None)

    def _fetch_hyperconv_host_rows_all(self, dc_code: str, time_range: dict) -> dict:
        """Load all Hyperconverged hosts for a DC/time range (no cluster SQL filter)."""
        start_ts, end_ts = time_range_to_bounds(time_range)
        empty_clusters: list[str] = []
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    host_rows = self._run_rows(
                        cur,
                        nq.NUTANIX_HOST_ROWS,
                        (dc_code, empty_clusters, empty_clusters, start_ts, end_ts),
                    )
                    alloc_rows = self._run_rows(
                        cur,
                        nq.NUTANIX_HOST_VM_ALLOCATION,
                        (dc_code, empty_clusters, empty_clusters, start_ts, end_ts, start_ts, end_ts),
                    )
                    peak_rows = self._run_rows(
                        cur,
                        nq.NUTANIX_HOST_MEM_PEAK,
                        (dc_code, empty_clusters, empty_clusters, start_ts, end_ts),
                    )
                    host_map = self._load_host_ghz_map(cur)
        except OperationalError as exc:
            logger.error("DB unavailable for get_hyperconv_host_rows(%s): %s", dc_code, exc)
            return finalize_host_payload({"hosts": [], "host_count": 0})

        _hz_per_ghz = 1_000_000_000
        _bytes_per_gb = 1024 ** 3
        alloc_map = self._host_alloc_map(alloc_rows)
        peak_map = self._host_mem_peak_map(peak_rows)
        default_ghz = self._get_default_host_cpu_ghz()
        hosts = []
        for r in host_rows or []:
            host_name = str(r[0] or "").strip()
            if not host_name:
                continue
            alloc = alloc_map.get(host_name.lower().split(".")[0]) or {}
            ghz, _ = resolve_host_ghz(host_name, host_map, default_ghz=default_ghz)
            key = host_name.lower().split(".")[0]
            payload = self._host_row_payload(
                host=host_name,
                cluster=str(r[1] or ""),
                cpu_cap_ghz=float(r[2] or 0) / _hz_per_ghz,
                cpu_used_ghz=float(r[3] or 0) / _hz_per_ghz,
                mem_cap_gb=float(r[4] or 0) / _bytes_per_gb,
                mem_used_gb=float(r[5] or 0) / _bytes_per_gb,
                alloc=alloc,
                ghz_per_core=ghz,
                is_nutanix=True,
            )
            payload["stor_cap_gb"] = round(float(r[6] or 0) / _bytes_per_gb, 2)
            payload["stor_used_host_gb"] = round(float(r[7] or 0) / _bytes_per_gb, 2)
            if payload["vm_count"] == 0:
                payload["vm_count"] = int(r[8] or 0)
            payload = self._apply_host_mem_peak(payload, peak_map.get(key))
            stor_cap = float(payload.get("stor_cap_gb") or 0)
            stor_used = float(payload.get("stor_used_host_gb") or 0)
            if stor_cap > 0:
                payload["stor_used_pct"] = round(100.0 * stor_used / stor_cap, 1)
                payload["stor_free_gb"] = round(max(stor_cap - stor_used, 0.0), 2)
            hosts.append(payload)
        hosts.sort(key=lambda h: (h["cluster"], h["host"]))
        return finalize_host_payload({"hosts": hosts, "host_count": len(hosts)})

    def get_hyperconv_host_rows(
        self, dc_code: str, selected_clusters: list[str] | None = None, time_range: dict | None = None
    ) -> dict:
        """Per-host compute capacity/usage/allocation for Hyperconverged (Nutanix) clusters.

        Source: nutanix_host_metrics (capacity/usage, Hz/bytes converted here)
        + nutanix_vm_metrics grouped by host_name (sales allocation, 1 vCPU = 1 GHz).
        Full DC list cached once per dc/time; cluster subset sliced in-process (P8 mirror).
        """
        tr = time_range or default_time_range()
        cache_key = f"hyperconv_hosts_all:{dc_code}:{tr.get('start','')}:{tr.get('end','')}"
        cached_val = cache.get(cache_key)
        if cached_val is None:
            cached_val = cache.run_singleflight(
                cache_key, lambda: self._fetch_hyperconv_host_rows_all(dc_code, tr)
            )
        clusters = sorted(c for c in (selected_clusters or []) if c)
        return self._slice_host_rows_payload(cached_val, clusters or None)

    # ------------------------------------------------------------------
    # Unit normalization & aggregation (shared by single + batch paths)
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_avg30_row(row) -> tuple:
        """Return (cpu_avg, mem_avg, cpu_max, mem_max, cpu_min, mem_min) for cluster_metrics utilization."""
        if not row:
            return (0, 0, 0, 0, 0, 0)
        if len(row) >= 6:
            return (row[0], row[1], row[2], row[3], row[4], row[5])
        if len(row) >= 4:
            # Legacy 4-column rows: approximate min with avg
            return (row[0], row[1], row[2], row[3], row[0], row[1])
        if len(row) >= 2:
            a, b = row[0], row[1]
            return (a, b, a, b, a, b)
        return (0, 0, 0, 0, 0, 0)

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
        power_storage=None,
        classic_row=None,
        classic_avg30=None,
        hyperconv_row=None,
        hyperconv_avg30=None,
        classic_storage_vm=None,
        hyperconv_storage_vm=None,
        classic_mem_peak=None,
        hyperconv_mem_peak=None,
        classic_unit_prices=None,
        hyperconv_unit_prices=None,
        power_unit_prices=None,
        sellable_multiplier: float = 3.3,
        dc_description: str = "",
    ) -> dict:
        """Apply unit normalization and build the standard DC detail dictionary.

        classic_row / hyperconv_row — rows from CLASSIC_METRICS / HYPERCONV_METRICS:
            (hosts, vms, cpu_cap_ghz, cpu_used_ghz, mem_cap_gb, mem_used_gb, stor_cap_gb, stor_used_gb)
        classic_avg30 / hyperconv_avg30 — rows from CLASSIC_AVG30 / HYPERCONV_AVG30:
            (cpu_avg_pct, mem_avg_pct, cpu_max_pct, mem_max_pct, cpu_min_pct, mem_min_pct)
        """
        nutanix_mem     = nutanix_mem     or (0, 0)
        nutanix_storage = nutanix_storage or (0, 0)
        nutanix_cpu     = nutanix_cpu     or (0, 0)
        vmware_counts   = vmware_counts   or (0, 0, 0)
        vmware_mem      = vmware_mem      or (0, 0)
        vmware_storage  = vmware_storage  or (0, 0)
        vmware_cpu      = vmware_cpu      or (0, 0)
        power_mem       = power_mem       or (0, 0, 0)
        power_cpu       = power_cpu       or (0, 0, 0, 0)
        classic_row     = classic_row     or (0,) * 8
        classic_avg30   = DatabaseService._normalize_avg30_row(classic_avg30)
        hyperconv_row   = hyperconv_row   or (0,) * 8
        hyperconv_avg30 = DatabaseService._normalize_avg30_row(hyperconv_avg30)

        # Memory → GB (coerce to float for DB Decimal)
        n_mem_cap_gb  = float(nutanix_mem[0] or 0) * 1024
        n_mem_used_gb = float(nutanix_mem[1] or 0) * 1024
        v_mem_cap_gb  = float(vmware_mem[0] or 0)
        v_mem_used_gb = float(vmware_mem[1] or 0)

        # Storage → TB (nutanix_cluster_metrics: bytes → TB; VMware: query returns stor in scaled GB, /1024 → TB)
        _bytes_per_tb = 1024**4
        n_stor_cap_tb  = float(nutanix_storage[0] or 0) / _bytes_per_tb
        n_stor_used_tb = float(nutanix_storage[1] or 0) / _bytes_per_tb
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
        if cl_cpu_pct == 0.0 and cl_cpu_cap > 0:
            cl_cpu_pct = round(100.0 * cl_cpu_used / cl_cpu_cap, 1)
        if cl_mem_pct == 0.0 and cl_mem_cap > 0:
            cl_mem_pct = round(100.0 * cl_mem_used / cl_mem_cap, 1)
        cl_cpu_pct_max = round(float(classic_avg30[2] or 0), 1)
        cl_mem_pct_max = round(float(classic_avg30[3] or 0), 1)
        cl_cpu_pct_min = round(float(classic_avg30[4] or 0), 1)
        cl_mem_pct_min = round(float(classic_avg30[5] or 0), 1)
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
        if hc_cpu_pct == 0.0 and hc_cpu_cap > 0:
            hc_cpu_pct = round(100.0 * hc_cpu_used / hc_cpu_cap, 1)
        if hc_mem_pct == 0.0 and hc_mem_cap > 0:
            hc_mem_pct = round(100.0 * hc_mem_used / hc_mem_cap, 1)
        hc_cpu_pct_max = round(float(hyperconv_avg30[2] or 0), 1)
        hc_mem_pct_max = round(float(hyperconv_avg30[3] or 0), 1)
        hc_cpu_pct_min = round(float(hyperconv_avg30[4] or 0), 1)
        hc_mem_pct_min = round(float(hyperconv_avg30[5] or 0), 1)
        # Storage from Nutanix (already in TB from the nutanix query)
        hc_stor_cap  = round(n_stor_cap_tb, 3)
        hc_stor_used = round(n_stor_used_tb, 3)

        # Live snapshot utilisation (capacity-weighted "current usage"), used by the
        # Overview DC Summary table so it reconciles with the Datacenters cards, which
        # show the combined Intel snapshot (used_cpu_pct / used_ram_pct).
        #   - Classic    = KM VMware only (matches the classic compute capacity).
        #   - Hyperconv  = merged non-KM VMware + per-cluster Nutanix CPU/RAM fallback
        #     (hyperconv_row already includes Nutanix-only clusters; no DC-wide double-count).
        cl_cpu_pct_live = round(100.0 * cl_cpu_used / cl_cpu_cap, 1) if cl_cpu_cap > 0 else 0.0
        cl_mem_pct_live = round(100.0 * cl_mem_used / cl_mem_cap, 1) if cl_mem_cap > 0 else 0.0
        # hyperconv_row already includes per-cluster Nutanix CPU/RAM fallback — do not add DC-wide Nutanix again.
        hc_cpu_pct_live = round(100.0 * hc_cpu_used / hc_cpu_cap, 1) if hc_cpu_cap > 0 else 0.0
        hc_mem_pct_live = round(100.0 * hc_mem_used / hc_mem_cap, 1) if hc_mem_cap > 0 else 0.0

        desc = (dc_description or "").strip()
        _vm_alloc_defaults = {
            "stor_provisioned_gb": 0.0,
            "stor_actual_used_gb": 0.0,
            "cpu_alloc_ghz_vm": 0.0,
            "cpu_alloc_ghz_sales": 0.0,
            "mem_alloc_gb_vm": 0.0,
        }
        classic_section = DatabaseService._apply_cpu_overalloc_flags({
            "hosts": cl_hosts, "vms": cl_vms,
            "cpu_cap": cl_cpu_cap, "cpu_used": cl_cpu_used, "cpu_pct": cl_cpu_pct,
            "cpu_pct_max": cl_cpu_pct_max,
            "cpu_pct_min": cl_cpu_pct_min,
            "cpu_pct_live": cl_cpu_pct_live,
            "cpu_util_pct": cl_cpu_pct,
            "cpu_util_pct_max": cl_cpu_pct_max,
            "mem_cap": cl_mem_cap, "mem_used": cl_mem_used, "mem_pct": cl_mem_pct,
            "mem_pct_max": cl_mem_pct_max,
            "mem_pct_min": cl_mem_pct_min,
            "ram_pct_live": cl_mem_pct_live,
            "mem_util_pct": cl_mem_pct,
            "mem_util_pct_max": cl_mem_pct_max,
            "stor_cap": cl_stor_cap, "stor_used": cl_stor_used,
            **(classic_storage_vm or _vm_alloc_defaults),
            "unit_prices": classic_unit_prices or {"cpu_vcpu": 0.0, "ram_gb": 0.0, "storage_gb": 0.0},
            "sellable_multiplier": sellable_multiplier,
        })
        classic_section = DatabaseService._apply_mem_peak_raw(classic_section, classic_mem_peak)
        hyperconv_section = DatabaseService._apply_cpu_overalloc_flags({
            "hosts": hc_hosts, "vms": hc_vms,
            "cpu_cap": hc_cpu_cap, "cpu_used": hc_cpu_used, "cpu_pct": hc_cpu_pct,
            "cpu_pct_max": hc_cpu_pct_max,
            "cpu_pct_min": hc_cpu_pct_min,
            "cpu_pct_live": hc_cpu_pct_live,
            "cpu_util_pct": hc_cpu_pct,
            "cpu_util_pct_max": hc_cpu_pct_max,
            "mem_cap": hc_mem_cap, "mem_used": hc_mem_used, "mem_pct": hc_mem_pct,
            "mem_pct_max": hc_mem_pct_max,
            "mem_pct_min": hc_mem_pct_min,
            "ram_pct_live": hc_mem_pct_live,
            "mem_util_pct": hc_mem_pct,
            "mem_util_pct_max": hc_mem_pct_max,
            "stor_cap": hc_stor_cap, "stor_used": hc_stor_used,
            **(hyperconv_storage_vm or _vm_alloc_defaults),
            "unit_prices": hyperconv_unit_prices or {"cpu_vcpu": 0.0, "ram_gb": 0.0, "storage_gb": 0.0},
            "sellable_multiplier": sellable_multiplier,
        })
        hyperconv_section = DatabaseService._apply_mem_peak_raw(hyperconv_section, hyperconv_mem_peak)
        return {
            "meta": {
                "name": dc_code,
                "location": DC_LOCATIONS.get(dc_code, "Unknown Data Center"),
                "description": desc,
            },
            # Compute-type split (new) — used by dc_view tabs
            "classic": classic_section,
            "hyperconv": hyperconv_section,
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
                "cpu_total_procunits": round(float(power_cpu[0] or 0), 2),
                "cpu_total_cores": round(float(power_cpu[0] or 0) * 8.0, 2),
                "cpu_available_procunits": round(float(power_cpu[1] or 0), 2),
                "cpu_available_cores": round(float(power_cpu[1] or 0) * 8.0, 2),
                "cpu_used": round(float(power_cpu[2] or 0), 2),
                "cpu_assigned": round(float(power_cpu[3] or 0), 2),
                "memory_total": round(float(power_mem[0] or 0) / 1024.0, 2),
                "memory_available": round(float(power_mem[1] or 0) / 1024.0, 2),
                "memory_assigned": round(float(power_mem[2] or 0) / 1024.0, 2),
                "storage_cap_tb": round(float((power_storage or (0.0, 0.0))[0]), 3),
                "storage_used_tb": round(float((power_storage or (0.0, 0.0))[1]), 3),
                "unit_prices": power_unit_prices or {"cpu_vcpu": 0.0, "ram_gb": 0.0, "storage_gb": 0.0},
                "sellable_multiplier": sellable_multiplier,
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

    def _get_ibm_storage_single(self, cursor, pattern: str) -> tuple[float, float]:
        sql = """
WITH latest AS (
    SELECT storage_ip, MAX("timestamp") AS max_ts
    FROM public.raw_ibm_storage_system
    GROUP BY storage_ip
)
SELECT
    s.total_mdisk_capacity,
    s.total_used_capacity
FROM public.raw_ibm_storage_system s
JOIN latest l ON s.storage_ip = l.storage_ip AND s."timestamp" = l.max_ts
WHERE UPPER(s.name) LIKE UPPER(%s) OR UPPER(s.location) LIKE UPPER(%s)
"""
        rows = self._run_rows(cursor, sql, (pattern, pattern))
        cap_tb, used_tb = 0.0, 0.0
        def parse_capacity(val: str) -> float:
            if not val:
                return 0.0
            val = str(val).upper().strip()
            try:
                num = float(''.join(c for c in val if c.isdigit() or c == '.'))
                if 'GB' in val:
                    return num / 1024.0
                if 'MB' in val:
                    return num / (1024.0**2)
                if 'PB' in val:
                    return num * 1024.0
                return num
            except Exception:
                return 0.0

        for row in rows:
            if not row or len(row) < 2:
                continue
            cap_str, used_str = row
            cap_tb += parse_capacity(cap_str)
            used_tb += parse_capacity(used_str)
        return (cap_tb, used_tb)

    def _overlay_classic_datastore_storage(
        self,
        dc_code: str,
        time_range: dict | None,
        result: dict,
    ) -> dict:
        """Replace classic stor_* with KM datastore mapping totals (same as Storage tab)."""
        mapping = self.get_datastore_mapping(dc_code, time_range)
        datastores = mapping.get("datastores") or []
        if not datastores:
            return result
        cap_bytes = sum(int(d.get("capacity_bytes") or 0) for d in datastores)
        used_bytes = sum(int(d.get("used_bytes") or 0) for d in datastores)
        cap_tb = cap_bytes / (1024**4)
        used_tb = used_bytes / (1024**4)
        if cap_tb > 0 and isinstance(result.get("classic"), dict):
            result = dict(result)
            classic = dict(result["classic"])
            classic["stor_cap"] = round(cap_tb, 3)
            classic["stor_used"] = round(used_tb, 3)
            result["classic"] = classic
        return result

    def get_dc_details(self, dc_code: str, time_range: dict | None = None) -> dict:
        """Return full metrics dict for a single data center. Result is TTL-cached per time range."""
        tr = time_range or default_time_range()
        if tr.get("anchor_latest"):
            tr = self._smart_1h_tr(tr)
        start_ts, end_ts = time_range_to_bounds(tr)
        cache_key = f"dc_details:{dc_code}:{tr.get('start','')}:{tr.get('end','')}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return self._overlay_classic_datastore_storage(dc_code, tr, cached_val)

        def _fetch():
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    self._ensure_dc_description_map(cur)
                    dc_wc = f"%{dc_code}%"
                    classic_row = self.get_classic_metrics(
                        cur, dc_wc, start_ts, end_ts, dc_code=dc_code
                    )
                    ds_cap_gb, ds_used_gb = self._km_datastore_storage_gb(
                        cur, dc_code, start_ts, end_ts
                    )
                    classic_row = self._patch_classic_row_storage(
                        classic_row, ds_cap_gb, ds_used_gb
                    )
                    result = self._aggregate_dc(
                        dc_code,
                        dc_description=self._dc_description_map.get(dc_code, ""),
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
                        power_storage=self._get_ibm_storage_single(cur, f"%{dc_code}%"),
                        ibm_w=self.get_ibm_energy(cur, dc_wc, start_ts, end_ts),
                        vcenter_w=self.get_vcenter_energy(cur, dc_code, start_ts, end_ts),
                        ibm_kwh=self.get_ibm_kwh(cur, dc_wc, start_ts, end_ts),
                        vcenter_kwh=self.get_vcenter_kwh(cur, dc_code, start_ts, end_ts),
                        classic_row=classic_row,
                        classic_avg30=self.get_classic_avg30(
                            cur, dc_wc, start_ts, end_ts, dc_code=dc_code
                        ),
                        hyperconv_row=self.get_hyperconv_metrics(
                            cur, dc_wc, start_ts, end_ts, dc_code=dc_code
                        ),
                        hyperconv_avg30=self.get_hyperconv_avg30(
                            cur, dc_wc, start_ts, end_ts, dc_code=dc_code
                        ),
                        classic_storage_vm=self.get_classic_storage_vm(cur, dc_wc, start_ts, end_ts),
                        hyperconv_storage_vm=self.get_hyperconv_storage_vm(
                            cur, dc_code, start_ts, end_ts
                        ),
                        classic_mem_peak=self.get_classic_mem_peak_raw(
                            cur, dc_wc, start_ts, end_ts
                        ),
                        hyperconv_mem_peak=self.get_hyperconv_mem_peak_raw(
                            cur, dc_wc, dc_code, start_ts, end_ts
                        ),
                        classic_unit_prices=self.get_unit_prices_tl(cur, "klasik"),
                        hyperconv_unit_prices=self.get_unit_prices_tl(cur, "hyperconv"),
                        power_unit_prices=self.get_unit_prices_tl(cur, "power"),
                    )
                    result = dict(result)
                    classic = self._apply_classic_mem_stats(
                        dict(result.get("classic") or {}),
                        cur,
                        dc_wc,
                        start_ts,
                        end_ts,
                    )
                    hyperconv = self._apply_hyperconv_mem_stats(
                        dict(result.get("hyperconv") or {}),
                        cur,
                        dc_wc,
                        dc_code,
                        start_ts,
                        end_ts,
                    )
                    result["classic"] = classic
                    result["hyperconv"] = hyperconv
                    return result

        try:
            result = cache.run_singleflight(cache_key, _fetch)
            result = self._overlay_classic_datastore_storage(dc_code, tr, result)
            cache.set(cache_key, result)
            return result
        except OperationalError as exc:
            logger.error("DB unavailable for get_dc_details(%s): %s", dc_code, exc)
            return _EMPTY_DC(dc_code)

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
        virt_compute_batch_params = (
            dc_list,
            pattern_list,
            start_ts,
            end_ts,
            dc_list,
            pattern_list,
            start_ts,
            end_ts,
        )
        ibm_ts_params  = (start_ts, end_ts)

        nutanix_queries = [
            ("n_host",     nq.BATCH_HOST_COUNT,    nutanix_params),
            ("n_vm",       nq.BATCH_VM_COUNT,      nutanix_params),
            ("n_mem",      nq.BATCH_MEMORY,        nutanix_params),
            ("n_stor",     nq.BATCH_STORAGE,       (dc_list, pattern_list, start_ts, end_ts)),
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
            ("v_classic",       vcq.BATCH_CLASSIC_CPU_MEM_MERGED, virt_compute_batch_params),
            ("v_classic_avg",   vcq.BATCH_CLASSIC_AVG30_MERGED,  virt_compute_batch_params),
            ("v_hyperconv",     vcq.BATCH_HYPERCONV_CPU_MEM_MERGED, virt_compute_batch_params),
            ("v_hyperconv_avg", vcq.BATCH_HYPERCONV_AVG30_MERGED,   virt_compute_batch_params),
        ]
        ibm_queries = [
            ("ibm_host_raw",   iq.BATCH_RAW_HOST,   ibm_ts_params),
            ("ibm_vios_raw",   iq.BATCH_RAW_VIOS,   ibm_ts_params),
            ("ibm_lpar_raw",   iq.BATCH_RAW_LPAR,   ibm_ts_params),
            ("ibm_mem_raw",    iq.BATCH_RAW_MEMORY,  ibm_ts_params),
            ("ibm_cpu_raw",    iq.BATCH_RAW_CPU,     ibm_ts_params),
            ("ibm_storage_raw", """
WITH latest AS (
    SELECT storage_ip, MAX("timestamp") AS max_ts
    FROM public.raw_ibm_storage_system
    GROUP BY storage_ip
)
SELECT
    s.name,
    s.location,
    s.total_mdisk_capacity,
    s.total_used_capacity
FROM public.raw_ibm_storage_system s
JOIN latest l ON s.storage_ip = l.storage_ip AND s."timestamp" = l.max_ts
            """, ()),
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

        ibm_mem_hosts: dict[str, dict[str, list[tuple[float, float, float, object]]]] = {}
        for row in ibm_raw["ibm_mem_raw"]:
            if not row or len(row) < 5:
                continue
            server_name = row[0]
            dc = _extract_dc(server_name)
            if not dc:
                continue
            try:
                total_mem = float(row[1] or 0)
                avail_mem = float(row[2] or 0)
                assigned_mem = float(row[3] or 0)
            except (TypeError, ValueError):
                continue
            ts = row[4]
            dc_hosts = ibm_mem_hosts.setdefault(dc, {})
            dc_hosts.setdefault(server_name, []).append((total_mem, avail_mem, assigned_mem, ts))

        ibm_mem: dict[str, tuple] = {}
        for dc, hosts in ibm_mem_hosts.items():
            total_mb = 0.0
            avail_mb = 0.0
            assigned_mb = 0.0
            for server_name, samples in hosts.items():
                if not samples:
                    continue
                latest_total, latest_avail, latest_assigned, _ = max(samples, key=lambda v: v[3])
                total_mb += latest_total
                avail_mb += latest_avail
                assigned_mb += latest_assigned
            # Raw MB per DC; _aggregate_dc converts to GB for API consumers.
            ibm_mem[dc] = (total_mb, avail_mb, assigned_mb)

        ibm_cpu_hosts: dict[str, dict[str, list[tuple[float, float, float, float, object]]]] = {}
        for row in ibm_raw["ibm_cpu_raw"]:
            if not row or len(row) < 6:
                continue
            server_name = row[0]
            dc = _extract_dc(server_name)
            if not dc:
                continue
            try:
                tot_p = float(row[1] or 0)
                avail_p = float(row[2] or 0)
                used_p = float(row[3] or 0)
                assigned_p = float(row[4] or 0)
            except (TypeError, ValueError):
                continue
            ts = row[5]
            dc_hosts = ibm_cpu_hosts.setdefault(dc, {})
            dc_hosts.setdefault(server_name, []).append((tot_p, avail_p, used_p, assigned_p, ts))

        ibm_cpu_map: dict[str, tuple] = {}
        for dc, hosts in ibm_cpu_hosts.items():
            sum_tot = sum_avail = 0.0
            used_vals: list[float] = []
            assigned_vals: list[float] = []
            for _sn, samples in hosts.items():
                if not samples:
                    continue
                tpu, apu, u, a, _ts = max(samples, key=lambda v: v[4])
                sum_tot += tpu
                sum_avail += apu
                used_vals.append(u)
                assigned_vals.append(a)
            nu = len(used_vals) or 1
            na = len(assigned_vals) or 1
            ibm_cpu_map[dc] = (
                sum_tot,
                sum_avail,
                sum(used_vals) / nu,
                sum(assigned_vals) / na,
            )

        def _parse_capacity(val: str) -> float:
            if not val:
                return 0.0
            val = str(val).upper().strip()
            try:
                num = float(''.join(c for c in val if c.isdigit() or c == '.'))
                if 'GB' in val:
                    return num / 1024.0
                if 'MB' in val:
                    return num / (1024.0**2)
                if 'PB' in val:
                    return num * 1024.0
                return num
            except Exception:
                return 0.0


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

        ibm_storage_tb: dict[str, tuple[float, float]] = {}
        for row in ibm_raw.get("ibm_storage_raw", []):
            if not row or len(row) < 4:
                continue
            name_val, loc_val, cap_str, used_str = row
            dc = _extract_dc(f"{name_val or ''} {loc_val or ''}")
            if not dc:
                dc = _canonical_dc(name_val)
            if not dc:
                dc = _canonical_dc(loc_val)
            if dc:
                cap_tb = _parse_capacity(cap_str)
                used_tb = _parse_capacity(used_str)
                curr_cap, curr_used = ibm_storage_tb.get(dc, (0.0, 0.0))
                ibm_storage_tb[dc] = (curr_cap + cap_tb, curr_used + used_tb)

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

        # Fetch CRM unit prices once for all archs — these are global, not per-DC.
        # Required so the dc_details cache populated by this batch path includes Power TL.
        try:
            with self._get_connection() as _up_conn:
                with _up_conn.cursor() as _up_cur:
                    classic_up   = self.get_unit_prices_tl(_up_cur, "klasik")
                    hyperconv_up = self.get_unit_prices_tl(_up_cur, "hyperconv")
                    power_up     = self.get_unit_prices_tl(_up_cur, "power")
        except Exception as _exc:
            logger.warning("Batch unit_prices fetch failed: %s", _exc)
            classic_up = hyperconv_up = power_up = None

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
            power_mem_tup = ibm_mem.get(dc, (0.0, 0.0, 0.0))
            power_cpu_tup = ibm_cpu_map.get(dc, (0.0, 0.0, 0.0, 0.0))

            # Classic / Hyperconverged rows from cluster_metrics
            vcl_row  = v_classic.get(dc)
            vcla_row = v_classic_avg.get(dc)
            vhc_row  = v_hyperconv.get(dc)
            vhca_row = v_hyperconv_avg.get(dc)

            # Batch CLASSIC_METRICS: (dc_code, hosts, vms, cpu_cap, cpu_used, mem_cap, mem_used, stor_cap, stor_used)
            cl_data = (vcl_row[1], vcl_row[2], vcl_row[3], vcl_row[4], vcl_row[5], vcl_row[6], vcl_row[7], vcl_row[8]) if (vcl_row and len(vcl_row) > 8) else None
            # Batch CLASSIC_AVG30: (dc_code, cpu_avg, mem_avg, cpu_max, mem_max, cpu_min, mem_min)
            if vcla_row and len(vcla_row) >= 7:
                cl_avg = (
                    vcla_row[1],
                    vcla_row[2],
                    vcla_row[3],
                    vcla_row[4],
                    vcla_row[5],
                    vcla_row[6],
                )
            elif vcla_row and len(vcla_row) >= 5:
                cl_avg = (
                    vcla_row[1],
                    vcla_row[2],
                    vcla_row[3],
                    vcla_row[4],
                    vcla_row[1],
                    vcla_row[2],
                )
            elif vcla_row and len(vcla_row) > 2:
                cl_avg = (
                    vcla_row[1],
                    vcla_row[2],
                    vcla_row[1],
                    vcla_row[2],
                    vcla_row[1],
                    vcla_row[2],
                )
            else:
                cl_avg = None
            hc_data = (vhc_row[1], vhc_row[2], vhc_row[3], vhc_row[4], vhc_row[5], vhc_row[6], vhc_row[7], vhc_row[8]) if (vhc_row and len(vhc_row) > 8) else None
            if vhca_row and len(vhca_row) >= 7:
                hc_avg = (
                    vhca_row[1],
                    vhca_row[2],
                    vhca_row[3],
                    vhca_row[4],
                    vhca_row[5],
                    vhca_row[6],
                )
            elif vhca_row and len(vhca_row) >= 5:
                hc_avg = (
                    vhca_row[1],
                    vhca_row[2],
                    vhca_row[3],
                    vhca_row[4],
                    vhca_row[1],
                    vhca_row[2],
                )
            elif vhca_row and len(vhca_row) > 2:
                hc_avg = (
                    vhca_row[1],
                    vhca_row[2],
                    vhca_row[1],
                    vhca_row[2],
                    vhca_row[1],
                    vhca_row[2],
                )
            else:
                hc_avg = None

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
                power_storage=ibm_storage_tb.get(dc, (0.0, 0.0)),
                ibm_w=ibm_e.get(dc, 0.0),
                vcenter_w=vctr_e.get(dc, 0.0),
                ibm_kwh=ibm_kwh_m.get(dc, 0.0),
                vcenter_kwh=vctr_kwh_m.get(dc, 0.0),
                classic_row=cl_data,
                classic_avg30=cl_avg,
                hyperconv_row=hc_data,
                hyperconv_avg30=hc_avg,
                classic_unit_prices=classic_up,
                hyperconv_unit_prices=hyperconv_up,
                power_unit_prices=power_up,
                dc_description=self._dc_description_map.get(dc, ""),
            )

        # VM-level allocation (storage + CPU/RAM) is not batched; enrich per DC.
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    for dc in dc_list:
                        dc_wc = f"%{dc}%"
                        if dc not in results:
                            continue
                        classic_vm = self.get_classic_storage_vm(cur, dc_wc, start_ts, end_ts)
                        hyper_vm = self.get_hyperconv_storage_vm(cur, dc, start_ts, end_ts)
                        cl_peak = self.get_classic_mem_peak_raw(cur, dc_wc, start_ts, end_ts)
                        hc_peak = self.get_hyperconv_mem_peak_raw(
                            cur, dc_wc, dc, start_ts, end_ts
                        )
                        results[dc]["classic"].update(classic_vm)
                        results[dc]["hyperconv"].update(hyper_vm)
                        results[dc]["classic"] = self._apply_cpu_overalloc_flags(results[dc]["classic"])
                        results[dc]["hyperconv"] = self._apply_cpu_overalloc_flags(results[dc]["hyperconv"])
                        results[dc]["classic"] = self._apply_mem_peak_raw(results[dc]["classic"], cl_peak)
                        results[dc]["hyperconv"] = self._apply_mem_peak_raw(
                            results[dc]["hyperconv"], hc_peak
                        )
        except OperationalError as exc:
            logger.warning("Batch VM allocation enrichment failed: %s", exc)

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
        if tr.get("anchor_latest"):
            tr = self._smart_1h_tr(tr)
        cache_key = f"all_dc_summary:{tr.get('start','')}:{tr.get('end','')}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        result = cache.run_singleflight(cache_key, lambda: self._rebuild_summary(tr))
        return result

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

            # Architecture-specific CPU/RAM/Storage utilisation for DC Summary.
            # Use the live snapshot (capacity-weighted, Nutanix-inclusive for hyperconv)
            # so the Overview table reconciles with the Datacenters cards. Fall back to
            # the legacy avg field for safety if *_live is absent.
            classic_cpu_pct = float(classic.get("cpu_pct_live", classic.get("cpu_pct", 0)) or 0)
            classic_ram_pct = float(classic.get("ram_pct_live", classic.get("mem_pct", 0)) or 0)
            classic_stor_cap = float(classic.get("stor_cap", 0) or 0)
            classic_stor_used = float(classic.get("stor_used", 0) or 0)
            classic_stor_pct = (classic_stor_used / classic_stor_cap * 100.0) if classic_stor_cap > 0 else 0.0

            hyperconv_cpu_pct = float(hyperconv.get("cpu_pct_live", hyperconv.get("cpu_pct", 0)) or 0)
            hyperconv_ram_pct = float(hyperconv.get("ram_pct_live", hyperconv.get("mem_pct", 0)) or 0)
            hyperconv_stor_cap = float(hyperconv.get("stor_cap", 0) or 0)
            hyperconv_stor_used = float(hyperconv.get("stor_used", 0) or 0)
            hyperconv_stor_pct = (hyperconv_stor_used / hyperconv_stor_cap * 100.0) if hyperconv_stor_cap > 0 else 0.0

            ibm_mem_total = float(power.get("memory_total", 0) or 0)
            ibm_mem_assigned = float(power.get("memory_assigned", 0) or 0)
            ibm_cpu_used = float(power.get("cpu_used", 0) or 0)
            ibm_cpu_assigned = float(power.get("cpu_assigned", 0) or 0)
            ibm_mem_pct = (ibm_mem_assigned / ibm_mem_total * 100.0) if ibm_mem_total > 0 else 0.0
            ibm_cpu_pct = (ibm_cpu_used / ibm_cpu_assigned * 100.0) if ibm_cpu_assigned > 0 else 0.0
            ibm_stor_cap = float(power.get("storage_cap_tb", 0) or 0)
            ibm_stor_used = float(power.get("storage_used_tb", 0) or 0)
            ibm_stor_pct = (ibm_stor_used / ibm_stor_cap * 100.0) if ibm_stor_cap > 0 else 0.0

            summary_list.append({
                "id": dc,
                "name": dc,
                "location": d["meta"]["location"],
                "description": (d.get("meta") or {}).get("description") or "",
                "site_name": self._dc_site_map.get(dc),
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
                    "arch_usage": {
                        "classic": {
                            "cpu_pct": round(classic_cpu_pct, 1),
                            "cpu_pct_avg": round(classic_cpu_pct, 1),
                            "cpu_pct_max": round(float(classic.get("cpu_pct_max", 0) or 0), 1),
                            "cpu_pct_min": round(float(classic.get("cpu_pct_min", 0) or 0), 1),
                            "ram_pct": round(classic_ram_pct, 1),
                            "ram_pct_avg": round(classic_ram_pct, 1),
                            "ram_pct_max": round(float(classic.get("mem_pct_max", 0) or 0), 1),
                            "ram_pct_min": round(float(classic.get("mem_pct_min", 0) or 0), 1),
                            "disk_pct": round(classic_stor_pct, 1),
                        },
                        "hyperconv": {
                            "cpu_pct": round(hyperconv_cpu_pct, 1),
                            "cpu_pct_avg": round(hyperconv_cpu_pct, 1),
                            "cpu_pct_max": round(float(hyperconv.get("cpu_pct_max", 0) or 0), 1),
                            "cpu_pct_min": round(float(hyperconv.get("cpu_pct_min", 0) or 0), 1),
                            "ram_pct": round(hyperconv_ram_pct, 1),
                            "ram_pct_avg": round(hyperconv_ram_pct, 1),
                            "ram_pct_max": round(float(hyperconv.get("mem_pct_max", 0) or 0), 1),
                            "ram_pct_min": round(float(hyperconv.get("mem_pct_min", 0) or 0), 1),
                            "disk_pct": round(hyperconv_stor_pct, 1),
                        },
                        "ibm": {
                            "cpu_pct": round(ibm_cpu_pct, 1),
                            "ram_pct": round(ibm_mem_pct, 1),
                            "disk_pct": round(ibm_stor_pct, 1),
                        },
                    },
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
        # Architecture-specific totals for home Resource Usage tabs
        classic_totals = {"cpu_cap": 0.0, "cpu_used": 0.0, "mem_cap": 0.0, "mem_used": 0.0, "stor_cap": 0.0, "stor_used": 0.0}
        hyperconv_totals = {"cpu_cap": 0.0, "cpu_used": 0.0, "mem_cap": 0.0, "mem_used": 0.0, "stor_cap": 0.0, "stor_used": 0.0}
        ibm_totals = {
            "mem_total": 0.0,
            "mem_available": 0.0,
            "mem_assigned": 0.0,
            "cpu_total_procunits": 0.0,
            "cpu_available_procunits": 0.0,
            "cpu_used": 0.0,
            "cpu_assigned": 0.0,
            "stor_cap": 0.0,
            "stor_used": 0.0,
        }
        for d in all_dc_data.values():
            c = d.get("classic", {})
            classic_totals["cpu_cap"] += float(c.get("cpu_cap", 0) or 0)
            classic_totals["cpu_used"] += float(c.get("cpu_used", 0) or 0)
            classic_totals["mem_cap"] += float(c.get("mem_cap", 0) or 0)
            classic_totals["mem_used"] += float(c.get("mem_used", 0) or 0)
            classic_totals["stor_cap"] += float(c.get("stor_cap", 0) or 0)
            classic_totals["stor_used"] += float(c.get("stor_used", 0) or 0)
            h = d.get("hyperconv", {})
            hyperconv_totals["cpu_cap"] += float(h.get("cpu_cap", 0) or 0)
            hyperconv_totals["cpu_used"] += float(h.get("cpu_used", 0) or 0)
            hyperconv_totals["mem_cap"] += float(h.get("mem_cap", 0) or 0)
            hyperconv_totals["mem_used"] += float(h.get("mem_used", 0) or 0)
            hyperconv_totals["stor_cap"] += float(h.get("stor_cap", 0) or 0)
            hyperconv_totals["stor_used"] += float(h.get("stor_used", 0) or 0)
            pw = d.get("power", {})
            ibm_totals["mem_total"] += float(pw.get("memory_total", 0) or 0)
            ibm_totals["mem_available"] += float(pw.get("memory_available", 0) or 0)
            ibm_totals["mem_assigned"] += float(pw.get("memory_assigned", 0) or 0)
            ibm_totals["cpu_total_procunits"] += float(pw.get("cpu_total_procunits", 0) or 0)
            ibm_totals["cpu_available_procunits"] += float(pw.get("cpu_available_procunits", 0) or 0)
            ibm_totals["cpu_used"] += float(pw.get("cpu_used", 0) or 0)
            ibm_totals["cpu_assigned"] += float(pw.get("cpu_assigned", 0) or 0)
            ibm_totals["stor_cap"] += float(pw.get("storage_cap_tb", 0) or 0)
            ibm_totals["stor_used"] += float(pw.get("storage_used_tb", 0) or 0)
        for tot in (classic_totals, hyperconv_totals):
            tot["cpu_cap"] = round(tot["cpu_cap"], 2)
            tot["cpu_used"] = round(tot["cpu_used"], 2)
            tot["mem_cap"] = round(tot["mem_cap"], 2)
            tot["mem_used"] = round(tot["mem_used"], 2)
            tot["stor_cap"] = round(tot["stor_cap"], 2)
            tot["stor_used"] = round(tot["stor_used"], 2)
        ibm_totals["mem_total"] = round(ibm_totals["mem_total"], 2)
        ibm_totals["mem_available"] = round(ibm_totals["mem_available"], 2)
        ibm_totals["mem_assigned"] = round(ibm_totals["mem_assigned"], 2)
        ibm_totals["cpu_total_procunits"] = round(ibm_totals["cpu_total_procunits"], 2)
        ibm_totals["cpu_available_procunits"] = round(ibm_totals["cpu_available_procunits"], 2)
        ibm_totals["cpu_used"] = round(ibm_totals["cpu_used"], 2)
        ibm_totals["cpu_assigned"] = round(ibm_totals["cpu_assigned"], 2)
        ibm_totals["stor_cap"] = round(ibm_totals["stor_cap"], 2)
        ibm_totals["stor_used"] = round(ibm_totals["stor_used"], 2)
        range_suffix = f"{tr.get('start','')}:{tr.get('end','')}"
        cache.set(f"global_dashboard:{range_suffix}", {
            "overview": overview,
            "platforms": {
                "nutanix": {"hosts": nutanix_h, "vms": nutanix_v},
                "vmware": {"clusters": vmware_c, "hosts": vmware_h, "vms": vmware_v},
                "ibm": {"hosts": ibm_h, "vios": ibm_v, "lpars": ibm_l},
            },
            "energy_breakdown": {"ibm_kw": round(ei, 2), "vcenter_kw": round(ev, 2)},
            "classic_totals": classic_totals,
            "hyperconv_totals": hyperconv_totals,
            "ibm_totals": ibm_totals,
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
        if tr.get("anchor_latest"):
            tr = self._smart_1h_tr(tr)
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

    def _get_latest_data_ts(self) -> datetime | None:
        """Most-recent timestamp in vm_metrics. Cached 60 s.

        Used to anchor the "1H" preset to actual data instead of wall-clock —
        a strict last-60-minutes window often misses the next ingestion cycle
        and renders empty even when data is fresh.
        """
        cached = cache.get("latest_vm_ts")
        if cached:
            try:
                return datetime.fromisoformat(str(cached).replace("Z", "+00:00"))
            except Exception:
                pass
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute('SELECT MAX("timestamp") FROM public.vm_metrics')
                    row = cur.fetchone()
                    if row and row[0]:
                        ts = row[0]
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=timezone.utc)
                        cache.set("latest_vm_ts", ts.isoformat(), ttl=60)
                        return ts
        except Exception as exc:
            logger.warning("latest vm_metrics timestamp lookup failed: %s", exc)
        return None

    _RELATIVE_PRESET_OFFSETS = {
        "1h": timedelta(hours=1),
        "1d": timedelta(days=1),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
        "1m": timedelta(days=30),
        "2m": timedelta(days=60),
        "3m": timedelta(days=90),
        "6m": timedelta(days=180),
    }

    def _smart_1h_tr(self, tr: dict | None) -> dict:
        """Anchor every relative preset (1h/1d/7d/30d/1m/2m/3m/6m) to the most
        recent ingested timestamp instead of wall-clock. Without this, a window
        like "last 7 days" returns nothing whenever ingestion is more than a
        couple of days behind real time — which is exactly what was happening
        when the customer reported '1H' (and then 7D) showing all zeros."""
        if not tr:
            return default_time_range()
        preset = tr.get("preset")
        offset = self._RELATIVE_PRESET_OFFSETS.get(preset)
        if offset is None:  # custom or unknown preset → pass through
            return tr
        latest = self._get_latest_data_ts()
        if not latest:
            return tr
        end = latest
        start = end - offset
        if preset == "1h":
            return {
                "start": start.strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                "end": end.strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                "preset": preset,
            }
        # Day-precision presets keep date-only strings so downstream SQL
        # `BETWEEN 00:00:00 AND 23:59:59` expansion still applies.
        return {
            "start": start.date().isoformat(),
            "end": end.date().isoformat(),
            "preset": preset,
        }

    def get_global_dashboard(self, time_range: dict | None = None) -> dict:
        """Return global overview + platform breakdown for the given time range."""
        tr = time_range or default_time_range()
        if tr.get("anchor_latest"):
            tr = self._smart_1h_tr(tr)
        range_suffix = f"{tr.get('start','')}:{tr.get('end','')}"
        cached = cache.get(f"global_dashboard:{range_suffix}")
        if cached is not None:
            return cached
        self.get_all_datacenters_summary(tr)
        empty_totals = {"cpu_cap": 0.0, "cpu_used": 0.0, "mem_cap": 0.0, "mem_used": 0.0, "stor_cap": 0.0, "stor_used": 0.0}
        empty_ibm = {
            "mem_total": 0.0,
            "mem_available": 0.0,
            "mem_assigned": 0.0,
            "cpu_total_procunits": 0.0,
            "cpu_available_procunits": 0.0,
            "cpu_used": 0.0,
            "cpu_assigned": 0.0,
            "stor_cap": 0.0,
            "stor_used": 0.0,
        }
        return cache.get(f"global_dashboard:{range_suffix}") or {
            "overview": self.get_global_overview(tr),
            "platforms": {"nutanix": {"hosts": 0, "vms": 0}, "vmware": {"clusters": 0, "hosts": 0, "vms": 0}, "ibm": {"hosts": 0, "vios": 0, "lpars": 0}},
            "energy_breakdown": {"ibm_kw": 0, "vcenter_kw": 0},
            "classic_totals": dict(empty_totals),
            "hyperconv_totals": dict(empty_totals),
            "ibm_totals": dict(empty_ibm),
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
        cache_key = customer_assets_cache_key(customer_name, tr.get("start", ""), tr.get("end", ""))
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        name = (customer_name or "").strip()
        # Broader ILIKE patterns: customer name anywhere (e.g. '%Boyner%')
        vm_pattern = f"%{name}%" if name else "%"
        lpar_pattern = f"%{name}%" if name else "%"
        veeam_pattern = f"%{name}%" if name else "%"
        storage_like_pattern = f"%{name}%" if name else "%"
        netbackup_workload_pattern = f"%{name}%" if name else "%"
        zerto_name_like = f"%{name}%" if name else "%"

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
                            "name": r[0], "source": r[1], "cluster": r[2], "vmhost": r[3],
                            "cpu": float(r[4] or 0.0),
                            "memory_gb": float(r[5] or 0.0),
                            "disk_gb": float(r[6] or 0.0),
                        }
                        for r in (classic_vm_rows or []) if r and r[0]
                    ]
                    classic_vm_list = self._enrich_customer_vm_list(cur, classic_vm_list)
                    classic_cpu_real = sum_cpu_real_total(classic_vm_list)

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
                            "name": r[0], "source": r[1], "cluster": r[2], "vmhost": r[3],
                            "cpu": float(r[4] or 0.0),
                            "memory_gb": float(r[5] or 0.0),
                            "disk_gb": float(r[6] or 0.0),
                        }
                        for r in (hc_vm_rows or []) if r and r[0]
                    ]
                    hc_vm_list = self._enrich_customer_vm_list(cur, hc_vm_list)
                    hc_cpu_real = sum_cpu_real_total(hc_vm_list)

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
            _empty_compute = {
                "vm_count": 0, "cpu_total": 0.0, "cpu_real_total": 0.0,
                "memory_gb": 0.0, "disk_gb": 0.0, "vm_list": [],
            }
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
                "cpu_real_total": classic_cpu_real,
                "memory_gb": classic_mem_gb,
                "disk_gb": classic_disk_gb,
                "vm_list": classic_vm_list,
            },
            "hyperconv": {
                "vm_count": hc_total,
                "vmware_only": hc_vmware_only,
                "nutanix_count": hc_nutanix,
                "cpu_total": hc_cpu,
                "cpu_real_total": hc_cpu_real,
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

    # ------------------------------------------------------------------
    # Backup helpers — NetBackup, Zerto, Veeam (per datacenter)
    # ------------------------------------------------------------------

    def _fetch_dc_netbackup_pools(self, dc_code: str, start_ts, end_ts) -> dict:
        """Fetch latest NetBackup pool metrics for a DC and time range."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                raw_rows = self._run_rows(
                    cur,
                    bq.NETBACKUP_DISK_POOLS_LATEST,
                    (start_ts, end_ts),
                )

        # Columns: collection_timestamp, netbackup_host, name, stype,
        #          storagecategory, diskvolumes_name, diskvolumes_state,
        #          usablesizebytes, availablespacebytes, usedcapacitybytes
        filtered = self._filter_rows_for_dc_by_name_and_host(
            raw_rows or [],
            dc_code,
            name_index=2,
            host_index=1,
        )

        pools: list[str] = []
        rows_out: list[dict] = []
        for r in filtered:
            (
                ts,
                host,
                name,
                stype,
                storagecategory,
                diskvolumes_name,
                diskvolumes_state,
                usable,
                available,
                used,
            ) = r
            if not name:
                continue
            pools.append(name)
            rows_out.append(
                {
                    "timestamp": ts,
                    "netbackup_host": host,
                    "name": name,
                    "stype": stype,
                    "storagecategory": storagecategory,
                    "diskvolumes_name": diskvolumes_name,
                    "diskvolumes_state": diskvolumes_state,
                    "usablesizebytes": int(usable or 0),
                    "availablespacebytes": int(available or 0),
                    "usedcapacitybytes": int(used or 0),
                }
            )

        unique_pools = sorted({p for p in pools if p})
        return {
            "pools": unique_pools,
            "rows": rows_out,
        }

    def _fetch_dc_zerto_sites(self, dc_code: str, start_ts, end_ts) -> dict:
        """Fetch latest Zerto site metrics for a DC and time range."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                raw_rows = self._run_rows(
                    cur,
                    bq.ZERTO_SITES_LATEST,
                    (start_ts, end_ts),
                )

        # Columns: collection_timestamp, zerto_host, name, site_type,
        #          is_connected, incoming_throughput_mb, outgoing_bandwidth_mb,
        #          provisioned_storage_mb, used_storage_mb
        filtered = self._filter_rows_for_dc_by_name_and_host(
            raw_rows or [],
            dc_code,
            name_index=2,
            host_index=1,
        )

        sites: list[str] = []
        rows_out: list[dict] = []
        for r in filtered:
            (
                ts,
                host,
                name,
                site_type,
                is_connected,
                incoming_mb,
                outgoing_mb,
                prov_mb,
                used_mb,
            ) = r
            if not name:
                continue
            sites.append(name)
            rows_out.append(
                {
                    "timestamp": ts,
                    "zerto_host": host,
                    "name": name,
                    "site_type": site_type,
                    "is_connected": str(is_connected).strip().lower() == "true"
                    if is_connected is not None
                    else None,
                    "incoming_throughput_mb": float(incoming_mb or 0),
                    "outgoing_bandwidth_mb": float(outgoing_mb or 0),
                    "provisioned_storage_mb": int(prov_mb or 0),
                    "used_storage_mb": int(used_mb or 0),
                }
            )

        unique_sites = sorted({s for s in sites if s})
        return {
            "sites": unique_sites,
            "rows": rows_out,
        }

    def _fetch_dc_veeam_repositories(self, dc_code: str, start_ts, end_ts) -> dict:
        """Fetch latest Veeam repository states for a DC and time range."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                raw_rows = self._run_rows(
                    cur,
                    bq.VEEAM_REPOSITORIES_LATEST,
                    (start_ts, end_ts),
                )

        # Columns: collection_time, id, name, host_name, type,
        #          capacity_gb, free_gb, used_space_gb, is_online
        filtered = self._filter_rows_for_dc_by_host_pattern(
            raw_rows or [],
            dc_code,
            host_index=3,
        )

        repos: list[str] = []
        rows_out: list[dict] = []
        for r in filtered:
            (
                ts,
                _repo_id,
                name,
                host_name,
                repo_type,
                capacity_gb,
                free_gb,
                used_gb,
                is_online,
            ) = r
            if not name:
                continue
            repos.append(name)
            rows_out.append(
                {
                    "timestamp": ts,
                    "name": name,
                    "host_name": host_name,
                    "type": repo_type,
                    "capacity_gb": float(capacity_gb or 0),
                    "free_gb": float(free_gb or 0),
                    "used_space_gb": float(used_gb or 0),
                    "is_online": bool(is_online) if is_online is not None else None,
                }
            )

        unique_repos = sorted({r for r in repos if r})
        return {
            "repos": unique_repos,
            "rows": rows_out,
        }

    def get_dc_netbackup_pools(self, dc_code: str, time_range: dict | None = None) -> dict:
        """Return cached NetBackup pool metrics for a DC and time range."""
        tr = time_range or default_time_range()
        start_ts, end_ts = time_range_to_bounds(tr)
        cache_key = f"dc_netbackup:{dc_code}:{tr.get('start','')}:{tr.get('end','')}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        try:
            result = self._fetch_dc_netbackup_pools(dc_code, start_ts, end_ts)
        except (OperationalError, PoolError) as exc:
            logger.warning("get_dc_netbackup_pools failed for %s: %s", dc_code, exc)
            return {"pools": [], "rows": []}

        cache.set(cache_key, result)
        return result

    def get_dc_zerto_sites(self, dc_code: str, time_range: dict | None = None) -> dict:
        """Return cached Zerto site metrics for a DC and time range."""
        tr = time_range or default_time_range()
        start_ts, end_ts = time_range_to_bounds(tr)
        cache_key = f"dc_zerto:{dc_code}:{tr.get('start','')}:{tr.get('end','')}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        try:
            result = self._fetch_dc_zerto_sites(dc_code, start_ts, end_ts)
        except (OperationalError, PoolError) as exc:
            logger.warning("get_dc_zerto_sites failed for %s: %s", dc_code, exc)
            return {"sites": [], "rows": []}

        cache.set(cache_key, result)
        return result

    def get_dc_veeam_repos(self, dc_code: str, time_range: dict | None = None) -> dict:
        """Return cached Veeam repository states for a DC and time range."""
        tr = time_range or default_time_range()
        start_ts, end_ts = time_range_to_bounds(tr)
        cache_key = f"dc_veeam:{dc_code}:{tr.get('start','')}:{tr.get('end','')}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        try:
            result = self._fetch_dc_veeam_repositories(dc_code, start_ts, end_ts)
        except (OperationalError, PoolError) as exc:
            logger.warning("get_dc_veeam_repos failed for %s: %s", dc_code, exc)
            return {"repos": [], "rows": []}

        cache.set(cache_key, result)
        return result

    # ------------------------------------------------------------------
    # Backup job statistics (Phase 1) — Veeam / Zerto / NetBackup
    # ------------------------------------------------------------------

    # Postgres date_trunc accepts these granularities.
    _ALLOWED_GRANULARITIES = ("day", "week", "month")

    # Backup-jobs cache için override TTL. Global cache_ttl_seconds (1200s/20dk)
    # warm pass interval'ından kısa olduğu için backup-jobs key'leri TTL geçtikten
    # sonra cache miss yaşıyordu. Bu TTL 35dk = 30dk warm interval + 5dk emniyet
    # marjı, böylece her warm pass key'leri expire OLMADAN overwrite eder.
    # Sadece backup-jobs key'lerine uygulanır; diğer endpoint'lerin TTL'i değişmez.
    _BACKUP_JOBS_CACHE_TTL_SECONDS = 2100

    def _trigger_async_jobs_compute(
        self,
        vendor: str,
        gran: str,
        start_ts,
        end_ts,
        tr_start: str,
        tr_end: str,
    ) -> None:
        """
        Stale-while-revalidate için arka planda yeni hesaplama tetikler.
        Singleflight altında çalışır, eş zamanlı tetiklerde tek SQL pass garantili.
        """
        compute_map = {
            "veeam": self._compute_all_dc_veeam_jobs,
            "zerto": self._compute_all_dc_zerto_jobs,
            "netbackup": self._compute_all_dc_netbackup_jobs,
        }
        compute_fn = compute_map.get(vendor)
        if compute_fn is None:
            return
        sf_key = f"_sf:{vendor}_jobs:{tr_start}:{tr_end}:{gran}"

        def _bg() -> None:
            try:
                cache.run_singleflight(
                    sf_key,
                    lambda: compute_fn(gran, start_ts, end_ts, tr_start, tr_end),
                    ttl=60,
                )
            except Exception as exc:  # noqa: BLE001 — background log only
                logger.warning("Stale-revalidate %s failed: %s", vendor, exc)

        threading.Thread(
            target=_bg, daemon=True, name=f"bkp-stale-refresh-{vendor}"
        ).start()

    @staticmethod
    def _normalize_granularity(value: str | None) -> str:
        v = (value or "day").lower().strip()
        if v in ("daily", "day"):
            return "day"
        if v in ("weekly", "week"):
            return "week"
        if v in ("monthly", "month"):
            return "month"
        return "day"

    @staticmethod
    def _normalize_veeam_result(raw: str | None) -> str:
        if not raw:
            return "other"
        v = str(raw).strip().lower()
        if v == "success":
            return "success"
        if v == "failed":
            return "failed"
        if v == "warning":
            return "warning"
        if v == "none":
            return "running"
        return "other"

    @staticmethod
    def _normalize_zerto_status(raw) -> str:
        """Zerto VPG status enum: 1=MeetingSLA (success), 2/3=problematic, 0/5=in-progress, 4=removing."""
        try:
            code = int(raw)
        except (TypeError, ValueError):
            return "other"
        if code == 1:
            return "success"
        if code in (2, 3):
            return "failed"
        if code in (0, 5):
            return "running"
        if code == 4:
            return "warning"
        return "other"

    @staticmethod
    def _normalize_netbackup_status(raw) -> str:
        """NetBackup exit code: 0=success, 1=partial(warning), other=failed."""
        try:
            code = int(raw)
        except (TypeError, ValueError):
            return "other"
        if code == 0:
            return "success"
        if code == 1:
            return "warning"
        return "failed"

    def _build_ip_to_dc_map(self, rows: list[tuple], ip_index: int, label_index: int) -> dict[str, str]:
        """Extract DC code from a free-text label column; map source_ip → DC code (UPPER)."""
        dc_set = {dc.upper() for dc in self.dc_list}
        ip_to_dc: dict[str, str] = {}
        for row in rows or []:
            if row is None or len(row) <= max(ip_index, label_index):
                continue
            ip = row[ip_index]
            label = row[label_index]
            if not ip or not label:
                continue
            dc = self._extract_dc_from_text(label, dc_set)
            if dc:
                ip_to_dc[str(ip)] = dc.upper()
        return ip_to_dc

    @staticmethod
    def _utc_now_iso() -> str:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _empty_job_stats(vendor: str, granularity: str, time_range: dict) -> dict:
        return {
            "vendor": vendor,
            "granularity": granularity,
            "range": {"start": str(time_range.get("start", "")), "end": str(time_range.get("end", ""))},
            "series": [],
            "totals": {
                "total": 0,
                "success": 0,
                "failed": 0,
                "warning": 0,
                "other": 0,
                "success_rate": 0.0,
                "avg_per_period": 0.0,
                "period_count": 0,
            },
            "as_of": DatabaseService._utc_now_iso(),
        }

    @staticmethod
    def _finalize_job_stats(
        series: list[dict],
        vendor: str,
        granularity: str,
        time_range: dict,
        as_of: str | None = None,
    ) -> dict:
        """Compute totals + success rate + avg per period over an already-collapsed series."""
        total = sum(int(p.get("count", 0)) for p in series)
        success = sum(int(p["count"]) for p in series if p.get("status") == "success")
        failed = sum(int(p["count"]) for p in series if p.get("status") == "failed")
        warning = sum(int(p["count"]) for p in series if p.get("status") == "warning")
        other = max(total - success - failed - warning, 0)
        success_rate = (success / total * 100.0) if total else 0.0
        period_count = len({p.get("period") for p in series if p.get("period")})
        avg_per_period = (total / period_count) if period_count else 0.0
        return {
            "vendor": vendor,
            "granularity": granularity,
            "range": {"start": str(time_range.get("start", "")), "end": str(time_range.get("end", ""))},
            "series": series,
            "totals": {
                "total": total,
                "success": success,
                "failed": failed,
                "warning": warning,
                "other": other,
                "success_rate": round(success_rate, 2),
                "avg_per_period": round(avg_per_period, 2),
                "period_count": period_count,
            },
            "as_of": as_of or DatabaseService._utc_now_iso(),
        }

    # ---- Veeam jobs --------------------------------------------------------

    def _compute_all_dc_veeam_jobs(
        self,
        gran: str,
        start_ts,
        end_ts,
        tr_start: str,
        tr_end: str,
    ) -> dict[str, dict]:
        """
        Tek SQL geçişiyle TÜM DC'lerin Veeam job stat'lerini hesapla; her DC'nin
        payload'unu kendi cache key'ine yaz. Singleflight altında çağrıldığı için
        eş zamanlı miss'lerde tek SQL run.

        Phase 1'deki "her DC için ayrı SQL" hatasını giderir — warm pass'te
        14 SQL × 504 task yerine 1 SQL × 36 task çalışır.
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                agg_rows = self._run_rows(cur, bq.VEEAM_SESSION_JOB_STATS, (gran, start_ts, end_ts))
                seed_rows = self._run_rows(cur, bq.VEEAM_IP_TO_DC_SEED, (start_ts, end_ts))

        ip_to_dc = self._build_ip_to_dc_map(seed_rows or [], ip_index=0, label_index=1)

        per_dc_collapsed: dict[str, dict[tuple, int]] = {}
        for row in agg_rows or []:
            period, source_ip, result, session_type, cnt = row
            dc = ip_to_dc.get(str(source_ip))
            if not dc:
                continue
            status = self._normalize_veeam_result(result)
            period_key = period.date().isoformat() if hasattr(period, "date") else str(period)
            key = (period_key, status, session_type or "Unknown")
            bucket = per_dc_collapsed.setdefault(dc.upper(), {})
            bucket[key] = bucket.get(key, 0) + int(cnt or 0)

        tr = {"start": tr_start, "end": tr_end}
        out: dict[str, dict] = {}
        for dc_code in self.dc_list:
            dc_upper = dc_code.upper()
            collapsed = per_dc_collapsed.get(dc_upper, {})
            if collapsed:
                series = [
                    {"period": p, "status": s, "job_type": t, "policy_type": None, "count": c}
                    for (p, s, t), c in sorted(collapsed.items())
                ]
                payload = self._finalize_job_stats(series, "veeam", gran, tr)
            else:
                payload = self._empty_job_stats("veeam", gran, tr)
            out[dc_upper] = payload
            cache.set_with_stale(
                f"dc_veeam_jobs:{dc_code}:{tr_start}:{tr_end}:{gran}",
                payload,
                fresh_ttl=self._BACKUP_JOBS_CACHE_TTL_SECONDS,
            )
        return out

    def get_dc_veeam_jobs(
        self,
        dc_code: str,
        time_range: dict | None = None,
        granularity: str = "day",
    ) -> dict:
        tr = time_range or default_time_range()
        start_ts, end_ts = time_range_to_bounds(tr)
        gran = self._normalize_granularity(granularity)
        tr_start = str(tr.get("start", ""))
        tr_end = str(tr.get("end", ""))
        cache_key = f"dc_veeam_jobs:{dc_code}:{tr_start}:{tr_end}:{gran}"

        # Stale-while-revalidate: fresh varsa direkt dön; stale varsa direkt
        # dön + arka planda yeniden hesap tetikle; ikisi de yoksa senkronize hesap.
        value, is_stale = cache.get_with_stale(cache_key)
        if value is not None:
            if is_stale:
                # Fresh key'i stale snapshot'tan re-write et — cache_backend
                # memory→Redis backfill'i default TTL kullanıyor; bu TTL'imizi
                # 35dk'da tutar. Background refresh sonucunu hala overwrite eder.
                cache.set(cache_key, value, ttl=self._BACKUP_JOBS_CACHE_TTL_SECONDS)
                self._trigger_async_jobs_compute("veeam", gran, start_ts, end_ts, tr_start, tr_end)
            return value

        sf_key = f"_sf:veeam_jobs:{tr_start}:{tr_end}:{gran}"
        try:
            all_payloads = cache.run_singleflight(
                sf_key,
                lambda: self._compute_all_dc_veeam_jobs(gran, start_ts, end_ts, tr_start, tr_end),
                ttl=60,
            )
        except (OperationalError, PoolError) as exc:
            logger.warning("get_dc_veeam_jobs failed for %s: %s", dc_code, exc)
            return self._empty_job_stats("veeam", gran, tr)

        return (
            all_payloads.get(dc_code.upper())
            if isinstance(all_payloads, dict)
            else None
        ) or self._empty_job_stats("veeam", gran, tr)

    # ---- Zerto jobs --------------------------------------------------------

    def _compute_all_dc_zerto_jobs(
        self,
        gran: str,
        start_ts,
        end_ts,
        tr_start: str,
        tr_end: str,
    ) -> dict[str, dict]:
        """
        Tek SQL geçişiyle TÜM DC'lerin Zerto VPG job stat'lerini hesapla;
        her DC'nin payload'unu kendi cache key'ine yaz. source_site DC label'ı
        zaten satırda olduğu için aux query gerekmiyor.
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                agg_rows = self._run_rows(cur, bq.ZERTO_VPG_JOB_STATS, (gran, start_ts, end_ts))

        dc_set = {dc.upper() for dc in self.dc_list}
        per_dc_collapsed: dict[str, dict[tuple, int]] = {}
        for row in agg_rows or []:
            period, source_site, status_int, cnt = row
            dc = self._extract_dc_from_text(source_site, dc_set)
            if not dc:
                continue
            status = self._normalize_zerto_status(status_int)
            period_key = period.date().isoformat() if hasattr(period, "date") else str(period)
            key = (period_key, status, f"status_{status_int}")
            bucket = per_dc_collapsed.setdefault(dc.upper(), {})
            bucket[key] = bucket.get(key, 0) + int(cnt or 0)

        tr = {"start": tr_start, "end": tr_end}
        out: dict[str, dict] = {}
        for dc_code in self.dc_list:
            dc_upper = dc_code.upper()
            collapsed = per_dc_collapsed.get(dc_upper, {})
            if collapsed:
                series = [
                    {"period": p, "status": s, "job_type": t, "policy_type": None, "count": c}
                    for (p, s, t), c in sorted(collapsed.items())
                ]
                payload = self._finalize_job_stats(series, "zerto", gran, tr)
            else:
                payload = self._empty_job_stats("zerto", gran, tr)
            out[dc_upper] = payload
            cache.set_with_stale(
                f"dc_zerto_jobs:{dc_code}:{tr_start}:{tr_end}:{gran}",
                payload,
                fresh_ttl=self._BACKUP_JOBS_CACHE_TTL_SECONDS,
            )
        return out

    def get_dc_zerto_jobs(
        self,
        dc_code: str,
        time_range: dict | None = None,
        granularity: str = "day",
    ) -> dict:
        tr = time_range or default_time_range()
        start_ts, end_ts = time_range_to_bounds(tr)
        gran = self._normalize_granularity(granularity)
        tr_start = str(tr.get("start", ""))
        tr_end = str(tr.get("end", ""))
        cache_key = f"dc_zerto_jobs:{dc_code}:{tr_start}:{tr_end}:{gran}"

        value, is_stale = cache.get_with_stale(cache_key)
        if value is not None:
            if is_stale:
                cache.set(cache_key, value, ttl=self._BACKUP_JOBS_CACHE_TTL_SECONDS)
                self._trigger_async_jobs_compute("zerto", gran, start_ts, end_ts, tr_start, tr_end)
            return value

        sf_key = f"_sf:zerto_jobs:{tr_start}:{tr_end}:{gran}"
        try:
            all_payloads = cache.run_singleflight(
                sf_key,
                lambda: self._compute_all_dc_zerto_jobs(gran, start_ts, end_ts, tr_start, tr_end),
                ttl=60,
            )
        except (OperationalError, PoolError) as exc:
            logger.warning("get_dc_zerto_jobs failed for %s: %s", dc_code, exc)
            return self._empty_job_stats("zerto", gran, tr)

        return (
            all_payloads.get(dc_code.upper())
            if isinstance(all_payloads, dict)
            else None
        ) or self._empty_job_stats("zerto", gran, tr)

    # ---- NetBackup jobs ----------------------------------------------------

    def _compute_all_dc_netbackup_jobs(
        self,
        gran: str,
        start_ts,
        end_ts,
        tr_start: str,
        tr_end: str,
    ) -> dict[str, dict]:
        """
        Tek SQL geçişiyle TÜM DC'lerin NetBackup job stat'lerini hesapla;
        her DC'nin payload'unu kendi cache key'ine yaz. destinationmediaservername
        kolonu DC code'unu (örn. 'nbmediadc14.blt.vc') zaten satırda taşıyor.
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                agg_rows = self._run_rows(cur, bq.NETBACKUP_JOB_STATS, (gran, start_ts, end_ts))

        dc_set = {dc.upper() for dc in self.dc_list}
        per_dc_collapsed: dict[str, dict[tuple, int]] = {}
        for row in agg_rows or []:
            period, dc_label, status_int, jobtype, policytype, cnt = row
            dc = self._extract_dc_from_text(dc_label, dc_set)
            if not dc:
                continue
            status = self._normalize_netbackup_status(status_int)
            period_key = period.date().isoformat() if hasattr(period, "date") else str(period)
            key = (period_key, status, jobtype or "Unknown", policytype or "Unknown")
            bucket = per_dc_collapsed.setdefault(dc.upper(), {})
            bucket[key] = bucket.get(key, 0) + int(cnt or 0)

        tr = {"start": tr_start, "end": tr_end}
        out: dict[str, dict] = {}
        for dc_code in self.dc_list:
            dc_upper = dc_code.upper()
            collapsed = per_dc_collapsed.get(dc_upper, {})
            if collapsed:
                series = [
                    {"period": p, "status": s, "job_type": jt, "policy_type": pt, "count": c}
                    for (p, s, jt, pt), c in sorted(collapsed.items())
                ]
                payload = self._finalize_job_stats(series, "netbackup", gran, tr)
            else:
                payload = self._empty_job_stats("netbackup", gran, tr)
            out[dc_upper] = payload
            cache.set_with_stale(
                f"dc_netbackup_jobs:{dc_code}:{tr_start}:{tr_end}:{gran}",
                payload,
                fresh_ttl=self._BACKUP_JOBS_CACHE_TTL_SECONDS,
            )
        return out

    def get_dc_netbackup_jobs(
        self,
        dc_code: str,
        time_range: dict | None = None,
        granularity: str = "day",
    ) -> dict:
        tr = time_range or default_time_range()
        start_ts, end_ts = time_range_to_bounds(tr)
        gran = self._normalize_granularity(granularity)
        tr_start = str(tr.get("start", ""))
        tr_end = str(tr.get("end", ""))
        cache_key = f"dc_netbackup_jobs:{dc_code}:{tr_start}:{tr_end}:{gran}"

        value, is_stale = cache.get_with_stale(cache_key)
        if value is not None:
            if is_stale:
                cache.set(cache_key, value, ttl=self._BACKUP_JOBS_CACHE_TTL_SECONDS)
                self._trigger_async_jobs_compute("netbackup", gran, start_ts, end_ts, tr_start, tr_end)
            return value

        sf_key = f"_sf:netbackup_jobs:{tr_start}:{tr_end}:{gran}"
        try:
            all_payloads = cache.run_singleflight(
                sf_key,
                lambda: self._compute_all_dc_netbackup_jobs(gran, start_ts, end_ts, tr_start, tr_end),
                ttl=60,
            )
        except (OperationalError, PoolError) as exc:
            logger.warning("get_dc_netbackup_jobs failed for %s: %s", dc_code, exc)
            return self._empty_job_stats("netbackup", gran, tr)

        return (
            all_payloads.get(dc_code.upper())
            if isinstance(all_payloads, dict)
            else None
        ) or self._empty_job_stats("netbackup", gran, tr)

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
        """Return list of customer names for selector (aligned with WARMED_CUSTOMERS)."""
        return list(WARMED_CUSTOMERS)

    # ------------------------------------------------------------------
    # Network SAN + Storage (Brocade + IBM Storage)
    # ------------------------------------------------------------------

    def _resolve_ibm_storage_dc(
        self,
        storage_ip: str | None,
        name: str | None = None,
        location: str | None = None,
    ) -> str | None:
        """
        Resolve DC code for an IBM storage system.

        Strategy:
        1) Regex extraction from `name` and `location` fields (and storage_ip as a last resort).
        2) Fallback: NetBox discovery match by `primary_ip_address` (storage_ip) and
           DC inference from site/location/name fields.
        """
        if not storage_ip:
            # Try regex from name/location without needing IP.
            dc_set = {dc.upper() for dc in self.dc_list}
            blob = f"{name or ''} {location or ''}".upper()
            match = _DC_CODE_RE.search(blob)
            if match:
                code = match.group(1).upper()
                return code if code in dc_set else None
            return None

        ip_key = str(storage_ip).strip()
        if not ip_key:
            return None

        if ip_key in self._ibm_storage_ip_dc_cache:
            return self._ibm_storage_ip_dc_cache[ip_key]

        dc_set = {dc.upper() for dc in self.dc_list}

        # Prefer textual signals (name/location) over IP matching. This avoids
        # cases where the discovery table returns a different site/location.
        blob_text = f"{name or ''} {location or ''}".upper()
        match = _DC_CODE_RE.search(blob_text)
        if match:
            code = match.group(1).upper()
            resolved = code if code in dc_set else None
            self._ibm_storage_ip_dc_cache[ip_key] = resolved
            return resolved

        resolved: str | None = None
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    like = f"%{ip_key}%"
                    rows = self._run_rows(
                        cur,
                        """
SELECT
    site_name,
    location_name,
    "name",
    primary_ip_address
FROM public.discovery_netbox_inventory_device
WHERE
    status_value = 'active'
    AND (
    primary_ip_address = %s
 OR primary_ip_address ILIKE %s
    )
ORDER BY collection_time DESC NULLS LAST
LIMIT 20
""",
                        (ip_key, like),
                    )

            for site_name, location_name, name_val, _primary_ip in rows:
                resolved = self._extract_dc_from_text(site_name, dc_set)
                if resolved:
                    break
                resolved = self._extract_dc_from_text(location_name, dc_set)
                if resolved:
                    break
                resolved = self._extract_dc_from_text(name_val, dc_set)
                if resolved:
                    break
        except Exception as exc:
            logger.warning("Could not resolve IBM storage DC for %s: %s", ip_key, exc)
            resolved = None

        self._ibm_storage_ip_dc_cache[ip_key] = resolved
        return resolved

    def get_san_switches(self, dc_code: str, time_range: dict | None = None) -> list[str]:
        """
        Return DC-scoped Brocade switch_host list for the given time range.

        This is used to gate the Network > SAN tab rendering (has_san).
        """
        tr = time_range or default_time_range()
        start_ts, end_ts = time_range_to_bounds(tr)

        dc_target = (dc_code or "").upper()
        if not dc_target:
            return []

        cache_key = f"dc_san_switches:{dc_target}:{tr.get('start','')}:{tr.get('end','')}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    switch_rows = self._run_rows(
                        cur,
                        brq.SWITCH_HOSTS_IN_RANGE,
                        (start_ts, end_ts),
                    )
            raw_switches = [r[0] for r in (switch_rows or []) if r and r[0]]

            resolved_switches: set[str] = set()
            for sh in raw_switches:
                resolved_dc = self._resolve_brocade_dc(sh)
                if resolved_dc and resolved_dc.upper() == dc_target:
                    resolved_switches.add(sh)
            result = sorted(resolved_switches)
        except (OperationalError, PoolError) as exc:
            logger.warning("get_san_switches failed for %s: %s", dc_target, exc)
            result = []

        cache.set(cache_key, result)
        return result

    def get_san_port_usage(self, dc_code: str, time_range: dict | None = None) -> dict:
        """
        Return aggregated port/licensing usage for Network > SAN gauges.
        """
        tr = time_range or default_time_range()
        dc_target = (dc_code or "").upper()

        cache_key = f"dc_san_port_usage:{dc_target}:{tr.get('start','')}:{tr.get('end','')}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        try:
            switches = self.get_san_switches(dc_target, tr)
            if not switches:
                result = {
                    "switch_count": 0,
                    "total_ports": 0,
                    "licensed_ports": 0,
                    "active_ports": 0,
                    "enabled_ports": 0,
                    "no_link_ports": 0,
                    "disabled_ports": 0,
                }
            else:
                with self._get_connection() as conn:
                    with conn.cursor() as cur:
                        row = self._run_row(
                            cur,
                            brq.PORT_USAGE_LATEST,
                            (switches,),
                        )

                row = row or (0, 0, 0, 0, 0, 0)
                result = {
                    "switch_count": len(switches),
                    "total_ports": int(row[0] or 0),
                    "licensed_ports": int(row[1] or 0),
                    "active_ports": int(row[2] or 0),
                    "enabled_ports": int(row[3] or 0),
                    "no_link_ports": int(row[4] or 0),
                    "disabled_ports": int(row[5] or 0),
                }
        except (OperationalError, PoolError) as exc:
            logger.warning("get_san_port_usage failed for %s: %s", dc_target, exc)
            result = {
                "switch_count": 0,
                "total_ports": 0,
                "licensed_ports": 0,
                "active_ports": 0,
                "enabled_ports": 0,
                "no_link_ports": 0,
                "disabled_ports": 0,
            }

        cache.set(cache_key, result)
        return result

    def get_san_health_alerts(self, dc_code: str, time_range: dict | None = None) -> list[dict]:
        """
        Return latest delta-based SAN health alerts for Network > SAN risk panel.
        """
        tr = time_range or default_time_range()
        dc_target = (dc_code or "").upper()

        cache_key = f"dc_san_health:{dc_target}:{tr.get('start','')}:{tr.get('end','')}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        try:
            switches = self.get_san_switches(dc_target, tr)
            if not switches:
                result: list[dict] = []
            else:
                with self._get_connection() as conn:
                    with conn.cursor() as cur:
                        rows = self._run_rows(
                            cur,
                            brq.HEALTH_ALERTS_LATEST,
                            (switches,),
                        )

                result = []
                for (
                    switch_host,
                    port_name,
                    crc_errors_delta,
                    link_failures_delta,
                    loss_of_sync_delta,
                    loss_of_signal_delta,
                ) in (rows or []):
                    result.append(
                        {
                            "switch_host": switch_host,
                            "port_name": port_name,
                            "crc_errors_delta": int(crc_errors_delta or 0),
                            "link_failures_delta": int(link_failures_delta or 0),
                            "loss_of_sync_delta": int(loss_of_sync_delta or 0),
                            "loss_of_signal_delta": int(loss_of_signal_delta or 0),
                        }
                    )
        except (OperationalError, PoolError) as exc:
            logger.warning("get_san_health_alerts failed for %s: %s", dc_target, exc)
            result = []

        cache.set(cache_key, result)
        return result

    def get_san_traffic_trend(self, dc_code: str, time_range: dict | None = None) -> list[dict]:
        """
        Return hourly in/out rate trend for Network > SAN traffic chart.
        """
        tr = time_range or default_time_range()
        dc_target = (dc_code or "").upper()
        start_ts, end_ts = time_range_to_bounds(tr)

        cache_key = f"dc_san_traffic:{dc_target}:{tr.get('start','')}:{tr.get('end','')}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        try:
            switches = self.get_san_switches(dc_target, tr)
            if not switches:
                result: list[dict] = []
            else:
                with self._get_connection() as conn:
                    with conn.cursor() as cur:
                        rows = self._run_rows(
                            cur,
                            brq.TRAFFIC_TREND_HOURLY,
                            (switches, start_ts, end_ts),
                        )
                result = [
                    {
                        "ts": ts,
                        "in_rate": int(in_rate or 0),
                        "out_rate": int(out_rate or 0),
                    }
                    for ts, in_rate, out_rate in (rows or [])
                ]
        except (OperationalError, PoolError) as exc:
            logger.warning("get_san_traffic_trend failed for %s: %s", dc_target, exc)
            result = []

        cache.set(cache_key, result)
        return result

    def get_storage_capacity(self, dc_code: str, time_range: dict | None = None) -> dict:
        """
        Return IBM Storage capacity snapshot data for DC-scoped systems.

        Capacity fields are returned as the raw varchar values coming from
        `ibm_storage_system` (e.g. '110.00 TB'); parsing happens in the GUI.
        """
        tr = time_range or default_time_range()
        dc_target = (dc_code or "").upper()

        cache_key = f"dc_storage_capacity:{dc_target}:{tr.get('start','')}:{tr.get('end','')}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        try:
            # Fetch one latest row per storage_ip (across all DCs), then resolve DC in Python.
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    rows = self._run_rows(
                        cur,
                        """
WITH latest AS (
    SELECT storage_ip, MAX("timestamp") AS max_ts
    FROM public.raw_ibm_storage_system
    GROUP BY storage_ip
)
SELECT
    s.storage_ip,
    s.name,
    s.location,
    s.topology,
    s.physical_capacity,
    s.physical_free_capacity,
    s.layer,
    s.total_mdisk_capacity,
    s.total_used_capacity,
    s.total_free_space,
    s."timestamp"
FROM public.raw_ibm_storage_system s
JOIN latest l
  ON s.storage_ip = l.storage_ip
 AND s."timestamp" = l.max_ts;
""",
                    )

            systems: list[dict] = []
            for (
                storage_ip,
                name,
                location,
                topology,
                physical_capacity,
                physical_free_capacity,
                layer,
                total_mdisk_capacity,
                total_used_capacity,
                total_free_space,
                ts,
            ) in (rows or []):
                resolved_dc = self._resolve_ibm_storage_dc(
                    storage_ip=str(storage_ip) if storage_ip is not None else None,
                    name=name,
                    location=location,
                )
                if not resolved_dc or resolved_dc.upper() != dc_target:
                    continue

                systems.append(
                    {
                        "storage_ip": storage_ip,
                        "name": name,
                        "location": location,
                        "topology": topology,
                        "physical_capacity": physical_capacity,
                        "physical_free_capacity": physical_free_capacity,
                        "layer": layer,
                        "total_mdisk_capacity": total_mdisk_capacity,
                        "total_used_capacity": total_used_capacity,
                        "total_free_space": total_free_space,
                        "timestamp": ts,
                    }
                )

            result = {"systems": systems, "system_count": len(systems)}
        except (OperationalError, PoolError) as exc:
            logger.warning("get_storage_capacity failed for %s: %s", dc_target, exc)
            result = {"systems": [], "system_count": 0}

        cache.set(cache_key, result)
        return result

    def get_storage_performance(self, dc_code: str, time_range: dict | None = None) -> dict:
        """
        Return daily average performance time series for DC-scoped IBM storage.
        """
        tr = time_range or default_time_range()
        dc_target = (dc_code or "").upper()
        start_ts, end_ts = time_range_to_bounds(tr)

        cache_key = f"dc_storage_perf:{dc_target}:{tr.get('start','')}:{tr.get('end','')}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        try:
            # Resolve the set of storage_ip values belonging to this DC.
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    rows = self._run_rows(
                        cur,
                        """
WITH latest AS (
    SELECT storage_ip, MAX("timestamp") AS max_ts
    FROM public.raw_ibm_storage_system
    GROUP BY storage_ip
)
SELECT
    s.storage_ip,
    s.name,
    s.location
FROM public.raw_ibm_storage_system s
JOIN latest l
  ON s.storage_ip = l.storage_ip
 AND s."timestamp" = l.max_ts;
""",
                    )

            storage_ips: list[str] = []
            for storage_ip, name, location in (rows or []):
                resolved_dc = self._resolve_ibm_storage_dc(storage_ip, name=name, location=location)
                if resolved_dc and resolved_dc.upper() == dc_target and storage_ip:
                    storage_ips.append(str(storage_ip))

            storage_ips = sorted(set(storage_ips))
            if not storage_ips:
                result = {"series": []}
            else:
                with self._get_connection() as conn:
                    with conn.cursor() as cur:
                        perf_rows = self._run_rows(
                            cur,
                            isq.STORAGE_SYSTEM_STATS_DAILY_AVG,
                            (storage_ips, start_ts, end_ts),
                        )

                series = [
                    {
                        "ts": ts,
                        "iops": float(avg_iops or 0),
                        "throughput_mb": float(avg_throughput_mb or 0),
                        "latency_ms": float(avg_latency_ms or 0),
                    }
                    for ts, avg_iops, avg_throughput_mb, avg_latency_ms in (perf_rows or [])
                ]
                result = {"series": series, "storage_ip_count": len(storage_ips)}
        except (OperationalError, PoolError) as exc:
            logger.warning("get_storage_performance failed for %s: %s", dc_target, exc)
            result = {"series": []}

        cache.set(cache_key, result)
        return result

    # ------------------------------------------------------------------
    # Zabbix Network Dashboard (Intel-capacity oriented Network view)
    # ------------------------------------------------------------------

    def _resolve_zabbix_dc_devices(
        self,
        dc_code: str,
        time_range: dict | None = None,
        manufacturer: str | None = None,
        device_role: str | None = None,
        device_name: str | None = None,
    ) -> dict:
        """
        Resolve Zabbix network device rows for the given DC (latest per loki_id),
        then optionally filter by manufacturer / role / device name.

        Returned structure:
          - devices: list[dict]
          - hosts: list[str]
          - loki_ids: list[str]
        """
        tr = time_range or default_time_range()
        start_ts, end_ts = time_range_to_bounds(tr)
        dc_target = (dc_code or "").upper()
        if not dc_target:
            return {"devices": [], "hosts": [], "loki_ids": []}

        cache_key = (
            f"dc_zabbix_net_devices:{dc_target}:"
            f"{manufacturer or ''}:{device_role or ''}:{device_name or ''}:"
            f"{tr.get('start','')}:{tr.get('end','')}"
        )
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    rows = self._run_rows(
                        cur,
                        znq.NETWORK_DEVICES_FOR_DC_LATEST,
                        (start_ts, end_ts, dc_target),
                    )

            devices: list[dict] = []
            for (
                loki_id,
                host,
                device_name_val,
                manufacturer_val,
                device_role_val,
                _location_name,
                _site_name,
                total_ports_count,
                active_ports_count,
                icmp_loss_pct,
                _collection_ts,
            ) in (rows or []):
                devices.append(
                    {
                        "loki_id": str(loki_id) if loki_id is not None else None,
                        "host": str(host) if host is not None else None,
                        "device_name": device_name_val or "Unknown",
                        "manufacturer_name": manufacturer_val or "Unknown",
                        "device_role_name": device_role_val or "Unknown",
                        "total_ports_count": int(total_ports_count or 0),
                        "active_ports_count": int(active_ports_count or 0),
                        "icmp_loss_pct": float(icmp_loss_pct or 0),
                    }
                )

            excluded_roles = self._excluded_roles_for_scope("datacenter")
            if excluded_roles:
                devices = [
                    d for d in devices
                    if not is_role_excluded(d.get("device_role_name"), excluded_roles)
                ]

            # Optional hierarchical filters
            if manufacturer is not None:
                devices = [d for d in devices if d.get("manufacturer_name") == manufacturer]
            if device_role is not None:
                devices = [d for d in devices if d.get("device_role_name") == device_role]
            if device_name is not None:
                devices = [d for d in devices if d.get("device_name") == device_name]

            hosts = sorted({d.get("host") for d in devices if d.get("host")})
            loki_ids = sorted({d.get("loki_id") for d in devices if d.get("loki_id")})

            result = {"devices": devices, "hosts": hosts, "loki_ids": loki_ids}
        except (OperationalError, PoolError) as exc:
            logger.warning("Zabbix network dc resolution failed for %s: %s", dc_target, exc)
            result = {"devices": [], "hosts": [], "loki_ids": []}

        cache.set(cache_key, result)
        return result

    def _resolve_scoped_network_devices(
        self,
        dc_target: str,
        tr: dict,
        interface_scope: str | None,
        manufacturer: str | None = None,
        device_name: str | None = None,
    ) -> dict:
        """Resolve hosts from scoped interface table (or all DC devices for overview)."""
        if not interface_scope or interface_scope == "overview":
            return self._resolve_zabbix_dc_devices(
                dc_target,
                tr,
                manufacturer=manufacturer,
                device_name=device_name,
            )

        start_ts, end_ts = time_range_to_bounds(tr)
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    rows = self._run_rows(
                        cur,
                        znq.build_scoped_hosts_for_dc_sql(interface_scope),
                        (dc_target, start_ts, end_ts),
                    )
        except (OperationalError, PoolError, ValueError) as exc:
            logger.warning("Scoped network host resolution failed for %s: %s", dc_target, exc)
            return {"devices": [], "hosts": [], "loki_ids": []}

        devices: list[dict] = []
        for host, manufacturer_val, device_name_val, device_role_val in (rows or []):
            devices.append(
                {
                    "host": str(host) if host is not None else None,
                    "device_name": device_name_val or "Unknown",
                    "manufacturer_name": manufacturer_val or "Unknown",
                    "device_role_name": device_role_val or "Unknown",
                }
            )

        if manufacturer is not None:
            devices = [d for d in devices if d.get("manufacturer_name") == manufacturer]
        if device_name is not None:
            devices = [d for d in devices if d.get("device_name") == device_name]

        hosts = sorted({d.get("host") for d in devices if d.get("host")})
        return {"devices": devices, "hosts": hosts, "loki_ids": []}

    def get_network_filters(
        self,
        dc_code: str,
        time_range: dict | None = None,
        interface_scope: str | None = None,
    ) -> dict:
        """
        Return filter options for the Network dashboard.
        When interface_scope is set, manufacturers/devices come from the scoped interface table.
        """
        tr = time_range or default_time_range()
        dc_target = (dc_code or "").upper()
        empty = {
            "manufacturers": [],
            "roles_by_manufacturer": {},
            "devices_by_manufacturer_role": {},
            "devices_by_manufacturer": {},
            "interface_scope": interface_scope or "overview",
        }
        if not dc_target:
            return empty

        scope_key = interface_scope or "overview"
        cache_key = (
            f"dc_zabbix_net_filters:{dc_target}:scope={scope_key}:"
            f"{tr.get('start','')}:{tr.get('end','')}"
        )
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        if scope_key != "overview":
            resolved = self._resolve_scoped_network_devices(dc_target, tr, interface_scope)
        else:
            resolved = self._resolve_zabbix_dc_devices(dc_target, tr)
        devices = resolved.get("devices") or []

        manufacturers = sorted({d.get("manufacturer_name") or "Unknown" for d in devices})
        roles_by_manufacturer: dict[str, set[str]] = {}
        devices_by_manufacturer_role: dict[str, dict[str, set[str]]] = {}
        devices_by_manufacturer: dict[str, set[str]] = {}

        for d in devices:
            manu = d.get("manufacturer_name") or "Unknown"
            role = d.get("device_role_name") or "Unknown"
            dev_name = d.get("device_name") or "Unknown"

            roles_by_manufacturer.setdefault(manu, set()).add(role)
            devices_by_manufacturer_role.setdefault(manu, {}).setdefault(role, set()).add(dev_name)
            devices_by_manufacturer.setdefault(manu, set()).add(dev_name)

        result = {
            "manufacturers": manufacturers,
            "roles_by_manufacturer": {
                manu: sorted(list(roles_set)) for manu, roles_set in roles_by_manufacturer.items()
            },
            "devices_by_manufacturer_role": {
                manu: {role: sorted(list(dev_set)) for role, dev_set in roles_map.items()}
                for manu, roles_map in devices_by_manufacturer_role.items()
            },
            "devices_by_manufacturer": {
                manu: sorted(list(dev_set)) for manu, dev_set in devices_by_manufacturer.items()
            },
            "interface_scope": scope_key,
        }
        cache.set(cache_key, result)
        return result

    def get_network_port_summary(
        self,
        dc_code: str,
        time_range: dict | None = None,
        manufacturer: str | None = None,
        device_role: str | None = None,
        device_name: str | None = None,
        interface_scope: str | None = None,
    ) -> dict:
        """
        Return KPI numbers for the Network Dashboard port capacity view.
        When interface_scope is set, counts come from scoped interface tables.
        """
        tr = time_range or default_time_range()
        dc_target = (dc_code or "").upper()
        scope_key = interface_scope or "overview"
        empty = {
            "device_count": 0,
            "total_ports": 0,
            "active_ports": 0,
            "avg_icmp_loss_pct": 0.0,
            "interface_scope": scope_key,
        }
        if not dc_target:
            return empty

        cache_key = (
            f"dc_zabbix_net_port_summary:{dc_target}:"
            f"{manufacturer or ''}:{device_role or ''}:{device_name or ''}:"
            f"scope={scope_key}:{tr.get('start','')}:{tr.get('end','')}"
        )
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        if scope_key != "overview":
            resolved = self._resolve_scoped_network_devices(
                dc_target,
                tr,
                interface_scope,
                manufacturer=manufacturer,
                device_name=device_name,
            )
            hosts: list[str] = resolved.get("hosts") or []
            if not hosts:
                cache.set(cache_key, empty)
                return empty

            start_ts, end_ts = time_range_to_bounds(tr)
            try:
                with self._get_connection() as conn:
                    with conn.cursor() as cur:
                        row = self._run_rows(
                            cur,
                            znq.build_scoped_port_summary_sql(interface_scope),
                            (hosts, start_ts, end_ts, hosts, start_ts, end_ts),
                        )
                if row:
                    device_count, total_ports, active_ports, avg_icmp_loss_pct = row[0]
                    result = {
                        "device_count": int(device_count or 0),
                        "total_ports": int(total_ports or 0),
                        "active_ports": int(active_ports or 0),
                        "avg_icmp_loss_pct": float(avg_icmp_loss_pct or 0),
                        "interface_scope": scope_key,
                    }
                else:
                    result = dict(empty)
            except (OperationalError, PoolError, ValueError) as exc:
                logger.warning("get_network_port_summary scoped failed for %s: %s", dc_target, exc)
                result = dict(empty)
        else:
            resolved = self._resolve_zabbix_dc_devices(
                dc_target,
                tr,
                manufacturer=manufacturer,
                device_role=device_role,
                device_name=device_name,
            )
            devices = resolved.get("devices") or []
            device_count = len(devices)
            total_ports = sum(int(d.get("total_ports_count") or 0) for d in devices)
            active_ports = sum(int(d.get("active_ports_count") or 0) for d in devices)
            avg_icmp_loss_pct = (
                sum(float(d.get("icmp_loss_pct") or 0) for d in devices) / device_count
                if device_count
                else 0.0
            )
            result = {
                "device_count": int(device_count),
                "total_ports": int(total_ports),
                "active_ports": int(active_ports),
                "avg_icmp_loss_pct": float(avg_icmp_loss_pct),
                "interface_scope": scope_key,
            }

        cache.set(cache_key, result)
        return result

    def get_network_95th_percentile(
        self,
        dc_code: str,
        time_range: dict | None = None,
        manufacturer: str | None = None,
        device_role: str | None = None,
        device_name: str | None = None,
        top_n: int = 20,
        interface_scope: str | None = None,
    ) -> dict:
        """
        Compute interface 95th percentile bandwidth (p95_rx/p95_tx) for the
        selected DC and (optional) device filters.
        """
        tr = time_range or default_time_range()
        dc_target = (dc_code or "").upper()
        if not dc_target:
            return {"top_interfaces": [], "overall_port_utilization_pct": 0.0}

        scope_key = interface_scope or "overview"
        cache_key = (
            f"dc_zabbix_net_95:{dc_target}:"
            f"{manufacturer or ''}:{device_role or ''}:{device_name or ''}:"
            f"scope={scope_key}:top={top_n}:{tr.get('start','')}:{tr.get('end','')}"
        )
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        if scope_key != "overview":
            resolved = self._resolve_scoped_network_devices(
                dc_target,
                tr,
                interface_scope,
                manufacturer=manufacturer,
                device_name=device_name,
            )
        else:
            resolved = self._resolve_zabbix_dc_devices(
                dc_target,
                tr,
                manufacturer=manufacturer,
                device_role=device_role,
                device_name=device_name,
            )
        hosts: list[str] = resolved.get("hosts") or []
        if not hosts:
            result = {"top_interfaces": [], "overall_port_utilization_pct": 0.0, "interface_scope": scope_key}
            cache.set(cache_key, result)
            return result

        start_ts, end_ts = time_range_to_bounds(tr)
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    rows = self._run_rows(
                        cur,
                        znq.build_interface_95th_percentile_sql(interface_scope),
                        (hosts, start_ts, end_ts),
                    )

            top_n_safe = int(top_n or 20)
            top_rows = (rows or [])[:top_n_safe]
            top_interfaces: list[dict] = []

            sum_total = 0.0
            sum_speed = 0.0
            for row in top_rows:
                if len(row) >= 7:
                    host_name, iface_name, iface_alias, p95_rx_bps, p95_tx_bps, p95_total_bps, speed_bps = row
                else:
                    host_name = None
                    iface_name, iface_alias, p95_rx_bps, p95_tx_bps, p95_total_bps, speed_bps = row
                p95_total = float(p95_total_bps or 0)
                speed = float(speed_bps or 0)
                utilization_pct = (p95_total / speed * 100.0) if speed > 0 else 0.0
                top_interfaces.append(
                    {
                        "host": host_name,
                        "interface_name": iface_name,
                        "interface_alias": iface_alias,
                        "p95_rx_bps": float(p95_rx_bps or 0),
                        "p95_tx_bps": float(p95_tx_bps or 0),
                        "p95_total_bps": p95_total,
                        "speed_bps": speed,
                        "utilization_pct": float(utilization_pct),
                    }
                )
                sum_total += p95_total
                sum_speed += speed

            overall_port_utilization_pct = (sum_total / sum_speed * 100.0) if sum_speed > 0 else 0.0
            result = {
                "top_interfaces": top_interfaces,
                "overall_port_utilization_pct": float(overall_port_utilization_pct),
                "interface_scope": scope_key,
            }
        except (OperationalError, PoolError, ValueError) as exc:
            logger.warning("get_network_95th_percentile failed for %s: %s", dc_target, exc)
            result = {"top_interfaces": [], "overall_port_utilization_pct": 0.0, "interface_scope": scope_key}

        cache.set(cache_key, result)
        return result

    def _resolve_network_interface_hosts(
        self,
        dc_target: str,
        tr: dict,
        interface_scope: str | None,
        manufacturer: str | None = None,
        device_role: str | None = None,
        device_name: str | None = None,
    ) -> tuple[list[str], str]:
        scope_key = interface_scope or "overview"
        if scope_key != "overview":
            resolved = self._resolve_scoped_network_devices(
                dc_target,
                tr,
                interface_scope,
                manufacturer=manufacturer,
                device_name=device_name,
            )
        else:
            resolved = self._resolve_zabbix_dc_devices(
                dc_target,
                tr,
                manufacturer=manufacturer,
                device_role=device_role,
                device_name=device_name,
            )
        return list(resolved.get("hosts") or []), scope_key

    def get_network_dc_access_unit_price_tl(self) -> dict:
        """Resolve TL/Mbit unit price for backbone billing (override, then catalog)."""
        productid = net_price_q.NETWORK_DC_ACCESS_PRODUCT_ID
        meta: dict[str, Any] = {
            "productid": productid,
            "product_name": net_price_q.NETWORK_DC_ACCESS_PRODUCT_NAME,
            "resource_unit": net_price_q.NETWORK_DC_ACCESS_RESOURCE_UNIT,
            "unit_price_tl": 0.0,
            "has_price": False,
            "price_source": None,
        }
        webui = getattr(self, "_webui", None)
        if webui is not None and getattr(webui, "is_available", False):
            try:
                row = webui.run_one(
                    net_price_q.GET_PRICE_OVERRIDE_FOR_PANEL,
                    (net_price_q.NETWORK_DC_ACCESS_PANEL_KEY,),
                )
                if row and row.get("unit_price_tl") is not None:
                    meta["unit_price_tl"] = round(float(row["unit_price_tl"]), 4)
                    meta["has_price"] = True
                    meta["price_source"] = "override"
                    return meta
            except Exception as exc:
                logger.warning("Network DC access price override lookup failed: %s", exc)

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    catalog = self._run_row(
                        cur,
                        net_price_q.CATALOG_TL_PRICE_FOR_PRODUCT,
                        (productid,),
                    )
            if catalog:
                amount = float(catalog[0] or 0)
                currency = str(catalog[1] or "TL").strip().upper()
                if amount > 0 and ("TL" in currency or currency in ("TRY", "TURKISH LIRA")):
                    meta["unit_price_tl"] = round(amount, 4)
                    meta["has_price"] = True
                    meta["price_source"] = "catalog"
        except Exception as exc:
            logger.warning("Network DC access catalog price lookup failed: %s", exc)
        return meta

    @staticmethod
    def _backbone_billing_response_meta(price_meta: dict) -> dict:
        return {
            "enabled": True,
            "productid": price_meta.get("productid"),
            "product_name": price_meta.get("product_name"),
            "resource_unit": price_meta.get("resource_unit"),
            "unit_price_tl": price_meta.get("unit_price_tl"),
            "price_source": price_meta.get("price_source"),
            "has_price": bool(price_meta.get("has_price")),
        }

    @staticmethod
    def _apply_backbone_billing(items: list[dict], price_meta: dict) -> list[dict]:
        """Enrich rows: Mbit from P95(total bps), cost = Mbit * CRM TL/Mbit (interface_calculation.py)."""
        unit_price = float(price_meta.get("unit_price_tl") or 0)
        has_price = bool(price_meta.get("has_price"))
        enriched: list[dict] = []
        for it in items or []:
            row = dict(it)
            p95_total = float(row.get("p95_total_bps") or 0)
            p95_mbit = p95_bps_to_mbit(p95_total)
            row["p95_billable_mbit"] = round(p95_mbit, 6)
            row["unit_price_tl_per_mbit"] = round(unit_price, 4) if has_price else None
            row["estimated_cost_tl"] = (
                estimate_backbone_cost_tl(p95_total, unit_price) if has_price else None
            )
            enriched.append(row)
        return enriched

    @staticmethod
    def _network_p95_rows_to_items(rows: list | None, include_total: bool = False) -> tuple[list[dict], int]:
        items: list[dict] = []
        total = 0
        for row in rows or []:
            if include_total and len(row) >= 8:
                (
                    host_name,
                    iface_name,
                    iface_alias,
                    p95_rx_bps,
                    p95_tx_bps,
                    p95_total_bps,
                    speed_bps,
                    total_count,
                ) = row
                total = int(total_count or 0)
            elif len(row) >= 7:
                host_name, iface_name, iface_alias, p95_rx_bps, p95_tx_bps, p95_total_bps, speed_bps = row
            else:
                host_name = None
                iface_name, iface_alias, p95_rx_bps, p95_tx_bps, p95_total_bps, speed_bps = row
            speed = float(speed_bps or 0)
            p95_total = float(p95_total_bps or 0)
            utilization_pct = (p95_total / speed * 100.0) if speed > 0 else 0.0
            items.append(
                {
                    "host": host_name,
                    "interface_name": iface_name,
                    "interface_alias": iface_alias,
                    "p95_rx_bps": float(p95_rx_bps or 0),
                    "p95_tx_bps": float(p95_tx_bps or 0),
                    "p95_total_bps": p95_total,
                    "speed_bps": speed,
                    "utilization_pct": float(utilization_pct),
                }
            )
        if include_total and not total:
            total = len(items)
        return items, total

    def get_network_interface_table(
        self,
        dc_code: str,
        time_range: dict | None = None,
        manufacturer: str | None = None,
        device_role: str | None = None,
        device_name: str | None = None,
        page: int = 1,
        page_size: int = 50,
        search: str | None = None,
        interface_scope: str | None = None,
    ) -> dict:
        """
        Return a paginated, searchable table of interface p95 utilization stats.
        """
        tr = time_range or default_time_range()
        dc_target = (dc_code or "").upper()
        if not dc_target:
            return {"items": [], "total": 0, "page": 1, "page_size": page_size}

        page_safe = max(1, int(page or 1))
        page_size_safe = max(1, min(200, int(page_size or 50)))
        offset = (page_safe - 1) * page_size_safe
        search_val = (search or "").strip()
        like = f"%{search_val}%"

        hosts, scope_key = self._resolve_network_interface_hosts(
            dc_target,
            tr,
            interface_scope,
            manufacturer=manufacturer,
            device_role=device_role,
            device_name=device_name,
        )

        cache_key = (
            f"dc_zabbix_net_iface_table:{dc_target}:"
            f"{manufacturer or ''}:{device_role or ''}:{device_name or ''}:"
            f"scope={scope_key}:p={page_safe}:ps={page_size_safe}:q={search_val}:"
            f"{tr.get('start','')}:{tr.get('end','')}"
        )
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        if not hosts:
            result = {
                "items": [],
                "total": 0,
                "page": page_safe,
                "page_size": page_size_safe,
                "interface_scope": scope_key,
            }
            cache.set(cache_key, result)
            return result

        start_ts, end_ts = time_range_to_bounds(tr)
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SET statement_timeout = '90000'")
                    sql = znq.build_interface_bandwidth_table_p95_sql(interface_scope)
                    rows = self._run_rows(
                        cur,
                        sql,
                        (
                            hosts,
                            start_ts,
                            end_ts,
                            search_val,
                            like,
                            like,
                            like,
                            page_size_safe,
                            offset,
                        ),
                    )

            items, total = self._network_p95_rows_to_items(rows, include_total=True)
            result = {
                "items": items,
                "total": total,
                "page": page_safe,
                "page_size": page_size_safe,
                "search": search_val,
                "interface_scope": scope_key,
            }
            if scope_key == "backbone":
                price_meta = self.get_network_dc_access_unit_price_tl()
                result["items"] = self._apply_backbone_billing(result["items"], price_meta)
                result["billing"] = self._backbone_billing_response_meta(price_meta)
        except Exception as exc:
            logger.warning("get_network_interface_table failed for %s: %s", dc_target, exc)
            result = {
                "items": [],
                "total": 0,
                "page": page_safe,
                "page_size": page_size_safe,
                "search": search_val,
                "interface_scope": scope_key,
            }

        cache.set(cache_key, result)
        return result

    def get_network_interface_export(
        self,
        dc_code: str,
        time_range: dict | None = None,
        manufacturer: str | None = None,
        device_role: str | None = None,
        device_name: str | None = None,
        search: str | None = None,
        interface_scope: str | None = None,
    ) -> dict:
        """Return all interface p95 rows for billing export (capped)."""
        tr = time_range or default_time_range()
        dc_target = (dc_code or "").upper()
        if not dc_target:
            return {"items": [], "total": 0, "interface_scope": "overview"}

        search_val = (search or "").strip()
        like = f"%{search_val}%"
        hosts, scope_key = self._resolve_network_interface_hosts(
            dc_target,
            tr,
            interface_scope,
            manufacturer=manufacturer,
            device_role=device_role,
            device_name=device_name,
        )

        cache_key = (
            f"dc_zabbix_net_iface_export:{dc_target}:"
            f"{manufacturer or ''}:{device_role or ''}:{device_name or ''}:"
            f"scope={scope_key}:q={search_val}:"
            f"{tr.get('start','')}:{tr.get('end','')}"
        )
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        if not hosts:
            result = {"items": [], "total": 0, "interface_scope": scope_key}
            cache.set(cache_key, result)
            return result

        start_ts, end_ts = time_range_to_bounds(tr)
        max_rows = znq.INTERFACE_EXPORT_MAX_ROWS
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SET statement_timeout = '120000'")
                    sql = znq.build_interface_bandwidth_table_p95_export_sql(interface_scope)
                    rows = self._run_rows(
                        cur,
                        sql,
                        (
                            hosts,
                            start_ts,
                            end_ts,
                            search_val,
                            like,
                            like,
                            like,
                            max_rows,
                        ),
                    )

            items, total = self._network_p95_rows_to_items(rows, include_total=False)
            result = {
                "items": items,
                "total": len(items),
                "interface_scope": scope_key,
                "export_cap": max_rows,
            }
            if scope_key == "backbone":
                price_meta = self.get_network_dc_access_unit_price_tl()
                result["items"] = self._apply_backbone_billing(result["items"], price_meta)
                result["billing"] = self._backbone_billing_response_meta(price_meta)
        except Exception as exc:
            logger.warning("get_network_interface_export failed for %s: %s", dc_target, exc)
            result = {"items": [], "total": 0, "interface_scope": scope_key, "export_cap": max_rows}

        cache.set(cache_key, result)
        return result

    def get_network_firewall_summary(self, dc_code: str, time_range: dict | None = None) -> dict:
        tr = time_range or default_time_range()
        dc_target = (dc_code or "").upper()
        if not dc_target:
            return {"devices": []}

        cache_key = f"dc_zabbix_net_firewall:{dc_target}:{tr.get('start','')}:{tr.get('end','')}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        start_ts, end_ts = time_range_to_bounds(tr)
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    rows = self._run_rows(cur, znq.FIREWALL_SUMMARY_LATEST, (start_ts, end_ts, dc_target))
            devices = [
                {
                    "host": row[0],
                    "device_name": row[1],
                    "manufacturer_name": row[2],
                    "cpu_utilization_pct": float(row[3] or 0),
                    "memory_utilization_pct": float(row[4] or 0),
                    "active_sessions": int(row[5] or 0),
                    "session_setup_rate": float(row[6] or 0),
                    "intrusions_detected": int(row[7] or 0),
                    "intrusions_blocked": int(row[8] or 0),
                    "ha_mode": row[9],
                    "ha_cluster_name": row[10],
                    "icmp_status": row[11],
                    "icmp_loss_pct": float(row[12] or 0),
                }
                for row in (rows or [])
            ]
            result = {"devices": devices}
        except Exception as exc:
            logger.warning("get_network_firewall_summary failed for %s: %s", dc_target, exc)
            result = {"devices": []}

        cache.set(cache_key, result)
        return result

    def get_network_load_balancer_summary(self, dc_code: str, time_range: dict | None = None) -> dict:
        tr = time_range or default_time_range()
        dc_target = (dc_code or "").upper()
        if not dc_target:
            return {"devices": []}

        cache_key = f"dc_zabbix_net_lb:{dc_target}:{tr.get('start','')}:{tr.get('end','')}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        start_ts, end_ts = time_range_to_bounds(tr)
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    rows = self._run_rows(cur, znq.LOAD_BALANCER_SUMMARY_LATEST, (start_ts, end_ts, dc_target))
            devices = [
                {
                    "host": row[0],
                    "device_name": row[1],
                    "manufacturer_name": row[2],
                    "icmp_status": row[3],
                    "icmp_loss_pct": float(row[4] or 0),
                    "icmp_response_time_ms": float(row[5] or 0),
                    "cpu_utilization_pct": float(row[6] or 0),
                    "memory_utilization_pct": float(row[7] or 0),
                    "uptime_seconds": int(row[8] or 0),
                    "total_ports_count": int(row[9] or 0),
                    "active_ports_count": int(row[10] or 0),
                }
                for row in (rows or [])
            ]
            result = {"devices": devices}
        except Exception as exc:
            logger.warning("get_network_load_balancer_summary failed for %s: %s", dc_target, exc)
            result = {"devices": []}

        cache.set(cache_key, result)
        return result

    # ------------------------------------------------------------------
    # Zabbix Intel Storage Dashboard (capacity planning + disk health)
    # ------------------------------------------------------------------

    def get_datastore_mapping(self, dc_code: str, time_range: dict | None = None) -> dict:
        """
        Return all VMware datastores for a DC with capacity/usage, per-host mount
        mapping (eşleştirme) and static inventory detail (VMFS / NAS).

        Backed by three datalake tables joined on datastore_moid:
          raw_vmware_datastore_metrics_agg      — capacity / usage / host & vm counts
          raw_vmware_datastore_host_mount       — datastore ↔ host mounts
          discovery_vmware_inventory_datastore  — VMFS version / NAS path / status

        Shape:
          {
            "datastore_count": int,
            "datastores": [
              { ...metrics..., ...inventory..., "hosts": [ {host_name, mount_path, ...} ] }
            ]
          }
        """
        tr = time_range or default_time_range()
        # Datastore tables are a one-shot snapshot; pin the window's end to the
        # latest ingested timestamp (like get_dc_details) so a relative preset
        # keeps finding the data instead of zeroing out as wall-clock advances.
        if tr.get("anchor_latest"):
            tr = self._smart_1h_tr(tr)
        dc_target = (dc_code or "").upper()
        start_ts, end_ts = time_range_to_bounds(tr)

        cache_key = f"dc_datastore_mapping:{dc_target}:{tr.get('start','')}:{tr.get('end','')}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    metric_rows = self._run_rows(
                        cur, vdq.DATASTORE_METRICS, (dc_target, start_ts, end_ts)
                    )
                    mount_rows = self._run_rows(
                        cur,
                        vdq.DATASTORE_HOST_MOUNTS,
                        (start_ts, end_ts, dc_target, start_ts, end_ts),
                    )
                    inv_rows = self._run_rows(cur, vdq.DATASTORE_INVENTORY, None)

            # Inventory detail keyed by datastore moid (component_moid).
            inv_by_moid: dict[str, dict[str, Any]] = {}
            for (
                moid,
                inv_type,
                capacity_gb,
                status,
                status_description,
                vmfs_uuid,
                vmfs_version,
                vmfs_block_size_mb,
                nas_remote_host,
                nas_remote_path,
                nas_type,
            ) in (inv_rows or []):
                inv_by_moid[moid] = {
                    "type": inv_type,
                    "capacity_gb": float(capacity_gb) if capacity_gb is not None else None,
                    "status": status,
                    "status_description": status_description,
                    "vmfs_uuid": vmfs_uuid,
                    "vmfs_version": vmfs_version,
                    "vmfs_block_size_mb": int(vmfs_block_size_mb)
                    if vmfs_block_size_mb is not None
                    else None,
                    "nas_remote_host": nas_remote_host,
                    "nas_remote_path": nas_remote_path,
                    "nas_type": nas_type,
                }

            # Host mounts grouped by datastore moid (the eşleştirme).
            mounts_by_ds: dict[str, list[dict[str, Any]]] = {}
            for (
                ds_moid,
                host_moid,
                host_name,
                mount_path,
                access_mode,
                mounted,
                accessible,
                inaccessible_reason,
            ) in (mount_rows or []):
                mounts_by_ds.setdefault(ds_moid, []).append(
                    {
                        "host_moid": host_moid,
                        "host_name": host_name or "Unknown",
                        "mount_path": mount_path,
                        "access_mode": access_mode,
                        "mounted": bool(mounted) if mounted is not None else None,
                        "accessible": bool(accessible) if accessible is not None else None,
                        "inaccessible_reason": inaccessible_reason,
                    }
                )

            datastores: list[dict[str, Any]] = []
            for (
                ds_moid,
                ds_name,
                datacenter_name,
                ds_type,
                capacity_bytes,
                free_bytes,
                used_bytes,
                uncommitted_bytes,
                used_percent,
                accessible,
                maintenance_mode,
                multiple_host_access,
                host_count,
                vm_count,
            ) in (metric_rows or []):
                inv = inv_by_moid.get(ds_moid, {})
                hosts = sorted(
                    mounts_by_ds.get(ds_moid, []),
                    key=lambda h: (h.get("host_name") or ""),
                )
                # IBM-backed datastores carry 'IBM' in their name; their capacity
                # is shared with the Power architecture (sellable range model).
                backing = "ibm" if "ibm" in (ds_name or "").lower() else "intel"
                datastores.append(
                    {
                        "datastore_moid": ds_moid,
                        "datastore_name": ds_name or "Unknown",
                        "datacenter_name": datacenter_name,
                        "backing": backing,
                        "type": ds_type or inv.get("type"),
                        "capacity_bytes": int(capacity_bytes or 0),
                        "free_bytes": int(free_bytes or 0),
                        "used_bytes": int(used_bytes or 0),
                        "uncommitted_bytes": int(uncommitted_bytes or 0),
                        "used_percent": float(used_percent or 0.0),
                        "accessible": bool(accessible) if accessible is not None else None,
                        "maintenance_mode": maintenance_mode,
                        "multiple_host_access": bool(multiple_host_access)
                        if multiple_host_access is not None
                        else None,
                        "host_count": int(host_count or 0),
                        "vm_count": int(vm_count or 0),
                        "status": inv.get("status"),
                        "status_description": inv.get("status_description"),
                        "vmfs_version": inv.get("vmfs_version"),
                        "vmfs_block_size_mb": inv.get("vmfs_block_size_mb"),
                        "nas_remote_host": inv.get("nas_remote_host"),
                        "nas_remote_path": inv.get("nas_remote_path"),
                        "nas_type": inv.get("nas_type"),
                        "hosts": hosts,
                    }
                )

            datastores.sort(key=lambda d: d.get("capacity_bytes", 0), reverse=True)
            result = {"datastore_count": len(datastores), "datastores": datastores}
        except (OperationalError, PoolError) as exc:
            logger.warning("get_datastore_mapping failed for %s: %s", dc_target, exc)
            result = {"datastore_count": 0, "datastores": []}

        cache.set(cache_key, result)
        return result

    def get_zabbix_storage_devices(self, dc_code: str, time_range: dict | None = None) -> list[dict[str, Any]]:
        """
        Return latest Zabbix storage device rows for the given DC.

        Used as Intel Storage device selector data. Each returned item corresponds
        to a resolved NetBox device mapped to a Zabbix host (via loki_id).
        """
        tr = time_range or default_time_range()
        dc_target = (dc_code or "").upper()
        start_ts, end_ts = time_range_to_bounds(tr)

        cache_key = f"dc_zabbix_storage_devices:{dc_target}:{tr.get('start','')}:{tr.get('end','')}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    rows = self._run_rows(
                        cur,
                        zsq.STORAGE_DEVICES_FOR_DC_LATEST,
                        (start_ts, end_ts, dc_target),
                    )

            devices: list[dict[str, Any]] = []
            for (
                loki_id,
                host,
                storage_device_name,
                manufacturer_name,
                device_role_name,
                _location_name,
                _site_name,
                total_capacity_bytes,
                used_capacity_bytes,
                free_capacity_bytes,
                health_status,
                _collection_ts,
            ) in (rows or []):
                devices.append(
                    {
                        "loki_id": str(loki_id) if loki_id is not None else None,
                        "host": str(host) if host is not None else None,
                        "device_name": storage_device_name or "Unknown",
                        "manufacturer_name": manufacturer_name or "Unknown",
                        "device_role_name": device_role_name or "Unknown",
                        "total_capacity_bytes": int(total_capacity_bytes or 0),
                        "used_capacity_bytes": int(used_capacity_bytes or 0),
                        "free_capacity_bytes": int(free_capacity_bytes or 0),
                        "health_status": health_status,
                    }
                )

            excluded_roles = self._excluded_roles_for_scope("datacenter")
            if excluded_roles:
                devices = filter_devices_by_role_exclusion(devices, excluded_roles)

            devices.sort(key=lambda d: d.get("total_capacity_bytes", 0), reverse=True)
            result = devices
        except (OperationalError, PoolError) as exc:
            logger.warning("get_zabbix_storage_devices failed for %s: %s", dc_target, exc)
            result = []

        cache.set(cache_key, result)
        return result

    def get_zabbix_storage_capacity(
        self,
        dc_code: str,
        time_range: dict | None = None,
        host: str | None = None,
    ) -> dict:
        """
        Return total/used/free capacity for Zabbix storage devices within a DC.
        """
        tr = time_range or default_time_range()
        dc_target = (dc_code or "").upper()
        start_ts, end_ts = time_range_to_bounds(tr)

        cache_key = (
            f"dc_zabbix_storage_cap:{dc_target}:"
            f"{tr.get('start','')}:{tr.get('end','')}:{host or ''}"
        )
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    rows = self._run_rows(
                        cur,
                        zsq.STORAGE_DEVICES_FOR_DC_LATEST,
                        (start_ts, end_ts, dc_target),
                    )

            if host is not None:
                rows = [r for r in (rows or []) if r and r[1] and str(r[1]) == str(host)]

            excluded_roles = self._excluded_roles_for_scope("datacenter")
            if excluded_roles:
                rows = [
                    r for r in (rows or [])
                    if r and not is_role_excluded(r[4] if len(r) > 4 else None, excluded_roles)
                ]

            # STORAGE_DEVICES_FOR_DC_LATEST select order:
            # 0:loki_id, 1:host, 2:storage_device_name, 3:manufacturer, 4:device_role,
            # 5:location_name, 6:site_name, 7:total_capacity_bytes, 8:used, 9:free, ...
            total_capacity = sum(int(r[7] or 0) for r in (rows or []))
            used_capacity = sum(int(r[8] or 0) for r in (rows or []))
            free_capacity = sum(int(r[9] or 0) for r in (rows or []))
            device_count = len(rows or [])

            result = {
                "storage_device_count": int(device_count),
                "total_capacity_bytes": int(total_capacity),
                "used_capacity_bytes": int(used_capacity),
                "free_capacity_bytes": int(free_capacity),
            }
        except (OperationalError, PoolError) as exc:
            logger.warning("get_zabbix_storage_capacity failed for %s: %s", dc_target, exc)
            result = {"storage_device_count": 0, "total_capacity_bytes": 0, "used_capacity_bytes": 0, "free_capacity_bytes": 0}

        cache.set(cache_key, result)
        return result

    def get_zabbix_storage_trend(
        self,
        dc_code: str,
        time_range: dict | None = None,
        host: str | None = None,
    ) -> dict:
        """
        Return daily capacity utilization trend (used/total) for a DC.
        """
        tr = time_range or default_time_range()
        dc_target = (dc_code or "").upper()
        start_ts, end_ts = time_range_to_bounds(tr)

        cache_key = (
            f"dc_zabbix_storage_trend:{dc_target}:"
            f"{tr.get('start','')}:{tr.get('end','')}:{host or ''}"
        )
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    rows = self._run_rows(
                        cur,
                        zsq.STORAGE_DEVICES_FOR_DC_LATEST,
                        (start_ts, end_ts, dc_target),
                    )

                    if host is not None:
                        hosts = sorted({str(r[1]) for r in (rows or []) if r and r[1] and str(r[1]) == str(host)})
                    else:
                        hosts = sorted({str(r[1]) for r in (rows or []) if r and r[1]})
                    if not hosts:
                        result = {"series": []}
                        cache.set(cache_key, result)
                        return result

                    trend_rows = self._run_rows(
                        cur,
                        zsq.STORAGE_CAPACITY_TREND_DAILY,
                        (hosts, start_ts, end_ts),
                    )

            series = []
            for ts, used_bytes, total_bytes in (trend_rows or []):
                used_val = float(used_bytes or 0)
                total_val = float(total_bytes or 0)
                used_pct = (used_val / total_val * 100.0) if total_val > 0 else 0.0
                series.append(
                    {
                        "ts": ts,
                        "used_capacity_bytes": used_val,
                        "total_capacity_bytes": total_val,
                        "used_pct": float(used_pct),
                    }
                )

            result = {"series": series}
        except (OperationalError, PoolError) as exc:
            logger.warning("get_zabbix_storage_trend failed for %s: %s", dc_target, exc)
            result = {"series": []}

        cache.set(cache_key, result)
        return result

    def get_zabbix_disk_list(
        self,
        dc_code: str,
        time_range: dict | None = None,
        host: str | None = None,
    ) -> dict:
        """
        Return distinct disk names for the selected storage host within the given DC.
        """
        if host is None:
            return {"items": []}

        tr = time_range or default_time_range()
        dc_target = (dc_code or "").upper()
        start_ts, end_ts = time_range_to_bounds(tr)

        cache_key = f"dc_zabbix_disk_list:{dc_target}:{host}:{tr.get('start','')}:{tr.get('end','')}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    # Validate host belongs to this DC (scoping).
                    dev_rows = self._run_rows(
                        cur,
                        zsq.STORAGE_DEVICES_FOR_DC_LATEST,
                        (start_ts, end_ts, dc_target),
                    )
                    valid_hosts = {str(r[1]) for r in (dev_rows or []) if r and r[1]}
                    if str(host) not in valid_hosts:
                        result = {"items": []}
                        cache.set(cache_key, result)
                        return result

                    disk_rows = self._run_rows(
                        cur,
                        zsq.STORAGE_DISK_LIST_BY_HOST,
                        ([str(host)], start_ts, end_ts),
                    )

            items: list[str] = [str(r[0]) for r in (disk_rows or []) if r and r[0]]
            items = sorted(set(items))
            result = {"items": items}
        except (OperationalError, PoolError) as exc:
            logger.warning("get_zabbix_disk_list failed for %s/%s: %s", dc_target, host, exc)
            result = {"items": []}

        cache.set(cache_key, result)
        return result

    def get_zabbix_disk_trend(
        self,
        dc_code: str,
        time_range: dict | None = None,
        host: str | None = None,
        disk_name: str | None = None,
    ) -> dict:
        """
        Return daily disk trend series (latest per host/day) for a given disk.
        """
        if host is None or not disk_name:
            return {"series": []}

        tr = time_range or default_time_range()
        dc_target = (dc_code or "").upper()
        start_ts, end_ts = time_range_to_bounds(tr)

        cache_key = (
            f"dc_zabbix_disk_trend:{dc_target}:{host}:{disk_name}:"
            f"{tr.get('start','')}:{tr.get('end','')}"
        )
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    # Validate host belongs to this DC (scoping).
                    dev_rows = self._run_rows(
                        cur,
                        zsq.STORAGE_DEVICES_FOR_DC_LATEST,
                        (start_ts, end_ts, dc_target),
                    )
                    valid_hosts = {str(r[1]) for r in (dev_rows or []) if r and r[1]}
                    if str(host) not in valid_hosts:
                        result = {"series": []}
                        cache.set(cache_key, result)
                        return result

                    trend_rows = self._run_rows(
                        cur,
                        zsq.STORAGE_DISK_TREND_DAILY,
                        ([str(host)], str(disk_name), start_ts, end_ts),
                    )

            series: list[dict[str, Any]] = []
            for ts, avg_iops, avg_latency_ms, total_capacity_bytes, free_capacity_bytes in (trend_rows or []):
                series.append(
                    {
                        "ts": ts,
                        "avg_iops": float(avg_iops or 0),
                        "avg_latency_ms": float(avg_latency_ms or 0),
                        "total_capacity_bytes": int(total_capacity_bytes or 0),
                        "free_capacity_bytes": int(free_capacity_bytes or 0),
                    }
                )
            result = {"series": series}
        except (OperationalError, PoolError) as exc:
            logger.warning("get_zabbix_disk_trend failed for %s/%s/%s: %s", dc_target, host, disk_name, exc)
            result = {"series": []}

        cache.set(cache_key, result)
        return result

    def get_zabbix_disk_health(self, dc_code: str, time_range: dict | None = None) -> dict:
        """
        Return a summary table of disk health/performance for a DC.
        """
        tr = time_range or default_time_range()
        dc_target = (dc_code or "").upper()
        start_ts, end_ts = time_range_to_bounds(tr)

        cache_key = f"dc_zabbix_disk_health:{dc_target}:{tr.get('start','')}:{tr.get('end','')}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        try:
            limit = 500
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    rows = self._run_rows(
                        cur,
                        zsq.STORAGE_DEVICES_FOR_DC_LATEST,
                        (start_ts, end_ts, dc_target),
                    )
                    hosts = sorted({str(r[1]) for r in (rows or []) if r and r[1]})

                    if not hosts:
                        result = {"items": []}
                        cache.set(cache_key, result)
                        return result

                    disk_rows = self._run_rows(
                        cur,
                        zsq.DISK_HEALTH_PERFORMANCE,
                        (hosts, start_ts, end_ts, hosts, start_ts, end_ts, limit),
                    )

            items: list[dict] = []
            for (
                disk_name,
                health_status,
                avg_total_iops,
                avg_latency_ms,
                avg_temperature_c,
                running_status,
            ) in (disk_rows or []):
                items.append(
                    {
                        "disk_name": disk_name,
                        "health_status": health_status,
                        "avg_total_iops": float(avg_total_iops or 0),
                        "avg_latency_ms": float(avg_latency_ms or 0),
                        "avg_temperature_c": float(avg_temperature_c or 0),
                        "running_status": running_status,
                    }
                )

            result = {"items": items}
        except (OperationalError, PoolError) as exc:
            logger.warning("get_zabbix_disk_health failed for %s: %s", dc_target, exc)
            result = {"items": []}

        cache.set(cache_key, result)
        return result

    def get_san_bottleneck(self, dc_code: str, time_range: dict | None = None) -> dict:
        """
        Return latest SAN bottleneck issues (raw_brocade_san_fcport_1).

        DC association is inferred from `portname` using DC regex.
        """
        dc_target = (dc_code or "").upper()
        # Bottleneck uses latest snapshot; time_range is kept in signature for API consistency.
        tr = time_range or default_time_range()

        cache_key = f"dc_san_bottleneck:{dc_target}:{tr.get('start','')}:{tr.get('end','')}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    rows = self._run_rows(cur, brq.SAN_FCPORT_LATEST, (200,))

            issues: list[dict] = []
            for portname, notxcredits, toomanyrdys, ts in (rows or []):
                if not portname:
                    continue
                match = _DC_CODE_RE.search(str(portname).upper())
                if not match:
                    continue
                code = match.group(1).upper()
                if code != dc_target:
                    continue

                issues.append(
                    {
                        "portname": portname,
                        "swfcportnotxcredits": int(notxcredits or 0),
                        "swfcporttoomanyrdys": int(toomanyrdys or 0),
                        "timestamp": ts,
                    }
                )

            # Sort by severity score
            issues.sort(
                key=lambda x: (x["swfcportnotxcredits"] + x["swfcporttoomanyrdys"]),
                reverse=True,
            )
            top_issues = issues[:10]
            result = {"has_issue": bool(top_issues), "issues": top_issues}
        except (OperationalError, PoolError) as exc:
            logger.warning("get_san_bottleneck failed for %s: %s", dc_target, exc)
            result = {"has_issue": False, "issues": []}

        cache.set(cache_key, result)
        return result

    # ------------------------------------------------------------------
    # Physical Inventory (discovery_netbox_inventory_device)
    # ------------------------------------------------------------------

    def get_netbox_device_roles(self) -> list[dict]:
        """Return distinct active device roles for Settings multi-select."""
        cache_key = "netbox:device_roles"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    rows = self._run_rows(cur, nbq.DISTINCT_DEVICE_ROLES)
            result = [{"role": r[0]} for r in (rows or []) if r and r[0]]
        except (OperationalError, PoolError) as exc:
            logger.warning("get_netbox_device_roles failed: %s", exc)
            result = []
        cache.set(cache_key, result, ttl=3600)
        return result

    # ------------------------------------------------------------------
    # Physical Inventory — raw data loaders (SQL-side)
    # ------------------------------------------------------------------

    def _get_physical_inventory_raw(self, *, force: bool = False) -> list[dict]:
        """
        Fetch active physical devices (status_value = 'active', latest snapshot per device key).
        Result is cached; all derived methods use this single dataset.
        No JOINs, no aggregations — DISTINCT ON with SQL-side status filter.
        """
        cache_key = "phys_inv:raw_devices"
        if not force:
            cached_val = cache.get(cache_key)
            if cached_val is not None:
                return cached_val
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    rows = self._run_rows(cur, cq.PHYSICAL_INVENTORY_ALL_DEVICES)
            devices = [
                {
                    "id": r[0],
                    "name": r[1],
                    "device_type_name": r[2],
                    "manufacturer_name": r[3] or "Unknown",
                    "device_role_name": r[4] or "Unknown",
                    "tenant_id": r[5],
                    "site_id": r[6],
                    "site_name": r[7] or "",
                    "location_id": r[8],
                    "location_name": r[9] or "",
                }
                for r in (rows or [])
            ]
            cache.set(cache_key, devices)
            return devices
        except (OperationalError, PoolError) as exc:
            logger.warning("_get_physical_inventory_raw failed: %s", exc)
            return []

    def _get_location_dc_map(self, *, force: bool = False) -> dict[str, str]:
        """
        Fetch loki location_name → dc_name mapping (from loki_locations).
        Cached in memory; used for in-Python location resolution (no SQL JOINs needed).
        """
        cache_key = "loki:location_dc_map"
        if not force:
            cached_val = cache.get(cache_key)
            if cached_val is not None:
                return cached_val
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    rows = self._run_rows(cur, lq.LOCATION_DC_MAP)
            loc_map = {r[0]: r[1] for r in (rows or []) if r[0] and r[1]}
            cache.set(cache_key, loc_map)
            return loc_map
        except (OperationalError, PoolError) as exc:
            logger.warning("_get_location_dc_map failed: %s", exc)
            return {}

    @staticmethod
    def _resolve_device_location(device: dict, loc_map: dict[str, str]) -> str:
        """Resolve DC-level location name for a device using the in-memory loki map."""
        loc = device.get("location_name") or ""
        if loc:
            dc = loc_map.get(loc)
            if dc:
                return dc
            return loc
        return device.get("site_name") or "Unknown"

    # ------------------------------------------------------------------
    # Physical Inventory — derived views (Python-side aggregation)
    # ------------------------------------------------------------------

    def _excluded_roles_for_scope(self, scope: str, *, webui=None) -> set[str]:
        pool = webui if webui is not None else getattr(self, "_webui", None)
        return load_excluded_roles(pool, scope)

    def _filter_phys_inventory_devices(
        self,
        devices: list[dict],
        scope: str,
        *,
        webui=None,
    ) -> list[dict]:
        excluded = self._excluded_roles_for_scope(scope, webui=webui)
        return filter_devices_by_role_exclusion(devices, excluded)

    def get_physical_inventory_customer(
        self,
        customer_name: str | None = None,
        *,
        webui=None,
    ) -> list[dict]:
        """Return physical device list for a CRM customer tenant scope (cached)."""
        normalized = (customer_name or "").strip()
        cache_key = f"phys_inv:customer:{normalized.casefold() or 'boyner_legacy'}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        tenant_ids, text_rules = self._resolve_physical_customer_filters(normalized, webui=webui)
        devices = self._filter_phys_inventory_devices(
            self._get_physical_inventory_raw(),
            "customer",
            webui=webui,
        )
        loc_map = self._get_location_dc_map()

        def _matches_device(device: dict) -> bool:
            if tenant_ids and device.get("tenant_id") in tenant_ids:
                return True
            tenant_name = str(device.get("tenant_name") or "")
            tenant_key = tenant_name.casefold()
            for method, value in text_rules:
                needle = (value or "").strip()
                if not needle:
                    continue
                key = needle.casefold()
                if method == "exact" and tenant_key == key:
                    return True
                if method == "prefix" and tenant_key.startswith(key):
                    return True
                if method == "suffix" and tenant_key.endswith(key):
                    return True
                if method in {"contains", "id_exact"} and key in tenant_key:
                    return True
            return False

        if not tenant_ids and not text_rules:
            # Legacy Boyner fallback when mappings are unavailable.
            if normalized and "boyner" not in normalized.casefold():
                result: list[dict] = []
                cache.set(cache_key, result)
                return result
            tenant_ids = {5}

        result = [
            {
                "name": d["name"],
                "device_role_name": d["device_role_name"],
                "manufacturer_name": d["manufacturer_name"],
                "location": self._resolve_device_location(d, loc_map),
            }
            for d in devices
            if _matches_device(d)
        ]
        result.sort(key=lambda x: (x["device_role_name"], x["name"]))
        cache.set(cache_key, result)
        return result

    @staticmethod
    def _resolve_physical_customer_filters(
        customer_name: str,
        *,
        webui=None,
    ) -> tuple[set[int], list[tuple[str, str]]]:
        tenant_ids: set[int] = set()
        text_rules: list[tuple[str, str]] = []
        if not customer_name:
            tenant_ids.add(5)
            return tenant_ids, text_rules

        account_id = None
        if webui is not None and getattr(webui, "is_available", False):
            try:
                resolved = webui.run_one(
                    crm_q.WEBUI_RESOLVE_ACCOUNTID_BY_DISPLAY_NAME,
                    (customer_name, customer_name, customer_name),
                )
                if resolved and resolved.get("crm_accountid"):
                    account_id = str(resolved["crm_accountid"])
            except Exception as exc:
                logger.warning("Physical inventory alias resolve failed: %s", exc)

        mapping_rows: list[dict] = []
        if account_id and webui is not None and getattr(webui, "is_available", False):
            try:
                mapping_rows = webui.run_rows(
                    crm_q.WEBUI_PHYSICAL_MAPPINGS_FOR_ACCOUNT,
                    (account_id,),
                )
            except Exception as exc:
                logger.warning("Physical inventory mapping load failed: %s", exc)

        for row in mapping_rows:
            method = str(row.get("match_method") or "contains").strip().lower()
            value = str(row.get("match_value") or "").strip()
            if not value:
                continue
            if method == "id_exact":
                try:
                    tenant_ids.add(int(value))
                except ValueError:
                    text_rules.append((method, value))
            else:
                text_rules.append((method, value))

        if not tenant_ids and not text_rules and "boyner" in customer_name.casefold():
            tenant_ids.add(5)
        return tenant_ids, text_rules

    def get_physical_inventory_dc(self, dc_name: str) -> dict:
        """Return physical inventory for a DC: total, by_role, by_role_manufacturer (cached)."""
        empty: dict = {"total": 0, "by_role": [], "by_role_manufacturer": []}
        if not dc_name or not dc_name.strip():
            return empty
        dc_key = dc_name.strip().lower()
        cache_key = f"phys_inv:dc:{dc_key}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        devices = self._filter_phys_inventory_devices(self._get_physical_inventory_raw(), "datacenter")
        loc_map = self._get_location_dc_map()

        def _matches_dc(d: dict) -> bool:
            resolved = self._resolve_device_location(d, loc_map).lower()
            site = (d.get("site_name") or "").lower()
            return dc_key in resolved or dc_key in site

        dc_devices = [d for d in devices if _matches_dc(d)]

        # by_role
        role_counts: dict[str, int] = {}
        for d in dc_devices:
            role_counts[d["device_role_name"]] = role_counts.get(d["device_role_name"], 0) + 1
        by_role = sorted(
            [{"role": k, "count": v} for k, v in role_counts.items()],
            key=lambda x: x["count"], reverse=True,
        )

        # by_role_manufacturer
        rm_counts: dict[tuple[str, str], int] = {}
        for d in dc_devices:
            key = (d["device_role_name"], d["manufacturer_name"])
            rm_counts[key] = rm_counts.get(key, 0) + 1
        by_role_manufacturer = sorted(
            [{"role": k[0], "manufacturer": k[1], "count": v} for k, v in rm_counts.items()],
            key=lambda x: (x["role"], -x["count"]),
        )

        result = {"total": len(dc_devices), "by_role": by_role, "by_role_manufacturer": by_role_manufacturer}
        cache.set(cache_key, result)
        return result

    def get_physical_inventory_overview_by_role(self) -> list[dict]:
        """Return platform-wide device count by device_role_name (Overview level 0, cached)."""
        cache_key = "phys_inv:overview_by_role"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val
        devices = self._filter_phys_inventory_devices(self._get_physical_inventory_raw(), "datacenter")
        role_counts: dict[str, int] = {}
        for d in devices:
            role_counts[d["device_role_name"]] = role_counts.get(d["device_role_name"], 0) + 1
        result = sorted(
            [{"role": k, "count": v} for k, v in role_counts.items()],
            key=lambda x: x["count"], reverse=True,
        )
        cache.set(cache_key, result)
        return result

    def get_physical_inventory_overview_manufacturer(self, role: str) -> list[dict]:
        """Return manufacturer distribution for a device role (Overview drill level 1, cached)."""
        if not role or not role.strip():
            return []
        role_key = role.strip().lower()
        cache_key = f"phys_inv:manufacturer:{role_key}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val
        devices = self._filter_phys_inventory_devices(self._get_physical_inventory_raw(), "datacenter")
        mfr_counts: dict[str, int] = {}
        for d in devices:
            if d["device_role_name"].lower() == role_key:
                mfr = d["manufacturer_name"]
                mfr_counts[mfr] = mfr_counts.get(mfr, 0) + 1
        result = sorted(
            [{"manufacturer": k, "count": v} for k, v in mfr_counts.items()],
            key=lambda x: x["count"], reverse=True,
        )
        cache.set(cache_key, result)
        return result

    def get_physical_inventory_overview_location(self, role: str, manufacturer: str) -> list[dict]:
        """Return resolved DC-level location for role+manufacturer (Overview drill level 2, cached)."""
        if not role or not manufacturer:
            return []
        role_key = role.strip().lower()
        mfr_key = manufacturer.strip().lower()
        cache_key = f"phys_inv:location:{role_key}:{mfr_key}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val
        devices = self._filter_phys_inventory_devices(self._get_physical_inventory_raw(), "datacenter")
        loc_map = self._get_location_dc_map()
        loc_counts: dict[str, int] = {}
        for d in devices:
            if d["device_role_name"].lower() == role_key and d["manufacturer_name"].lower() == mfr_key:
                loc = self._resolve_device_location(d, loc_map)
                loc_counts[loc] = loc_counts.get(loc, 0) + 1
        result = sorted(
            [{"location": k, "count": v} for k, v in loc_counts.items()],
            key=lambda x: x["count"], reverse=True,
        )
        cache.set(cache_key, result)
        return result

    # ------------------------------------------------------------------
    # Cache warming / background refresh API
    # ------------------------------------------------------------------

    def warm_physical_inventory(self) -> None:
        """
        Pre-load physical inventory raw data and location map into cache.
        All derived views (overview, per-DC, customer) are computed from these two datasets.
        """
        logger.info("Warming physical inventory cache…")
        t0 = time.perf_counter()
        try:
            devices = self._get_physical_inventory_raw(force=True)
            self._get_location_dc_map(force=True)
            logger.info(
                "Physical inventory raw data loaded: %d devices. Computing derived views…",
                len(devices),
            )
            cache.delete_prefix("phys_inv:overview_by_role")
            cache.delete_prefix("phys_inv:customer_")
            cache.delete_prefix("phys_inv:dc:")
            cache.delete_prefix("phys_inv:manufacturer:")
            cache.delete_prefix("phys_inv:location:")
            self.get_physical_inventory_overview_by_role()
            self.get_physical_inventory_customer()
            for dc_code in self.dc_list:
                try:
                    self.get_physical_inventory_dc(dc_code)
                except Exception as exc:
                    logger.warning("PhysInv warm failed for DC %s: %s", dc_code, exc)
            logger.info("Physical inventory cache warm-up done in %.2fs.", time.perf_counter() - t0)
        except Exception as exc:
            logger.warning("Physical inventory cache warm-up failed: %s", exc)

    def get_dc_racks(self, dc_code: str) -> dict:
        empty = {"racks": [], "summary": {"total_racks": 0, "active_racks": 0, "total_u_height": 0, "racks_with_energy": 0, "racks_with_pdu": 0}}
        if not dc_code or not dc_code.strip():
            return empty
        cache_key = f"dc_racks:{dc_code.strip()}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        def _fetch():
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    rows = self._run_rows(cur, drq.RACKS_BY_DC, (dc_code, dc_code))
                    summary_row = self._run_row(cur, drq.RACK_SUMMARY_BY_DC, (dc_code, dc_code))
            columns = [
                "id", "name", "display_name", "status", "status_description",
                "u_height", "kabin_enerji", "pdu_a_ip", "pdu_b_ip", "rack_type",
                "serial", "asset_tag", "tenant_name", "facility_id",
                "weight", "max_weight", "weight_unit",
                "description", "comments",
                "first_observed", "last_observed", "location_id", "site_id",
                "hall_name",
            ]
            racks = []
            for r in (rows or []):
                rack = {}
                for i, col in enumerate(columns):
                    rack[col] = r[i] if i < len(r) else None
                if rack.get("first_observed"):
                    rack["first_observed"] = str(rack["first_observed"])
                if rack.get("last_observed"):
                    rack["last_observed"] = str(rack["last_observed"])
                racks.append(rack)
            s = summary_row or (0, 0, 0, 0, 0)
            summary = {
                "total_racks": int(s[0] or 0),
                "active_racks": int(s[1] or 0),
                "total_u_height": int(s[2] or 0),
                "racks_with_energy": int(s[3] or 0),
                "racks_with_pdu": int(s[4] or 0),
            }
            return {"racks": racks, "summary": summary}

        try:
            result = cache.run_singleflight(cache_key, _fetch, ttl=21600)
            return result
        except OperationalError as exc:
            logger.error("DB unavailable for get_dc_racks(%s): %s", dc_code, exc)
            return empty

    def get_rack_devices(self, rack_name: str) -> dict:
        """Return all devices installed in a specific rack (by name), with U position."""
        if not rack_name or not rack_name.strip():
            return {"devices": []}
        cache_key = f"rack_devices:{rack_name.strip()}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        def _fetch():
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    rows = self._run_rows(cur, drq.DEVICES_BY_RACK_NAME, (rack_name.strip(),))
            columns = ["name", "position", "face", "role", "device_type",
                       "status_value", "status_label", "manufacturer", "description"]
            devices = []
            for r in (rows or []):
                d = {}
                for i, col in enumerate(columns):
                    val = r[i] if i < len(r) else None
                    d[col] = float(val) if hasattr(val, '__float__') and col == "position" else val
                devices.append(d)
            return {"devices": devices}

        try:
            return cache.run_singleflight(cache_key, _fetch, ttl=21600)
        except OperationalError as exc:
            logger.error("DB unavailable for get_rack_devices(%s): %s", rack_name, exc)
            return {"devices": []}

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
            # Route through the public methods so smart_1h_tr normalisation
            # writes to the same cache keys the request handlers will read.
            self.get_all_datacenters_summary(tr)
            self.get_global_overview(tr)
            for cust in WARMED_CUSTOMERS:
                try:
                    self.get_customer_resources(cust, tr)
                except Exception as exc:
                    logger.warning("Customer cache warm-up for %s failed: %s", cust, exc)

            # Rack floor map data (time-range independent)
            try:
                for dc_code in self._dc_list:
                    self.get_dc_racks(dc_code)
            except Exception as exc:
                logger.warning("Rack cache warm-up failed: %s", exc)

            # Physical inventory (time-range independent)
            try:
                self.warm_physical_inventory()
            except Exception as exc:
                logger.warning("Physical inventory warm-up failed at startup: %s", exc)

            logger.info(
                "Cache warm-up complete for last 7d in %.2fs.",
                time.perf_counter() - t0,
            )
            # Host-level compute rows (Hosts panel + host-based sellable).
            try:
                for dc_code in self._dc_list:
                    self.get_classic_host_rows(dc_code, None, tr)
                    self.get_hyperconv_host_rows(dc_code, None, tr)
            except Exception as exc:
                logger.warning("Host rows cache warm-up failed: %s", exc)
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
                self.get_all_datacenters_summary(tr)
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

            for cust in WARMED_CUSTOMERS:
                try:
                    key_c = f"customer_s3:{cust}:{tr.get('start','')}:{tr.get('end','')}"
                    data_c = self._fetch_customer_s3_vaults(cust, start_ts, end_ts)
                    cache.set(key_c, data_c)
                except Exception as exc:
                    logger.warning("warm_s3_cache failed for customer %s: %s", cust, exc)

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
                self.get_all_datacenters_summary(tr)
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

                for cust in WARMED_CUSTOMERS:
                    try:
                        key_c = f"customer_s3:{cust}:{tr.get('start','')}:{tr.get('end','')}"
                        data_c = self._fetch_customer_s3_vaults(cust, start_ts, end_ts)
                        cache.set(key_c, data_c)
                    except Exception as exc:
                        logger.warning("refresh_s3_cache failed for customer %s: %s", cust, exc)

            logger.info("Background S3 cache refresh complete.")
        except Exception as exc:
            logger.error("Background S3 cache refresh failed: %s", exc)

    def refresh_backup_cache(self) -> None:
        """
        Refresh backup (NetBackup, Zerto, Veeam) cache for the standard reporting ranges.

        This is called by the background scheduler every 30 minutes. Cache entries
        are updated in place so UI panels continue to use the previous values until
        new data has been written. Capacity warm runs first (lighter, fast UX win),
        then jobs warm (heavier aggregations across 4 windows × 3 granularities)
        runs in a thread pool for parallelism.
        """
        logger.info("Background backup cache refresh started.")
        try:
            # ---- Capacity warm (existing) -----------------------------------
            for tr in cache_time_ranges():
                start_ts, end_ts = time_range_to_bounds(tr)
                for dc_code in self.dc_list:
                    try:
                        key_nb = f"dc_netbackup:{dc_code}:{tr.get('start','')}:{tr.get('end','')}"
                        data_nb = self._fetch_dc_netbackup_pools(dc_code, start_ts, end_ts)
                        cache.set(key_nb, data_nb)
                    except Exception as exc:
                        logger.warning("refresh_backup_cache (NetBackup) failed for DC %s: %s", dc_code, exc)

                    try:
                        key_z = f"dc_zerto:{dc_code}:{tr.get('start','')}:{tr.get('end','')}"
                        data_z = self._fetch_dc_zerto_sites(dc_code, start_ts, end_ts)
                        cache.set(key_z, data_z)
                    except Exception as exc:
                        logger.warning("refresh_backup_cache (Zerto) failed for DC %s: %s", dc_code, exc)

                    try:
                        key_v = f"dc_veeam:{dc_code}:{tr.get('start','')}:{tr.get('end','')}"
                        data_v = self._fetch_dc_veeam_repositories(dc_code, start_ts, end_ts)
                        cache.set(key_v, data_v)
                    except Exception as exc:
                        logger.warning("refresh_backup_cache (Veeam) failed for DC %s: %s", dc_code, exc)

            # ---- Jobs warm (new in Phase 3 A1) ------------------------------
            self._warm_backup_jobs_cache()

            logger.info("Background backup cache refresh complete.")
        except Exception as exc:
            logger.error("Background backup cache refresh failed: %s", exc)

    def _warm_network_cache_for_range(self, tr: dict) -> None:
        """Warm Zabbix network endpoints for one time range (unfiltered default view)."""
        for dc_code in self.dc_list:
            try:
                filters = self.get_network_filters(dc_code, tr)
                if not filters.get("manufacturers"):
                    continue
                self.get_network_port_summary(dc_code, tr)
                self.get_network_95th_percentile(dc_code, tr, top_n=20)
                self.get_network_interface_table(dc_code, tr, page=1, page_size=50)
            except Exception as exc:
                logger.warning("network cache warm failed for DC %s: %s", dc_code, exc)

    def warm_network_cache(self) -> None:
        """
        Warm Zabbix network cache for the default reporting range.

        Triggered once in the background after startup so Network panels open
        with data on first visit (same pattern as S3 warm-up).
        """
        logger.info("Warming network cache for default time range…")
        try:
            tr = default_time_range()
            self._warm_network_cache_for_range(tr)
            logger.info("Network cache warm-up complete for default range.")
        except Exception as exc:
            logger.warning("Network cache warm-up failed: %s", exc)

    def refresh_network_cache(self) -> None:
        """
        Refresh Zabbix network cache for the standard reporting ranges.

        Called by the background scheduler every 30 minutes. Entries are updated
        in place so the UI keeps serving previous values until new data is written.
        """
        logger.info("Background network cache refresh started.")
        try:
            for tr in cache_time_ranges():
                self._warm_network_cache_for_range(tr)
            logger.info("Background network cache refresh complete.")
        except Exception as exc:
            logger.error("Background network cache refresh failed: %s", exc)

    def _warm_backup_jobs_cache(self) -> None:
        """
        Warm Phase 1 backup-jobs endpoints for every vendor × window × granularity.

        Sadece (vendor × window × granularity) — toplam 36 task. Her task
        _compute_all_dc_<vendor>_jobs çağırır ve tek SQL pass'iyle TÜM DC'lere
        cache yazar. Eski sürümde 504 task vardı (DC döngüsü) — refactor sonrası
        14x azaldı.
        """
        windows = backup_jobs_warm_windows()
        grans = BACKUP_JOBS_WARM_GRANULARITIES
        if not self.dc_list:
            return

        tasks: list[tuple[str, Callable[[], Any]]] = []
        for tr in windows:
            start_ts, end_ts = time_range_to_bounds(tr)
            tr_start = str(tr.get("start", ""))
            tr_end = str(tr.get("end", ""))
            for gran in grans:
                tasks.append((
                    f"veeam:{tr['preset']}:{gran}",
                    lambda g=gran, s=start_ts, e=end_ts, ts=tr_start, te=tr_end:
                        self._compute_all_dc_veeam_jobs(g, s, e, ts, te),
                ))
                tasks.append((
                    f"zerto:{tr['preset']}:{gran}",
                    lambda g=gran, s=start_ts, e=end_ts, ts=tr_start, te=tr_end:
                        self._compute_all_dc_zerto_jobs(g, s, e, ts, te),
                ))
                tasks.append((
                    f"netbackup:{tr['preset']}:{gran}",
                    lambda g=gran, s=start_ts, e=end_ts, ts=tr_start, te=tr_end:
                        self._compute_all_dc_netbackup_jobs(g, s, e, ts, te),
                ))

        if not tasks:
            return

        logger.info(
            "Backup-jobs warm: %d tasks (windows=%d, grans=%d, vendors=3) — "
            "each pass caches ALL %d DCs.",
            len(tasks), len(windows), len(grans), len(self.dc_list),
        )
        t0 = time.perf_counter()
        ok = 0
        with ThreadPoolExecutor(max_workers=6, thread_name_prefix="bkpjobs-warm") as pool:
            futures = {pool.submit(fn): label for label, fn in tasks}
            for fut in futures:
                label = futures[fut]
                try:
                    fut.result()
                    ok += 1
                except Exception as exc:
                    logger.warning("Backup-jobs warm task %s failed: %s", label, exc)
        logger.info("Backup-jobs warm finished: %d/%d ok in %.2fs.",
                    ok, len(tasks), time.perf_counter() - t0)

    @property
    def dc_list(self) -> list[str]:
        """Expose current dynamic DC list (read-only)."""
        return list(self._dc_list)
