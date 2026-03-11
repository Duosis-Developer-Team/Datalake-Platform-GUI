from __future__ import annotations

import os
import re
import logging
import time
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor

import psycopg2
from psycopg2 import pool as pg_pool
from psycopg2 import OperationalError
from psycopg2.pool import PoolError

from app.db.queries import nutanix as nq, vmware as vq, ibm as iq, energy as eq
from app.db.queries import loki as lq, customer as cq
from app.services import cache_service as cache
from app.services import query_overrides as qo
from app.utils.time_range import default_time_range, time_range_to_bounds, cache_time_ranges

_DC_CODE_RE = re.compile(r'(DC\d+|AZ\d+|ICT\d+|UZ\d+|DH\d+)', re.IGNORECASE)

logger = logging.getLogger(__name__)

_FALLBACK_DC_LIST = [
    "AZ11", "DC11", "DC12", "DC13", "DC14", "DC15", "DC16", "DC17", "ICT11"
]

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


def _EMPTY_DC(dc_code: str) -> dict:
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

    def __init__(self):
        self._db_host = os.getenv("DB_HOST", "10.134.16.6")
        self._db_port = os.getenv("DB_PORT", "5000")
        self._db_name = os.getenv("DB_NAME", "bulutlake")
        self._db_user = os.getenv("DB_USER", "datalakeui")
        self._db_pass = os.getenv("DB_PASS")
        self._pool: pg_pool.ThreadedConnectionPool | None = None
        self._dc_list: list[str] = _FALLBACK_DC_LIST.copy()
        self._init_pool()

    def _init_pool(self) -> None:
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
        if self._pool is None:
            raise OperationalError("Connection pool is not available.")
        conn = self._pool.getconn()
        try:
            yield conn
        finally:
            self._pool.putconn(conn)

    @staticmethod
    def _run_value(cursor, sql: str, params=None) -> float | int:
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

    @staticmethod
    def _prepare_params(params_style: str, user_input: str):
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

    def _load_dc_list(self) -> list[str]:
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    rows = self._run_rows(cur, lq.DC_LIST)
                    dc_names = [row[0] for row in rows if row[0]]
                    if not dc_names:
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
        nutanix_mem     = nutanix_mem     or (0, 0)
        nutanix_storage = nutanix_storage or (0, 0)
        nutanix_cpu     = nutanix_cpu     or (0, 0)
        vmware_counts   = vmware_counts   or (0, 0, 0)
        vmware_mem      = vmware_mem      or (0, 0)
        vmware_storage  = vmware_storage  or (0, 0)
        vmware_cpu      = vmware_cpu      or (0, 0)
        power_mem       = power_mem       or (0, 0)
        power_cpu       = power_cpu       or (0, 0, 0)

        n_mem_cap_gb  = float(nutanix_mem[0] or 0) * 1024
        n_mem_used_gb = float(nutanix_mem[1] or 0) * 1024
        v_mem_cap_gb  = float(vmware_mem[0] or 0) / (1024 ** 3)
        v_mem_used_gb = float(vmware_mem[1] or 0) / (1024 ** 3)

        n_stor_cap_tb  = float(nutanix_storage[0] or 0)
        n_stor_used_tb = float(nutanix_storage[1] or 0)
        v_stor_cap_tb  = float(vmware_storage[0] or 0) / (1024 ** 4)
        v_stor_used_tb = float(vmware_storage[1] or 0) / (1024 ** 4)

        n_cpu_cap_ghz  = float(nutanix_cpu[0] or 0)
        n_cpu_used_ghz = float(nutanix_cpu[1] or 0)
        v_cpu_cap_ghz  = float(vmware_cpu[0] or 0) / 1_000_000_000
        v_cpu_used_ghz = float(vmware_cpu[1] or 0) / 1_000_000_000

        total_energy_kw = (float(ibm_w or 0) + float(vcenter_w or 0)) / 1000.0
        total_energy_kwh = float(ibm_kwh or 0) + float(vcenter_kwh or 0)

        return {
            "meta": {
                "name": dc_code,
                "location": DC_LOCATIONS.get(dc_code, "Unknown Data Center"),
            },
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

    def get_dc_details(self, dc_code: str, time_range: dict | None = None) -> dict:
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
                    )
        except OperationalError as exc:
            logger.error("DB unavailable for get_dc_details(%s): %s", dc_code, exc)
            return _EMPTY_DC(dc_code)

        cache.set(cache_key, result)
        return result

    def _fetch_all_batch(self, dc_list: list[str], start_ts, end_ts) -> tuple[dict, dict]:
        logger.info(
            "Batch fetch: starting for %d DCs, range %s -> %s",
            len(dc_list), start_ts, end_ts,
        )
        pattern_list = [f"%{dc}%" for dc in dc_list]
        dc_set_upper = {dc.upper() for dc in dc_list}

        def _run_group(queries: list[tuple[str, str, tuple]]) -> dict[str, list]:
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
            ("n_stor",     nq.BATCH_STORAGE,       nutanix_params),
            ("n_cpu",      nq.BATCH_CPU,           nutanix_params),
            ("n_platform", nq.BATCH_PLATFORM_COUNT, nutanix_params),
        ]
        vmware_queries = [
            ("v_cnt",      vq.BATCH_COUNTS,         vmware_params),
            ("v_mem",      vq.BATCH_MEMORY,         vmware_params),
            ("v_stor",     vq.BATCH_STORAGE,        vmware_params),
            ("v_cpu",      vq.BATCH_CPU,            vmware_params),
            ("v_platform", vq.BATCH_PLATFORM_COUNT, vmware_params),
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

        ibm_mem_acc: dict[str, list] = {}
        for row in ibm_raw["ibm_mem_raw"]:
            if not row or len(row) < 3:
                continue
            dc = _extract_dc(row[0])
            if dc:
                ibm_mem_acc.setdefault(dc, []).append((float(row[1] or 0), float(row[2] or 0)))
        ibm_mem: dict[str, tuple] = {}
        for dc, vals in ibm_mem_acc.items():
            n_vals = len(vals)
            ibm_mem[dc] = (
                sum(v[0] for v in vals) / n_vals,
                sum(v[1] for v in vals) / n_vals,
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

        n_host  = _index_exact(n_host_rows)
        n_vms   = _index_exact(n_vm_rows)
        n_mem   = _index_exact(n_mem_rows)
        n_stor  = _index_exact(n_stor_rows)
        n_cpu   = _index_exact(n_cpu_rows)

        v_cnt   = _index_exact(v_cnt_rows)
        v_mem_m = _index_exact(v_mem_rows)
        v_stor  = _index_exact(v_stor_rows)
        v_cpu   = _index_exact(v_cpu_rows)

        ibm_e_rows = e["e_ibm"]
        vcenter_rows = e["e_vcenter"]
        ibm_kwh_rows = e["e_ibm_kwh"]
        vcenter_kwh_rows = e["e_vctr_kwh"]

        ibm_e   = {row[0]: float(row[1] or 0) for row in ibm_e_rows if row and len(row) >= 2 and row[0]}
        vctr_e  = {row[0]: float(row[1] or 0) for row in vcenter_rows if row and len(row) >= 2 and row[0]}
        ibm_kwh_m   = {row[0]: float(row[1] or 0) for row in ibm_kwh_rows if row and len(row) >= 2 and row[0]}
        vctr_kwh_m  = {row[0]: float(row[1] or 0) for row in vcenter_kwh_rows if row and len(row) >= 2 and row[0]}

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
            )

        return results, platform_counts

    def get_all_datacenters_summary(self, time_range: dict | None = None) -> list[dict]:
        tr = time_range or default_time_range()
        cache_key = f"all_dc_summary:{tr.get('start','')}:{tr.get('end','')}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        return self._rebuild_summary(tr)

    def _rebuild_summary(self, time_range: dict | None = None) -> list[dict]:
        tr = time_range or default_time_range()
        start_ts, end_ts = time_range_to_bounds(tr)
        self._dc_list = self._load_dc_list()
        dc_list = self._dc_list
        logger.info("Rebuilding summary for %d DCs (batch fetch + aggregate)...", len(dc_list))

        t_total_start = time.perf_counter()
        try:
            all_dc_data, platform_counts = self._fetch_all_batch(dc_list, start_ts, end_ts)
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

            host_count = (intel["hosts"] or 0) + (power["hosts"] or 0)
            vm_count = (intel["vms"] or 0) + (power.get("vms", 0) or 0)

            if host_count == 0 and vm_count == 0:
                cache.set(f"dc_details:{dc}:{tr.get('start','')}:{tr.get('end','')}", d)
                continue

            cpu_cap   = intel["cpu_cap"]       or 0
            cpu_used  = intel["cpu_used"]      or 0
            ram_cap   = intel["ram_cap"]       or 0
            ram_used  = intel["ram_used"]      or 0
            stor_cap  = intel["storage_cap"]   or 0
            stor_used = intel["storage_used"]  or 0

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

            cache.set(f"dc_details:{dc}:{tr.get('start','')}:{tr.get('end','')}", d)

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

    def get_global_overview(self, time_range: dict | None = None) -> dict:
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
        tr = time_range or default_time_range()
        cache_key = f"customer_assets:{customer_name}:{tr.get('start','')}:{tr.get('end','')}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        name = (customer_name or "").strip()
        vm_pattern = f"{name}-%" if name else "%"
        lpar_pattern = f"{name}%" if name else "%"
        veeam_pattern = f"{name}%" if name else "%"
        storage_like_pattern = f"%{name}%" if name else "%"
        netbackup_workload_pattern = f"%{name}%" if name else "%"
        zerto_name_like = f"{name}%-%" if name else "%"

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
        return ["Boyner"]

    def warm_cache(self) -> None:
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
        logger.info("Warming additional cache ranges (30d, previous month)…")
        try:
            ranges = cache_time_ranges()[1:]
            for tr in ranges:
                self._rebuild_summary(tr)
                self.get_global_overview(tr)
            logger.info("Additional cache warm-up complete.")
        except Exception as exc:
            logger.warning("Additional cache warm-up failed: %s", exc)

    def refresh_all_data(self) -> None:
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
        return list(self._dc_list)
