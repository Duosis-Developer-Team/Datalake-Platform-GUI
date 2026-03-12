from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

from psycopg2 import OperationalError, pool as pg_pool

from app.adapters.energy_adapter import EnergyAdapter
from app.adapters.ibm_power_adapter import IBMPowerAdapter, _DC_CODE_RE
from app.adapters.nutanix_adapter import NutanixAdapter
from app.adapters.vmware_adapter import VMwareAdapter
from app.db.queries import loki as lq
from app.services import cache_service as cache
from app.services.dc_support import DC_LOCATIONS, _FALLBACK_DC_LIST, aggregate_dc, empty_dc, rebuild_summary
from app.utils.time_range import cache_time_ranges, default_time_range, time_range_to_bounds

logger = logging.getLogger(__name__)

_EMPTY_DC = empty_dc


class DatabaseService:
    _aggregate_dc = staticmethod(aggregate_dc)

    def __init__(self):
        self._db_host = os.getenv("DB_HOST", "10.134.16.6")
        self._db_port = os.getenv("DB_PORT", "5000")
        self._db_name = os.getenv("DB_NAME", "bulutlake")
        self._db_user = os.getenv("DB_USER", "infra_svc")
        self._db_pass = os.getenv("DB_PASS")
        self._pool: pg_pool.ThreadedConnectionPool | None = None
        self._dc_list: list[str] = _FALLBACK_DC_LIST.copy()
        self._init_pool()
        self._nutanix = NutanixAdapter(self._get_connection, self._run_value, self._run_row, self._run_rows)
        self._vmware = VMwareAdapter(self._get_connection, self._run_value, self._run_row, self._run_rows)
        self._ibm = IBMPowerAdapter(self._get_connection, self._run_value, self._run_row, self._run_rows)
        self._energy = EnergyAdapter(self._get_connection, self._run_value)

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
                    nutanix_data = self._nutanix.fetch_single_dc(cur, dc_code, start_ts, end_ts)
                    vmware_data = self._vmware.fetch_single_dc(cur, dc_code, start_ts, end_ts)
                    ibm_data = self._ibm.fetch_single_dc(cur, dc_wc, start_ts, end_ts)
                    energy_data = self._energy.fetch_single_dc(cur, dc_code, dc_wc, start_ts, end_ts)
                    result = self._aggregate_dc(
                        dc_code,
                        nutanix_host_count=nutanix_data["host_count"],
                        nutanix_vms=nutanix_data["vm_count"],
                        nutanix_mem=nutanix_data["memory"],
                        nutanix_storage=nutanix_data["storage"],
                        nutanix_cpu=nutanix_data["cpu"],
                        vmware_counts=vmware_data["counts"],
                        vmware_mem=vmware_data["memory"],
                        vmware_storage=vmware_data["storage"],
                        vmware_cpu=vmware_data["cpu"],
                        power_hosts=ibm_data["host_count"],
                        power_vios=ibm_data["vios_count"],
                        power_lpar_count=ibm_data["lpar_count"],
                        power_mem=ibm_data["memory"],
                        power_cpu=ibm_data["cpu"],
                        ibm_w=energy_data["ibm_w"],
                        vcenter_w=energy_data["vcenter_w"],
                        ibm_kwh=energy_data["ibm_kwh"],
                        vcenter_kwh=energy_data["vcenter_kwh"],
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

        nutanix_queries = self._nutanix.fetch_batch_queries(dc_list, pattern_list, start_ts, end_ts)
        vmware_queries = self._vmware.fetch_batch_queries(dc_list, pattern_list, start_ts, end_ts)
        ibm_queries = self._ibm.fetch_batch_queries(dc_list, pattern_list, start_ts, end_ts)
        energy_queries = self._energy.fetch_batch_queries(dc_list, pattern_list, start_ts, end_ts)

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

        ibm_processed = self._ibm.process_raw_batch(ibm_raw, dc_set_upper)
        ibm_h = ibm_processed["hosts"]
        ibm_vios = ibm_processed["vios"]
        ibm_lpar = ibm_processed["lpar"]
        ibm_mem = ibm_processed["mem"]
        ibm_cpu_map = ibm_processed["cpu"]

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
        return rebuild_summary(self, time_range)

    def get_global_overview(self, time_range: dict | None = None) -> dict:
        tr = time_range or default_time_range()
        cache_key = f"global_overview:{tr.get('start','')}:{tr.get('end','')}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        summaries = self.get_all_datacenters_summary(tr)
        result: dict[str, int | float] = {
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
