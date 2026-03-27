from __future__ import annotations

import logging
import os
from contextlib import contextmanager

from psycopg2 import OperationalError, pool as pg_pool
from psycopg2.pool import PoolError

from app.adapters.customer_adapter import CustomerAdapter
from app.db.queries import customer as cq
from app.db.queries import s3 as s3q
from app.services import cache_service as cache
from app.utils.cluster_match import build_cluster_arch_map
from app.utils.time_range import default_time_range, time_range_to_bounds

logger = logging.getLogger(__name__)

# Cluster name classification cache (align with DC summary-style TTL)
CLUSTER_ARCH_MAP_TTL_SECONDS = 1800


class CustomerService:
    def __init__(self):
        self._db_host = os.getenv("DB_HOST", "10.134.16.6")
        self._db_port = os.getenv("DB_PORT", "5000")
        self._db_name = os.getenv("DB_NAME", "bulutlake")
        self._db_user = os.getenv("DB_USER", "customer_svc")
        self._db_pass = os.getenv("DB_PASS")
        self._pool: pg_pool.ThreadedConnectionPool | None = None
        self._init_pool()
        self._customer = CustomerAdapter(
            self._get_connection,
            self._run_value,
            self._run_row,
            self._run_rows,
        )

    def _init_pool(self) -> None:
        try:
            self._pool = pg_pool.ThreadedConnectionPool(
                minconn=2,
                maxconn=8,
                host=self._db_host,
                port=self._db_port,
                dbname=self._db_name,
                user=self._db_user,
                password=self._db_pass,
                options="-c statement_timeout=25000",
            )
            logger.info("DB connection pool initialized (min=2, max=8, statement_timeout=25000ms).")
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
    def _run_value(cursor, sql: str, params=None):
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
    def _run_row(cursor, sql: str, params=None):
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
    def _run_rows(cursor, sql: str, params=None):
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

    def _get_cluster_arch_map(self, tr: dict) -> dict[str, list[str]]:
        """Load VMware non-KM vs Nutanix cluster lists and classify managed vs pure Nutanix."""
        start_ts, end_ts = time_range_to_bounds(tr)
        cache_key = f"cluster_arch_map:{start_ts}:{end_ts}"
        cached = cache.get(cache_key)
        if cached is not None and isinstance(cached, dict):
            managed = cached.get("managed_nutanix") or []
            pure = cached.get("pure_nutanix") or []
            if isinstance(managed, list) and isinstance(pure, list):
                return {"managed_nutanix": managed, "pure_nutanix": pure}

        if self._pool is None:
            empty = {"managed_nutanix": [], "pure_nutanix": []}
            cache.set(cache_key, empty, ttl=CLUSTER_ARCH_MAP_TTL_SECONDS)
            return empty

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    vmware_rows = self._run_rows(cur, cq.ALL_VMWARE_CLUSTER_NAMES, (start_ts, end_ts))
                    nutanix_rows = self._run_rows(cur, cq.ALL_NUTANIX_CLUSTER_NAMES, (start_ts, end_ts))
                    if not nutanix_rows:
                        # Fallback: if range-scoped cluster records are missing, use latest known cluster mapping.
                        nutanix_rows = self._run_rows(cur, cq.ALL_NUTANIX_CLUSTER_NAMES_LATEST)
        except (OperationalError, PoolError) as exc:
            logger.warning("_get_cluster_arch_map failed: %s", exc)
            empty = {"managed_nutanix": [], "pure_nutanix": []}
            return empty

        vmware_nonkm: list[str] = []
        for r in vmware_rows or []:
            if not r or len(r) < 2:
                continue
            cluster_name, arch_type = r[0], r[1]
            if not cluster_name:
                continue
            if str(arch_type).lower() == "hyperconv":
                vmware_nonkm.append(str(cluster_name))

        nutanix_names: list[str] = []
        for r in nutanix_rows or []:
            if r and r[0]:
                nutanix_names.append(str(r[0]))

        arch = build_cluster_arch_map(vmware_nonkm, nutanix_names)
        result = {
            "managed_nutanix": arch["managed_nutanix"],
            "pure_nutanix": arch["pure_nutanix"],
        }
        cache.set(cache_key, result, ttl=CLUSTER_ARCH_MAP_TTL_SECONDS)
        return result

    def get_customer_resources(self, customer_name: str, time_range: dict | None = None) -> dict:
        tr = time_range or default_time_range()
        cache_key = f"customer_assets:{customer_name}:{tr.get('start','')}:{tr.get('end','')}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        if self._pool is None:
            return self._customer._empty_result()
        arch = self._get_cluster_arch_map(tr)
        result = self._customer.fetch(
            customer_name,
            tr,
            managed_nutanix_clusters=arch.get("managed_nutanix") or [],
            pure_nutanix_clusters=arch.get("pure_nutanix") or [],
        )
        cache.set(cache_key, result)
        return result

    def get_customer_list(self) -> list[str]:
        return ["Boyner"]

    def _fetch_customer_s3_vaults(self, customer_name: str, start_ts, end_ts) -> dict:
        """Fetch S3 vault metrics for a customer (same logic as datacenter-api DatabaseService)."""
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
