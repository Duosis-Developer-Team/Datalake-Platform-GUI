from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from psycopg2 import InterfaceError, OperationalError
from psycopg2 import pool as pg_pool
from psycopg2.pool import PoolError

from app.adapters.customer_adapter import CustomerAdapter
from app.config import settings
from app.db.queries import customer as cq
from app.db.queries import crm_sales as crm_sq
from app.db.queries import s3 as s3q
from app.db.queries import service_mapping as smq
from app.services import cache_service as cache
from app.services.crm_account_resolver import make_datalake_account_lookup, resolve_crm_account_ids
from app.services.crm_customer_list import build_crm_project_customer_list, resolve_infra_search_name
from app.services.customer_catalog import (
    CATALOG_SNAPSHOT_KEY,
    CATALOG_SNAPSHOT_TTL_SECONDS,
    build_catalog_row,
    build_overview_payload,
    group_catalog_rows,
    load_project_customer_rows,
    _is_mapped,
)
from app.utils.service_sales_mapping import map_service_sales_lines
from app.services.mapping_warm_scheduler import MappingWarmScheduler
from app.services.customer_mapping_resolver import (
    MappingRule,
    ResolvedSourcePatterns,
    build_resolved_patterns,
)
from app.utils.cluster_match import build_cluster_arch_map
from app.utils.time_range import cache_time_ranges, default_time_range, time_range_to_bounds
from shared.customer.cache_keys import customer_assets_cache_key
from shared.backup.policy_classification import classify_netbackup_policy
from shared.backup.unique_jobs import (
    aggregate_unique_jobs,
    filter_unique_job_rows,
    normalize_unique_job_rows,
    paginate_rows as paginate_unique_job_rows,
)
from app.utils.usage_comparison import (
    build_lightweight_compliance_from_bundle,
    catalog_product_names_for_compliance,
    derive_catalog_overuse_status,
    group_entitled_by_customer,
    group_weighted_prices_by_customer,
)
from app.services.crm_config_service import CrmConfigService
from app.services.mapping_cache_invalidator import (
    ResolutionError,
    plan_invalidation_for_accounts,
    plan_invalidation_for_every_name,
)

logger = logging.getLogger(__name__)

MAPPING_CACHE_WARNING = (
    "Mapping kaydedildi, ancak cache temizlenemedi — lütfen tekrar kaydedin."
)


@dataclass(frozen=True)
class MappingInvalidationPlan:
    """An invalidation that has been decided but not yet executed.

    Carries the outcome of the *resolution* step so that apply can run later,
    after the DB write has committed, without resolving anything itself.

    ``warning`` holds a resolution failure rather than raising it: planning runs
    on a request that is about to commit (or already has), so the honest report
    is "saved, but the cache is suspect", never a 500. ``is_noop`` distinguishes
    "there was nothing to invalidate in the first place" from "we planned, and
    the answer happened to be zero keys" — only the latter should still drop
    unmapped_resources: and log the zero-delete warning.
    """

    account_ids: tuple[str, ...] = ()
    doomed_keys: tuple[str, ...] = ()
    matched_names: tuple[str, ...] = ()
    scanned_count: int = 0
    warning: str | None = None
    is_noop: bool = False

# Hot/cold TTL = 4x the 15-minute scheduler interval (ADR-0007); warm tier stays 6h.
CLUSTER_ARCH_MAP_TTL_SECONDS = 3600
CUSTOMER_DATA_CACHE_TTL_HOT = 3600
CUSTOMER_DATA_CACHE_TTL_WARM = 21600
CUSTOMER_DATA_CACHE_TTL_COLD = 3600
# Backward-compatible alias for tests and legacy imports.
CUSTOMER_DATA_CACHE_TTL_SECONDS = CUSTOMER_DATA_CACHE_TTL_COLD

BATCH_WARM_STATUS_KEY = "customer_warm_batch:status"
BATCH_WARM_COMPLETED_KEY = "customer_warm_batch:last_completed_at"
HOT_WARM_STATUS_KEY = "customer_warm_hot:status"

# Guards lazy construction of each CustomerService instance's
# MappingWarmScheduler (see _get_warm_scheduler). Module-level rather than an
# instance attribute: several tests build the service via
# CustomerService.__new__(CustomerService), bypassing __init__, so a lock
# assigned there would not exist for them.
_warm_scheduler_init_lock = threading.Lock()


def _iso_or_none(value: Any) -> str | None:
    """date/datetime -> 'YYYY-MM-DD' string; None/blank -> None."""
    if value is None:
        return None
    try:
        return value.isoformat()
    except AttributeError:
        s = str(value).strip()
        return s or None


class QueryTimeoutError(Exception):
    """PostgreSQL statement timeout; result must not be cached."""


def _is_timeout_error(exc: BaseException) -> bool:
    code = getattr(exc, "pgcode", None)
    if code == "57014":  # query_canceled (includes statement_timeout)
        return True
    msg = (str(exc) or "").lower()
    return "canceling statement" in msg or "statement timeout" in msg


def _is_fatal_db_error(exc: BaseException) -> bool:
    """
    True if the connection is likely unusable and should be discarded from the pool.
    Query timeouts / statement cancel usually leave the connection valid — do not discard.
    """
    if isinstance(exc, InterfaceError):
        return True
    if isinstance(exc, PoolError):
        return True
    if isinstance(exc, OperationalError):
        code = getattr(exc, "pgcode", None)
        if code == "57014":  # query_canceled (includes statement_timeout in PG)
            return False
        msg = (str(exc) or "").lower()
        if "query canceled" in msg or "statement timeout" in msg or "canceling statement" in msg:
            return False
        return True
    msg = (str(exc) or "").lower()
    if "cursor already closed" in msg:
        return True
    if "ssl syscall" in msg or "eof detected" in msg:
        return True
    return False


class CustomerService:
    def __init__(self):
        self._db_host = os.getenv("DB_HOST", "10.134.16.6")
        self._db_port = os.getenv("DB_PORT", "5000")
        self._db_name = os.getenv("DB_NAME", "bulutlake")
        self._db_user = os.getenv("DB_USER", "customer_svc")
        self._db_pass = os.getenv("DB_PASS")
        self._pool: pg_pool.ThreadedConnectionPool | None = None
        self._webui = None
        self._netbox_tenant_names: list[str] | None = None
        self._init_pool()
        self._customer = CustomerAdapter(
            self._get_connection,
            self._run_value,
            self._run_row,
            self._run_rows,
        )

    def attach_webui_pool(self, webui) -> None:
        """Optional WebUI pool for alias resolution (set from FastAPI lifespan)."""
        self._webui = webui

    def _init_pool(self) -> None:
        try:
            pool_kw: dict[str, Any] = dict(
                minconn=settings.db_pool_minconn,
                maxconn=settings.db_pool_maxconn,
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
            timeout_ms = settings.db_statement_timeout_ms
            if timeout_ms > 0:
                pool_kw["options"] = f"-c statement_timeout={timeout_ms}"
            self._pool = pg_pool.ThreadedConnectionPool(**pool_kw)
            if timeout_ms > 0:
                logger.info(
                    "DB connection pool initialized (min=%d, max=%d, statement_timeout=%dms).",
                    settings.db_pool_minconn,
                    settings.db_pool_maxconn,
                    timeout_ms,
                )
            else:
                logger.info(
                    "DB connection pool initialized (min=%d, max=%d, no client statement_timeout).",
                    settings.db_pool_minconn,
                    settings.db_pool_maxconn,
                )
        except OperationalError as exc:
            logger.error("Failed to initialize DB pool: %s", exc)
            self._pool = None

    @contextmanager
    def _get_connection(self):
        if self._pool is None:
            raise OperationalError("Connection pool is not available.")
        conn = self._pool.getconn()
        discard = False
        try:
            yield conn
        except Exception as exc:
            discard = _is_fatal_db_error(exc)
            if discard:
                logger.warning(
                    "Discarding DB connection after fatal error (correlation: Redis keys "
                    "customer_assets:* / customer_s3:* / cluster_arch_map:*): %s",
                    exc,
                )
            raise
        finally:
            try:
                self._pool.putconn(conn, close=discard)
            except Exception:
                logger.exception("putconn failed while returning connection to pool")

    @staticmethod
    def _sql_label(sql: str) -> str:
        """Extract a short label from SQL for logging (first meaningful keyword line)."""
        for line in sql.strip().splitlines():
            stripped = line.strip().upper()
            if stripped and not stripped.startswith("--") and not stripped.startswith("WITH"):
                return stripped[:120]
        return sql.strip()[:120]

    @staticmethod
    def _run_value(cursor, sql: str, params=None):
        try:
            t0 = time.perf_counter()
            cursor.execute(sql, params)
            row = cursor.fetchone()
            elapsed = (time.perf_counter() - t0) * 1000
            logger.info("SQL value (%.0fms): %s", elapsed, CustomerService._sql_label(sql))
            if row and row[0] is not None:
                return row[0]
        except Exception as exc:
            if _is_timeout_error(exc):
                logger.warning("Query timeout (value): %s | SQL: %s", exc, CustomerService._sql_label(sql))
                try:
                    cursor.execute("ROLLBACK")
                except Exception:
                    pass
                raise QueryTimeoutError(str(exc)) from exc
            if _is_fatal_db_error(exc):
                logger.warning(
                    "Fatal DB error (value), re-raising: %s | SQL: %s",
                    exc,
                    CustomerService._sql_label(sql),
                )
                raise
            logger.warning("Query error (value): %s | SQL: %s", exc, CustomerService._sql_label(sql))
            try:
                cursor.execute("ROLLBACK")
            except Exception:
                pass
        return 0

    @staticmethod
    def _run_row(cursor, sql: str, params=None):
        try:
            t0 = time.perf_counter()
            cursor.execute(sql, params)
            row = cursor.fetchone()
            elapsed = (time.perf_counter() - t0) * 1000
            logger.info("SQL row (%.0fms): %s", elapsed, CustomerService._sql_label(sql))
            return row
        except Exception as exc:
            if _is_timeout_error(exc):
                logger.warning("Query timeout (row): %s | SQL: %s", exc, CustomerService._sql_label(sql))
                try:
                    cursor.execute("ROLLBACK")
                except Exception:
                    pass
                raise QueryTimeoutError(str(exc)) from exc
            if _is_fatal_db_error(exc):
                logger.warning(
                    "Fatal DB error (row), re-raising: %s | SQL: %s",
                    exc,
                    CustomerService._sql_label(sql),
                )
                raise
            logger.warning("Query error (row): %s | SQL: %s", exc, CustomerService._sql_label(sql))
            try:
                cursor.execute("ROLLBACK")
            except Exception:
                pass
        return None

    @staticmethod
    def _run_rows(cursor, sql: str, params=None):
        try:
            t0 = time.perf_counter()
            cursor.execute(sql, params)
            rows = cursor.fetchall() or []
            elapsed = (time.perf_counter() - t0) * 1000
            logger.info("SQL rows (%.0fms, %d rows): %s", elapsed, len(rows), CustomerService._sql_label(sql))
            return rows
        except Exception as exc:
            if _is_timeout_error(exc):
                logger.warning("Query timeout (rows): %s | SQL: %s", exc, CustomerService._sql_label(sql))
                try:
                    cursor.execute("ROLLBACK")
                except Exception:
                    pass
                raise QueryTimeoutError(str(exc)) from exc
            if _is_fatal_db_error(exc):
                logger.warning(
                    "Fatal DB error (rows), re-raising: %s | SQL: %s",
                    exc,
                    CustomerService._sql_label(sql),
                )
                raise
            logger.warning("Query error (rows): %s | SQL: %s", exc, CustomerService._sql_label(sql))
            try:
                cursor.execute("ROLLBACK")
            except Exception:
                pass
        return []

    def _get_cluster_arch_map(self, tr: dict) -> dict[str, list[str]]:
        """Load VMware non-KM vs Nutanix cluster lists and classify managed vs pure Nutanix."""
        if self._pool is None:
            return {"managed_nutanix": [], "pure_nutanix": []}

        start_ts, end_ts = time_range_to_bounds(tr)
        cache_key = f"cluster_arch_map:{start_ts}:{end_ts}"
        cached = cache.get(cache_key)
        if cached is not None and isinstance(cached, dict):
            managed = cached.get("managed_nutanix") or []
            pure = cached.get("pure_nutanix") or []
            if isinstance(managed, list) and isinstance(pure, list):
                return {"managed_nutanix": managed, "pure_nutanix": pure}

        def _compute() -> dict[str, list[str]]:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    vmware_rows = self._run_rows(cur, cq.ALL_VMWARE_CLUSTER_NAMES, (start_ts, end_ts))
                    nutanix_rows = self._run_rows(cur, cq.ALL_NUTANIX_CLUSTER_NAMES, (start_ts, end_ts))
                    if not nutanix_rows:
                        nutanix_rows = self._run_rows(cur, cq.ALL_NUTANIX_CLUSTER_NAMES_LATEST)

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
            return {
                "managed_nutanix": arch["managed_nutanix"],
                "pure_nutanix": arch["pure_nutanix"],
            }

        return cache.run_singleflight(cache_key, _compute, ttl=CLUSTER_ARCH_MAP_TTL_SECONDS)

    def _get_latest_data_ts(self) -> datetime | None:
        """Most-recent timestamp in vm_metrics (cached 60 s). See _smart_1h_tr."""
        cached = cache.get("latest_vm_ts")
        if cached:
            try:
                return datetime.fromisoformat(str(cached).replace("Z", "+00:00"))
            except Exception:
                pass
        if self._pool is None:
            return None
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
        recent ingested timestamp instead of wall-clock. Custom ranges are
        left untouched — those are user-chosen on purpose."""
        if not tr:
            return default_time_range()
        preset = tr.get("preset")
        offset = self._RELATIVE_PRESET_OFFSETS.get(preset)
        if offset is None:
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
        return {
            "start": start.date().isoformat(),
            "end": end.date().isoformat(),
            "preset": preset,
        }

    def _load_customer_resources(self, customer_name: str, tr: dict) -> dict:
        arch = self._get_cluster_arch_map(tr)
        search_name = self.resolve_infra_search_name(customer_name)
        source_patterns = self.resolve_source_patterns(customer_name)
        return self._customer.fetch(
            customer_name,
            tr,
            managed_nutanix_clusters=arch.get("managed_nutanix") or [],
            pure_nutanix_clusters=arch.get("pure_nutanix") or [],
            infra_search_name=search_name,
            source_patterns=source_patterns,
        )

    def get_customer_resources(self, customer_name: str, time_range: dict | None = None, *, cache_ttl: int | None = None) -> dict:
        tr = time_range or default_time_range()
        if tr.get("anchor_latest"):
            tr = self._smart_1h_tr(tr)
        cache_key = customer_assets_cache_key(customer_name, tr.get("start", ""), tr.get("end", ""))
        if self._pool is None:
            return self._customer._empty_result()
        ttl = cache_ttl if cache_ttl is not None else self._cache_ttl_for_customer(customer_name)
        try:
            return cache.run_singleflight(
                cache_key,
                lambda: self._load_customer_resources(customer_name, tr),
                ttl=ttl,
            )
        except QueryTimeoutError as exc:
            logger.warning(
                "get_customer_resources timed out for %s; trying stale cache key=%s: %s",
                customer_name,
                cache_key,
                exc,
            )
            stale = self._stale_customer_resources(cache_key, customer_name)
            if stale is not None:
                return stale
            raise HTTPException(status_code=503, detail="Data temporarily unavailable") from exc
        except (OperationalError, PoolError, InterfaceError) as exc:
            logger.warning(
                "get_customer_resources failed (response not cached); correlation Redis key=%s: %s",
                cache_key,
                exc,
            )
            stale = self._stale_customer_resources(cache_key, customer_name)
            if stale is not None:
                return stale
            raise HTTPException(status_code=503, detail="Database temporarily unavailable") from exc

    @staticmethod
    def _stale_customer_resources(cache_key: str, customer_name: str) -> dict | None:
        """Primary cache, then last_good shadow key (ADR-0007)."""
        stale = cache.get_stale(cache_key)
        if stale is not None:
            if cache.get(cache_key) is None and cache.get_last_good(cache_key) is not None:
                logger.warning(
                    "Serving last_good stale customer resources for %s key=%s",
                    customer_name,
                    cache_key,
                )
            return stale
        return None

    def get_unmapped_resources(self, time_range: dict | None = None) -> dict:
        """Resources claimed by NO customer — the reverse of per-customer queries.

        Phase 1: VMs. Cached + single-flighted; the classification is Python-side
        (no leading-wildcard scan). Failure returns the empty payload, never 5xx —
        an orphan report must never break the customers page.
        """
        empty = {"rows": [], "total": 0, "alias_gap_count": 0, "orphan_count": 0}
        if self._pool is None:
            return empty
        tr = time_range or default_time_range()
        if tr.get("anchor_latest"):
            tr = self._smart_1h_tr(tr)
        start, end = time_range_to_bounds(tr)
        cache_key = f"unmapped_resources:{start.isoformat()}:{end.isoformat()}"
        try:
            return cache.run_singleflight(
                cache_key,
                lambda: self._load_unmapped_resources(start, end),
                ttl=CUSTOMER_DATA_CACHE_TTL_WARM,
            )
        except (QueryTimeoutError, OperationalError, PoolError, InterfaceError) as exc:
            logger.warning("get_unmapped_resources failed key=%s: %s", cache_key, exc)
            stale = cache.get_stale(cache_key)
            return stale if stale is not None else empty

    def _load_unmapped_resources(self, start, end) -> dict:
        from app.db.queries import unmapped as uq
        from shared.customer.unmapped_classifier import (
            account_keys_from_names,
            build_unmapped_payload,
            owner_matchers_from_mappings,
        )

        names_with_platform: list[tuple[str, str]] = []
        for sql, platform in (
            (uq.UNMAPPED_VMWARE_NAMES, "vmware"),
            (uq.UNMAPPED_NUTANIX_NAMES, "nutanix"),
        ):
            for row in self._run_query(sql, (start, end)):
                name = str(row.get("name") or "").strip()
                if name:
                    names_with_platform.append((name, platform))

        account_names = [
            str(r.get("name") or "").strip()
            for r in self._run_query(uq.CRM_ACCOUNT_NAMES, ())
            if r.get("name")
        ]
        account_keys = account_keys_from_names(account_names)

        # Ownership = every VM mapping rule (flattened from the per-account index)
        # unioned with each customer's display-name fallback (safe over-claim).
        mapping_index = self._load_source_mapping_index()
        mapping_rows = [row for rows in mapping_index.values() for row in rows]
        owners = owner_matchers_from_mappings(mapping_rows, display_names=account_names)

        return build_unmapped_payload(names_with_platform, owners, account_keys)

    def refresh_deleted_vm_registry(self) -> dict:
        """Rebuild gui_deleted_vm_registry from an all-time metric scan (scheduler).

        The leading-'_' scan is a full seq-scan (~84s) that exceeds the request-path
        60s timeout, so this runs with an elevated per-transaction timeout and is
        invoked only from the background scheduler — never on a request.
        """
        import datetime as _dt

        from app.db.queries import deleted_vm as dvq
        from shared.customer.deleted_vm_parser import build_registry_row

        if self._pool is None:
            return {"ok": False, "reason": "datalake pool unavailable"}
        webui = self._webui
        if webui is None or not getattr(webui, "is_available", False):
            return {"ok": False, "reason": "webui pool unavailable"}

        today = _dt.date.today()
        scanned = 0
        upserts: list[dict[str, Any]] = []
        try:
            with self._get_connection() as conn:
                try:
                    with conn.cursor() as cur:
                        cur.execute("SET LOCAL statement_timeout = '300s'")  # this txn only; scan ~85-255s under load
                        for sql, platform in (
                            (dvq.DELETED_VMWARE_ALLTIME, "vmware"),
                            (dvq.DELETED_NUTANIX_ALLTIME, "nutanix"),
                        ):
                            cur.execute(sql)
                            cols = [d[0] for d in cur.description]
                            for r in cur.fetchall():
                                rec = dict(zip(cols, r))
                                scanned += 1
                                row = build_registry_row(
                                    platform,
                                    str(rec.get("name") or ""),
                                    rec.get("first_seen"),
                                    rec.get("last_seen"),
                                    today,
                                )
                                if row is not None:
                                    upserts.append(row)
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
        except (OperationalError, PoolError, InterfaceError) as exc:
            logger.warning("Deleted-VM registry scan failed: %s", exc)
            return {"ok": False, "reason": "scan failed", "scanned": scanned}

        upserted = webui.execute_batch(dvq.UPSERT_DELETED_VM, upserts)
        logger.info(
            "Deleted-VM registry refreshed: scanned=%d parsed/upserted=%d", scanned, upserted
        )
        return {"ok": True, "scanned": scanned, "upserted": upserted}

    def get_infra_patterns(self, customer_name: str) -> dict:
        """Resolved ILIKE patterns that match a customer's infra by name.

        The GUI passes these to datacenter-api's Nutanix-snapshot endpoint so the
        snapshot protection-domain names (short prefix, e.g. 'Acme-...') are
        matched the same way the rest of the platform matches this customer — not
        the raw CRM legal name. Returns virtualization + backup patterns, deduped;
        falls back to '%name%' if nothing resolves.
        """
        name = str(customer_name or "").strip()
        if not name:
            return {"patterns": []}
        patterns: list[str] = []
        try:
            rp = self.resolve_source_patterns(name)
            seen: set[str] = set()
            for src in ("virtualization", "backup_veeam", "backup_zerto", "backup_netbackup"):
                for p in rp.ilike_patterns(src):
                    if p not in seen:
                        seen.add(p)
                        patterns.append(p)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Infra-pattern resolve failed for %s: %s", name, exc)
        if not patterns:
            patterns = [f"%{name}%"]
        return {"patterns": patterns}

    def get_deleted_machines(self, customer_name: str) -> dict:
        """All-time deleted VMs for a customer, read from the registry (instant).

        Matches by the same `%display_name%` fallback the resources path uses, over
        the tiny registry table (ILIKE is cheap here). Never raises — an empty
        payload is returned if the registry is unavailable.
        """
        from app.db.queries import deleted_vm as dvq

        empty = {"rows": [], "total": 0, "overdue": 0}
        webui = self._webui
        name = str(customer_name or "").strip()
        if not name or webui is None or not getattr(webui, "is_available", False):
            return empty

        # Match the customer's resolved virtualization patterns (mapping rules +
        # display-name fallback) — the same set the resources path uses — so the
        # short VM prefix (e.g. _Acme-...) is matched, not the full legal name.
        try:
            patterns = self.resolve_source_patterns(name).ilike_patterns("virtualization")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Deleted-machines pattern resolve failed for %s: %s", name, exc)
            patterns = []
        if not patterns:
            patterns = [f"%{name}%"]

        try:
            rows = webui.run_rows(dvq.LIST_DELETED_VMS_BY_PATTERNS, (patterns,))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Deleted-machines read failed for %s: %s", name, exc)
            return empty

        import datetime as _dt

        today = _dt.date.today()
        out: list[dict[str, Any]] = []
        overdue = 0
        for r in rows:
            planned = r.get("planned_date")
            actual = r.get("actual_delete_date")
            # overdue = planned date passed AND the VM is still emitting (not deleted)
            is_overdue = actual is None and planned is not None and planned < today
            if is_overdue:
                overdue += 1
            out.append({
                "vm_name": r.get("vm_name"),
                "platform": r.get("platform"),
                "customer": r.get("customer"),
                "request_date": _iso_or_none(r.get("request_date")),
                "planned_date": _iso_or_none(planned),
                "actual_delete_date": _iso_or_none(actual),
                "overdue": is_overdue,
            })
        return {"rows": out, "total": len(out), "overdue": overdue}

    def _load_customer_names_from_db(self) -> list[str]:
        """Distinct tenant names from NetBox inventory (active devices)."""
        if self._pool is None:
            return []
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    rows = self._run_rows(cur, cq.CUSTOMER_NAME_LIST)
            return sorted({str(r[0]).strip() for r in (rows or []) if r and r[0]})
        except Exception as exc:
            logger.warning("Failed to load customer names from DB: %s", exc)
            return []

    def _load_netbox_tenant_names(self) -> list[str]:
        if self._netbox_tenant_names is not None:
            return self._netbox_tenant_names
        self._netbox_tenant_names = self._load_customer_names_from_db()
        return self._netbox_tenant_names

    def _load_boyner_crm_display_name(self) -> str | None:
        if self._pool is None:
            return None
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    row = self._run_row(cur, cq.CRM_BOYNER_ACCOUNT_NAME)
            if row and row[0]:
                return str(row[0]).strip()
        except Exception as exc:
            logger.warning("Failed to load Boyner CRM account name: %s", exc)
        return None

    def _load_crm_project_customer_names(self) -> list[str]:
        """CRM accounts with at least one PRJ-* sales order."""
        if self._pool is None:
            return []
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    rows = self._run_rows(cur, cq.CRM_PROJECT_CUSTOMER_LIST)
            project_names = [str(r[0]).strip() for r in (rows or []) if r and r[0]]
            boyner_crm_name = self._load_boyner_crm_display_name()
            return build_crm_project_customer_list(
                project_names,
                boyner_crm_name=boyner_crm_name,
            )
        except Exception as exc:
            logger.warning("Failed to load CRM project customer names: %s", exc)
            return []

    def _lookup_alias_for_display_name_raising(self, display_name: str) -> tuple[str | None, str | None, str | None]:
        """The real lookup. Lets failures propagate — see _lookup_alias_for_display_name."""
        webui = self._webui
        if webui is None or not getattr(webui, "is_available", False):
            return None, None, None
        rows = webui.run_rows(
            smq.RESOLVE_ALIAS_BY_NAME,
            (display_name, f"%{display_name}%"),
        )
        if rows:
            row = rows[0]
            return (
                row.get("netbox_musteri_value"),
                row.get("canonical_customer_key"),
                row.get("crm_accountid"),
            )
        resolved = webui.run_one(
            smq.RESOLVE_ACCOUNTID_BY_DISPLAY_NAME,
            (display_name, display_name, display_name),
        )
        if resolved:
            return (
                resolved.get("netbox_musteri_value"),
                resolved.get("canonical_customer_key"),
                resolved.get("crm_accountid"),
            )
        datalake_lookup = None
        if self._pool is not None:
            datalake_lookup = make_datalake_account_lookup(self._get_connection, self._run_row)
        account_ids = resolve_crm_account_ids(
            display_name,
            webui=None,
            datalake_account_lookup=datalake_lookup,
        )
        if account_ids:
            return None, None, account_ids[0]
        return None, None, None

    def _lookup_alias_for_display_name(self, display_name: str) -> tuple[str | None, str | None, str | None]:
        """Swallowing wrapper for read-path callers: never raises, "can't tell"
        collapses to "belongs to nobody". Do NOT use this for invalidation
        decisions — see resolve_account_id_strict, which needs the distinction
        this wrapper deliberately erases."""
        try:
            return self._lookup_alias_for_display_name_raising(display_name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Alias lookup failed for customer=%s: %s", display_name, exc)
            return None, None, None

    def _load_source_mapping_rules(self, crm_accountid: str | None) -> list[MappingRule]:
        webui = self._webui
        if webui is None or not getattr(webui, "is_available", False) or not crm_accountid:
            return []
        try:
            rows = webui.run_rows(smq.LIST_SOURCE_MAPPINGS_FOR_ACCOUNT, (crm_accountid,))
            return [MappingRule.from_row(r) for r in rows if r.get("enabled", True)]
        except Exception as exc:
            logger.warning("Source mapping load failed for account=%s: %s", crm_accountid, exc)
            return []

    def resolve_source_patterns(self, display_name: str) -> ResolvedSourcePatterns:
        """Resolve enabled source mappings for a CRM display name."""
        netbox_value, canonical_key, account_id = self._lookup_alias_for_display_name(display_name)
        fallback = resolve_infra_search_name(
            display_name,
            alias_netbox_value=netbox_value,
            alias_canonical_key=canonical_key,
            netbox_tenant_names=self._load_netbox_tenant_names(),
        )
        rules = self._load_source_mapping_rules(account_id)
        resolved = build_resolved_patterns(rules, fallback_search_name=fallback)
        if not resolved.has_mappings():
            return build_resolved_patterns([], fallback_search_name=fallback)
        return resolved

    def resolve_account_id_strict(self, display_name: str) -> str | None:
        """Resolve a display name to a CRM account id, or raise if we cannot tell.

        _lookup_alias_for_display_name swallows exceptions and returns
        (None, None, None), which conflates "belongs to nobody" with "lookup
        failed". Invalidation must not act on that ambiguity: skipping a key we
        were unsure about leaves it silently stale. So this calls the raising
        core directly (never the swallowing wrapper) and additionally treats an
        unavailable webui pool as "cannot tell" rather than "belongs to
        nobody" — without webui we have no way to answer either way.
        """
        webui = self._webui
        if webui is None or not getattr(webui, "is_available", False):
            raise ResolutionError(
                f"WebUI pool unavailable; cannot resolve display name {display_name!r}"
            )
        try:
            _netbox_value, _canonical_key, account_id = self._lookup_alias_for_display_name_raising(
                display_name
            )
        except Exception as exc:  # noqa: BLE001
            raise ResolutionError(f"Could not resolve display name {display_name!r}") from exc
        return account_id

    def _scan_cache_keys(self, prefix: str) -> list[str]:
        return cache.scan_prefix(prefix)

    def _delete_cache_keys(self, keys: list[str]) -> None:
        for key in keys:
            cache.delete(key)

    def _get_warm_scheduler(self) -> MappingWarmScheduler:
        scheduler = getattr(self, "_mapping_warm_scheduler", None)
        if scheduler is not None:
            return scheduler
        # Double-checked: FastAPI serves sync handlers from a thread pool, so two
        # concurrent first calls could otherwise each build a scheduler, orphaning
        # one whose timers still fire — a duplicate warm the debounce exists to avoid.
        with _warm_scheduler_init_lock:
            scheduler = getattr(self, "_mapping_warm_scheduler", None)
            if scheduler is None:
                scheduler = MappingWarmScheduler(
                    warm_fn=lambda name: self._rebuild_customer_caches_for_customer(name)
                )
                self._mapping_warm_scheduler = scheduler
        return scheduler

    def _schedule_mapping_warm(self, names: tuple[str, ...]) -> None:
        self._get_warm_scheduler().schedule(names)

    def plan_mapping_invalidation(self, account_ids: set[str]) -> MappingInvalidationPlan:
        """Resolve which cached keys a mapping change dooms, deleting nothing.

        Callers whose write touches gui_crm_customer_alias (upsert_alias,
        delete_alias) MUST call this before that write. The resolver reads that
        table, so afterwards a display name can resolve to None — or to a
        different account — and its keys would be skipped as already-correct and
        left stale. Only the resolution moves earlier; apply_mapping_invalidation
        still deletes after the commit.

        Never raises, for the same reason invalidate_mapping_caches does not: a
        resolution failure is reported as a warning on a write that succeeds.
        """
        targets = tuple(sorted({a for a in account_ids if a}))
        if not targets:
            return MappingInvalidationPlan(is_noop=True)
        try:
            planned = plan_invalidation_for_accounts(
                set(targets),
                resolve_account_id=self.resolve_account_id_strict,
                scan_keys=self._scan_cache_keys,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Mapping cache invalidation planning failed for accounts=%s: %s",
                list(targets),
                exc,
            )
            return MappingInvalidationPlan(
                account_ids=targets, warning=MAPPING_CACHE_WARNING
            )
        return MappingInvalidationPlan(
            account_ids=targets,
            doomed_keys=planned.doomed_keys,
            matched_names=planned.matched_names,
            scanned_count=planned.scanned_count,
        )

    def plan_all_mapping_invalidation(self) -> MappingInvalidationPlan:
        """Plan the removal of every cached customer view, resolver-free.

        For bulk writes (resync_aliases_from_datalake) whose account set is
        every project customer anyway and cannot be fully known before their
        first write. See plan_invalidation_for_every_name for why targeting is
        both useless and unsafe there.
        """
        try:
            planned = plan_invalidation_for_every_name(scan_keys=self._scan_cache_keys)
        except Exception as exc:  # noqa: BLE001
            logger.error("Mapping cache invalidation planning failed for all names: %s", exc)
            return MappingInvalidationPlan(warning=MAPPING_CACHE_WARNING)
        return MappingInvalidationPlan(
            doomed_keys=planned.doomed_keys,
            matched_names=planned.matched_names,
            scanned_count=planned.scanned_count,
        )

    def apply_mapping_invalidation(self, plan: MappingInvalidationPlan) -> str | None:
        """Execute a plan, once the DB write it belongs to has committed.

        Returns None on success, or a user-facing warning when the cache could
        not be cleared. It never raises: the DB write has already committed by
        the time this runs, so failing the request would report "not saved"
        about a mapping that was in fact saved.
        """
        if plan.is_noop:
            return None
        if plan.warning:
            return plan.warning
        try:
            self._delete_cache_keys(list(plan.doomed_keys))
            # The unmapped view is the complement of every mapping, so any
            # mapping write changes it regardless of which account moved.
            cache.delete_prefix("unmapped_resources:")
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Mapping cache invalidation failed for accounts=%s: %s",
                list(plan.account_ids),
                exc,
            )
            return MAPPING_CACHE_WARNING

        if not plan.doomed_keys:
            # Not necessarily a bug (the customer may never have been viewed),
            # but a silent miss looks identical to success, so say so out loud.
            logger.warning(
                "Mapping cache invalidation deleted nothing for accounts=%s (scanned=%d)",
                list(plan.account_ids),
                plan.scanned_count,
            )
        else:
            logger.info(
                "Mapping cache invalidation deleted %d keys for names=%s",
                len(plan.doomed_keys),
                list(plan.matched_names),
            )

        if plan.matched_names:
            # Warming is an optimisation layered on an invalidation that has
            # already succeeded (the deletes above already ran). A warm
            # failure must not be reported as a cache-invalidation failure,
            # and — critically — must not raise out of this method: the
            # debounced scheduler can fail for its own reasons (queue/network
            # errors), and that failure must not escape here.
            try:
                self._schedule_mapping_warm(plan.matched_names)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Mapping cache warm scheduling failed for names=%s: %s",
                    list(plan.matched_names),
                    exc,
                )
        return None

    def invalidate_mapping_caches(self, account_ids: set[str]) -> str | None:
        """Plan and immediately apply an invalidation for these accounts.

        Safe only for writes that do NOT touch gui_crm_customer_alias — the
        resolver reads that table, so resolving after such a write can answer
        for a state the cached views were never built under. save_source_mappings
        and seed_boyner_source_mappings write gui_crm_customer_source_mapping
        only, which the resolver never reads, so their resolution is stable
        across the write and one call is enough. Everything else must split
        plan (before the write) from apply (after the commit).
        """
        return self.apply_mapping_invalidation(self.plan_mapping_invalidation(account_ids))

    def invalidate_all_mapping_caches(self) -> str | None:
        """Drop every cached customer view. See plan_all_mapping_invalidation.

        No plan/apply split is needed: with no resolution step there is nothing
        that can go stale across the write. It must still run after the commit,
        so a reader cannot repopulate the cache from pre-write rows.
        """
        return self.apply_mapping_invalidation(self.plan_all_mapping_invalidation())

    def resolve_infra_search_name(self, display_name: str) -> str:
        """Resolve CRM display name to infra ILIKE search key."""
        netbox_value, canonical_key, _account_id = self._lookup_alias_for_display_name(display_name)
        return resolve_infra_search_name(
            display_name,
            alias_netbox_value=netbox_value,
            alias_canonical_key=canonical_key,
            netbox_tenant_names=self._load_netbox_tenant_names(),
        )

    def get_customer_list(self) -> list[str]:
        """
        Customer names for the GUI selector.

        Primary source: CRM accounts with PRJ-* project sales orders.
        Boyner remains pinned as legacy pilot; when a Boyner CRM account exists,
        its CRM display name is used instead of the manual label.
        """
        return self._load_crm_project_customer_names()

    def _customers_for_cache_rebuild(self) -> tuple[str, ...]:
        """VIP / cache-pinned customers refreshed every 15 minutes (hot tier)."""
        return self._load_cache_pinned_display_names()

    def _mapped_non_vip_customers_for_warm(self) -> tuple[str, ...]:
        """Mapped CRM project customers that are not VIP — warm tier batch queue."""
        if self._pool is None:
            return ()
        try:
            project_rows = load_project_customer_rows(self._run_query, self._run_one).rows
            flags = self._load_profile_flags_index()
            mapping_index = self._load_source_mapping_index()
            names: list[str] = []
            for row in project_rows:
                account_id = str(row.get("crm_accountid") or "").strip()
                account_name = str(row.get("crm_account_name") or account_id).strip()
                if not account_id or not account_name:
                    continue
                flag = flags.get(account_id) or {}
                if flag.get("is_vip") or flag.get("cache_pinned"):
                    continue
                mappings = mapping_index.get(account_id, [])
                if _is_mapped(mappings):
                    names.append(account_name)
            return tuple(sorted(set(names), key=str.casefold))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Mapped non-VIP warm list load failed: %s", exc)
            return ()

    def _cache_ttl_for_customer(self, customer_name: str) -> int:
        name = str(customer_name or "").strip()
        if not name:
            return CUSTOMER_DATA_CACHE_TTL_COLD
        pinned = {n.casefold() for n in self._load_cache_pinned_display_names()}
        if name.casefold() in pinned:
            return CUSTOMER_DATA_CACHE_TTL_HOT
        mapped_warm = {n.casefold() for n in self._mapped_non_vip_customers_for_warm()}
        if name.casefold() in mapped_warm:
            return CUSTOMER_DATA_CACHE_TTL_WARM
        return CUSTOMER_DATA_CACHE_TTL_COLD

    def _rebuild_customer_caches_for_customer(
        self,
        customer_name: str,
        *,
        cache_ttl: int | None = None,
    ) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "customer": customer_name,
            "ok": 0,
            "failed": 0,
            "errors": [],
        }
        for tr in cache_time_ranges():
            preset = str(tr.get("preset") or "")
            try:
                self.get_customer_resources(customer_name, tr, cache_ttl=cache_ttl)
                summary["ok"] += 1
            except Exception as exc:
                summary["failed"] += 1
                summary["errors"].append({"preset": preset, "target": "resources", "error": str(exc)})
                logger.warning(
                    "Customer cache rebuild failed for customer=%s preset=%s: %s",
                    customer_name,
                    preset,
                    exc,
                )
            try:
                self.get_customer_s3_vaults(customer_name, tr, cache_ttl=cache_ttl)
                summary["ok"] += 1
            except Exception as exc:
                summary["failed"] += 1
                summary["errors"].append({"preset": preset, "target": "s3", "error": str(exc)})
                logger.warning(
                    "Customer S3 cache rebuild failed for customer=%s preset=%s: %s",
                    customer_name,
                    preset,
                    exc,
                )
        # Unique-jobs inventory: default time range only (Backup & Replication
        # table view doesn't need every cache_time_ranges() preset warmed).
        for vendor in self._UNIQUE_JOBS_VENDORS:
            try:
                self.get_customer_unique_jobs(customer_name, vendor)
                summary["ok"] += 1
            except Exception as exc:
                summary["failed"] += 1
                summary["errors"].append(
                    {"preset": "default", "target": f"unique_jobs_{vendor}", "error": str(exc)}
                )
                logger.warning(
                    "Customer unique-jobs cache rebuild failed for customer=%s vendor=%s: %s",
                    customer_name,
                    vendor,
                    exc,
                )
        return summary

    def _batch_warm_already_running(self) -> bool:
        try:
            status = cache.get(BATCH_WARM_STATUS_KEY)
            if isinstance(status, dict) and str(status.get("status") or "").lower() == "running":
                return True
        except Exception:  # noqa: BLE001
            pass
        return False

    def warm_mapped_non_vip_batch(self) -> None:
        """Sequentially warm mapped non-VIP customers; runs on a 6-hour scheduler cadence."""
        if self._pool is None:
            logger.warning("warm_mapped_non_vip_batch skipped: database pool is not available.")
            return
        if self._batch_warm_already_running():
            logger.info("warm_mapped_non_vip_batch skipped: another batch warm is already running.")
            return
        customers = self._mapped_non_vip_customers_for_warm()
        total = len(customers)
        logger.info("Customer API mapped batch warm started (%d customers).", total)
        cache.set(BATCH_WARM_STATUS_KEY, {"status": "running", "total": total, "completed": 0}, ttl=86400)
        completed = 0
        t0 = time.perf_counter()
        for customer_name in customers:
            completed += 1
            logger.info(
                "Customer API mapped batch warm %d/%d: %s",
                completed,
                total,
                customer_name,
            )
            self._rebuild_customer_caches_for_customer(
                customer_name,
                cache_ttl=CUSTOMER_DATA_CACHE_TTL_WARM,
            )
            if completed < total:
                time.sleep(1)
        elapsed = time.perf_counter() - t0
        completed_at = datetime.now(timezone.utc).isoformat()
        cache.set(
            BATCH_WARM_COMPLETED_KEY,
            {"completed_at": completed_at, "customer_count": total, "elapsed_seconds": round(elapsed, 2)},
            ttl=86400,
        )
        cache.set(
            BATCH_WARM_STATUS_KEY,
            {"status": "idle", "total": total, "completed": total, "last_completed_at": completed_at},
            ttl=86400,
        )
        logger.info(
            "Customer API mapped batch warm finished (%d customers in %.2fs).",
            total,
            elapsed,
        )

    @staticmethod
    def _merge_customer_names(*name_groups: tuple[str, ...] | list[str]) -> tuple[str, ...]:
        out: list[str] = []
        seen: set[str] = set()
        for group in name_groups:
            for name in group or []:
                cleaned = str(name or "").strip()
                if not cleaned:
                    continue
                key = cleaned.casefold()
                if key in seen:
                    continue
                seen.add(key)
                out.append(cleaned)
        return tuple(out)

    def _load_profile_flags_index(self) -> dict[str, dict[str, Any]]:
        webui = self._webui
        if webui is None or not getattr(webui, "is_available", False):
            return {}
        try:
            rows = webui.run_rows(smq.LIST_PROFILE_FLAGS)
            return {str(r.get("crm_accountid")): r for r in rows if r.get("crm_accountid")}
        except Exception as exc:
            logger.warning("Profile flags load failed: %s", exc)
            return {}

    def _load_mapping_count_index(self) -> dict[str, int]:
        webui = self._webui
        if webui is None or not getattr(webui, "is_available", False):
            return {}
        try:
            rows = webui.run_rows(smq.MAPPING_COUNTS_BY_ACCOUNT)
            return {
                str(r.get("crm_accountid")): int(r.get("enabled_mapping_count") or 0)
                for r in rows
                if r.get("crm_accountid")
            }
        except Exception as exc:
            logger.warning("Mapping count load failed: %s", exc)
            return {}

    def _load_source_mapping_index(self) -> dict[str, list[dict[str, Any]]]:
        webui = self._webui
        if webui is None or not getattr(webui, "is_available", False):
            return {}
        try:
            from app.services.customer_mapping_resolver import group_mappings_by_account

            rows = webui.run_rows(smq.LIST_SOURCE_MAPPINGS)
            return group_mappings_by_account(rows)
        except Exception as exc:
            logger.warning("Source mapping index load failed: %s", exc)
            return {}

    def _load_cache_pinned_display_names(self) -> tuple[str, ...]:
        if self._pool is None:
            return ()
        try:
            project_rows = load_project_customer_rows(self._run_query, self._run_one).rows
            flags = self._load_profile_flags_index()
            names: list[str] = []
            for row in project_rows:
                account_id = str(row.get("crm_accountid") or "")
                flag = flags.get(account_id) or {}
                if not (flag.get("is_vip") or flag.get("cache_pinned")):
                    continue
                name = str(row.get("crm_account_name") or "").strip()
                if name:
                    names.append(name)
            return tuple(names)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cache pinned display names load failed: %s", exc)
            return ()

    def _run_query(self, sql: str, params: tuple) -> list[dict[str, Any]]:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                if cur.description is None:
                    return []
                cols = [desc[0] for desc in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]

    def _run_one(self, sql: str, params: tuple) -> dict[str, Any] | None:
        rows = self._run_query(sql, params)
        return rows[0] if rows else None

    def _load_compliance_price_indexes(self) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
        price_overrides: dict[str, float] = {}
        catalog_by_productid: dict[str, float] = {}
        catalog_by_name: dict[str, float] = {}
        webui = self._webui
        if webui is not None and getattr(webui, "is_available", False):
            try:
                cfg = CrmConfigService(webui)
                price_overrides = {
                    str(r["productid"]): float(r["unit_price_tl"])
                    for r in cfg.list_price_overrides()
                    if r.get("productid")
                }
            except Exception as exc:
                logger.warning("Compliance price override load failed: %s", exc)
        if self._pool is not None:
            try:
                for row in self._run_query(crm_sq.SALES_CATALOG_PRICES, ()):
                    pid = str(row.get("productid") or "")
                    price = row.get("catalog_unit_price")
                    if pid and price is not None and pid not in catalog_by_productid:
                        catalog_by_productid[pid] = float(price)
                names = catalog_product_names_for_compliance()
                if names:
                    for row in self._run_query(crm_sq.SALES_CATALOG_PRICE_BY_PRODUCT_NAME, (names,)):
                        name = str(row.get("product_name") or "").strip()
                        price = row.get("catalog_unit_price")
                        if name and price is not None and name not in catalog_by_name:
                            catalog_by_name[name] = float(price)
            except Exception as exc:
                logger.warning("Compliance catalog price load failed: %s", exc)
        return price_overrides, catalog_by_productid, catalog_by_name

    def _cached_customer_bundle(self, display_name: str) -> dict[str, Any] | None:
        tr = default_time_range()
        cache_key = customer_assets_cache_key(display_name, tr.get("start", ""), tr.get("end", ""))
        try:
            hit = cache.get(cache_key)
            if isinstance(hit, dict):
                return hit
        except Exception:
            return None
        return None

    def get_customer_catalog(self, *, use_snapshot_cache: bool = True) -> dict[str, Any]:
        if use_snapshot_cache:
            try:
                cached = cache.get(CATALOG_SNAPSHOT_KEY)
                if isinstance(cached, dict) and isinstance(cached.get("customers"), list):
                    return cached
            except Exception:  # noqa: BLE001
                pass
        result = self._build_customer_catalog()
        if use_snapshot_cache and not result.get("degraded"):
            try:
                cache.set(CATALOG_SNAPSHOT_KEY, result, ttl=CATALOG_SNAPSHOT_TTL_SECONDS)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to cache customer catalog snapshot: %s", exc)
        return result

    def _build_customer_catalog(self) -> dict[str, Any]:
        project_load = load_project_customer_rows(self._run_query, self._run_one)
        project_rows = project_load.rows
        flags = self._load_profile_flags_index()
        mapping_index = self._load_source_mapping_index()
        account_ids = [str(r.get("crm_accountid")) for r in project_rows if r.get("crm_accountid")]
        ytd_index: dict[str, dict[str, Any]] = {}
        active_index: dict[str, dict[str, Any]] = {}
        entitled_by_customer: dict[str, list[dict[str, Any]]] = {}
        weighted_by_customer: dict[str, dict[str, float]] = {}
        product_mapping: dict[str, dict[str, Any]] = {}
        under_pct = 80.0
        over_pct = 110.0

        if account_ids and self._pool is not None:
            try:
                for row in self._run_query(crm_sq.CRM_PROJECT_SALES_BY_CUSTOMER_YTD, (account_ids,)):
                    ytd_index[str(row.get("crm_accountid"))] = row
            except Exception as exc:
                logger.warning("Customer YTD sales lookup failed: %s", exc)
            try:
                for row in self._run_query(crm_sq.CRM_PROJECT_ACTIVE_ORDERS_BY_CUSTOMER, (account_ids,)):
                    active_index[str(row.get("crm_accountid"))] = row
            except Exception as exc:
                logger.warning("Customer active orders lookup failed: %s", exc)
            try:
                entitled_by_customer = group_entitled_by_customer(
                    self._run_query(crm_sq.SALES_ENTITLED_RAW_BY_CUSTOMER_PRODUCT, (account_ids,))
                )
            except Exception as exc:
                logger.warning("Customer entitled sales lookup failed: %s", exc)
            try:
                weighted_by_customer = group_weighted_prices_by_customer(
                    self._run_query(crm_sq.SALES_ENTITLED_UNIT_PRICE_BY_CUSTOMER_PRODUCT, (account_ids,))
                )
            except Exception as exc:
                logger.warning("Customer entitled unit price lookup failed: %s", exc)

        webui = self._webui
        if webui is not None and getattr(webui, "is_available", False):
            try:
                rows = webui.run_rows(smq.LIST_SERVICE_MAPPINGS_WEBUI)
                product_mapping = {str(r["productid"]): r for r in rows if r.get("productid")}
                cfg = CrmConfigService(webui)
                calc = cfg.get_calc_dict()
                under_pct = float(calc.get("efficiency.under_pct", 80.0))
                over_pct = float(calc.get("efficiency.over_pct", 110.0))
            except Exception as exc:
                logger.warning("Catalog compliance mapping load failed: %s", exc)

        price_overrides, catalog_by_productid, catalog_by_name = self._load_compliance_price_indexes()

        catalog_rows: list[dict[str, Any]] = []
        for row in project_rows:
            account_id = str(row.get("crm_accountid") or "").strip()
            account_name = str(row.get("crm_account_name") or account_id).strip()
            if not account_id:
                continue
            flag = flags.get(account_id) or {}
            ytd = ytd_index.get(account_id) or {}
            active = active_index.get(account_id) or {}
            currency = ytd.get("currency") or active.get("currency")
            source_mappings = mapping_index.get(account_id, [])
            mapped = _is_mapped(source_mappings)
            has_cache = self._cached_customer_bundle(account_name) is not None
            compliance_summary = None
            if mapped and has_cache:
                bundle = self._cached_customer_bundle(account_name) or {}
                try:
                    compliance_summary = build_lightweight_compliance_from_bundle(
                        entitled_raw=entitled_by_customer.get(account_id, []),
                        product_mapping=product_mapping,
                        assets=bundle.get("assets") or {},
                        totals=bundle.get("totals") or {},
                        weighted_prices=weighted_by_customer.get(account_id, {}),
                        price_overrides=price_overrides,
                        catalog_by_productid=catalog_by_productid,
                        catalog_by_name=catalog_by_name,
                        under_pct=under_pct,
                        over_pct=over_pct,
                    )
                except Exception as exc:
                    logger.warning("Catalog overuse check failed for %s: %s", account_name, exc)
            overuse_status = derive_catalog_overuse_status(
                mapped=mapped,
                has_infra_cache=has_cache,
                compliance_summary=compliance_summary,
            )
            catalog_rows.append(
                build_catalog_row(
                    crm_accountid=account_id,
                    crm_account_name=account_name,
                    source_mappings=source_mappings,
                    is_vip=bool(flag.get("is_vip")),
                    cache_pinned=bool(flag.get("cache_pinned") or flag.get("is_vip")),
                    ytd_revenue=float(ytd.get("ytd_revenue") or 0.0),
                    active_order_value=float(active.get("active_order_value") or 0.0),
                    active_order_count=int(active.get("active_order_count") or 0),
                    currency=currency,
                    overuse_status=overuse_status,
                )
            )

        groups = group_catalog_rows(catalog_rows)
        webui_degraded = self._webui is None or not getattr(self._webui, "is_available", False)
        return {
            "customers": catalog_rows,
            "groups": groups,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "degraded": bool(project_load.degraded or webui_degraded),
            "prj_query_failed": project_load.prj_query_failed,
            "webui_unavailable": webui_degraded,
        }

    def get_customer_overview(self) -> dict[str, Any]:
        catalog = self.get_customer_catalog()
        catalog_rows = catalog.get("customers") or []
        sales_total: dict[str, Any] = {
            "total_revenue": 0.0,
            "currency": None,
            "order_count": 0,
        }
        raw_lines: list[dict[str, Any]] = []
        if self._pool is not None:
            try:
                sales_total = self._run_one(crm_sq.CRM_PROJECT_SALES_TOTAL, ()) or sales_total
                raw_lines = self._run_query(crm_sq.CRM_PROJECT_SALES_LINES_BY_PRODUCT, ())
            except Exception as exc:
                logger.warning("Customer overview sales query failed: %s", exc)

        product_mapping: dict[str, dict[str, Any]] = {}
        webui = self._webui
        if webui is not None and getattr(webui, "is_available", False):
            try:
                rows = webui.run_rows(smq.LIST_SERVICE_MAPPINGS_WEBUI)
                product_mapping = {str(r["productid"]): r for r in rows if r.get("productid")}
            except Exception as exc:
                logger.warning("Overview product mapping load failed: %s", exc)

        service_sales = map_service_sales_lines(raw_lines, product_mapping)
        overview = build_overview_payload(
            catalog_rows=catalog_rows,
            sales_total=sales_total or {},
            service_sales=service_sales,
        )
        overview["catalog"] = {
            "customers": catalog.get("customers") or [],
            "groups": catalog.get("groups") or {},
            "generated_at": catalog.get("generated_at"),
            "degraded": catalog.get("degraded"),
            "prj_query_failed": catalog.get("prj_query_failed"),
            "webui_unavailable": catalog.get("webui_unavailable"),
        }
        return overview

    def set_customer_vip(self, crm_accountid: str, *, is_vip: bool, updated_by: str | None = None) -> dict[str, Any]:
        webui = self._webui
        if webui is None or not getattr(webui, "is_available", False):
            raise RuntimeError("WebUI pool not configured")
        account_id = (crm_accountid or "").strip()
        if not account_id:
            raise ValueError("crm_accountid is required")
        cache_pinned = bool(is_vip)
        webui.execute(
            smq.UPSERT_PROFILE_VIP,
            (account_id, bool(is_vip), cache_pinned, updated_by),
        )
        try:
            cache.delete(CATALOG_SNAPSHOT_KEY)
        except Exception:  # noqa: BLE001
            pass
        result = {
            "status": "ok",
            "crm_accountid": account_id,
            "is_vip": bool(is_vip),
            "cache_pinned": cache_pinned,
        }
        if is_vip:
            display_name = self._display_name_for_account(account_id)
            if display_name:
                threading.Thread(
                    target=self._rebuild_customer_caches_for_customer,
                    kwargs={
                        "customer_name": display_name,
                        "cache_ttl": CUSTOMER_DATA_CACHE_TTL_HOT,
                    },
                    name=f"vip-warm-{account_id}",
                    daemon=True,
                ).start()
        return result

    def _display_name_for_account(self, crm_accountid: str) -> str | None:
        if self._pool is None:
            return None
        try:
            for row in load_project_customer_rows(self._run_query, self._run_one).rows:
                if str(row.get("crm_accountid") or "").strip() == crm_accountid:
                    name = str(row.get("crm_account_name") or "").strip()
                    return name or None
        except Exception as exc:
            logger.warning("Display name lookup failed for account=%s: %s", crm_accountid, exc)
        return None

    def _fetch_customer_s3_vaults(self, customer_name: str, start_ts, end_ts) -> dict:
        """Fetch S3 vault metrics for a customer (same logic as datacenter-api DatabaseService)."""
        source_patterns = self.resolve_source_patterns(customer_name)
        patterns = source_patterns.ilike_patterns("s3_icos")
        if not patterns:
            search_name = self.resolve_infra_search_name(customer_name)
            patterns = [f"%{(search_name or customer_name or '').strip()}%"]

        vault_names: set[str] = set()
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                for pattern in patterns:
                    vault_rows = self._run_rows(
                        cur,
                        s3q.VAULT_LIST,
                        (pattern, start_ts, end_ts),
                    )
                    for row in (vault_rows or []):
                        if row and row[0]:
                            vault_names.add(str(row[0]))
                vaults = sorted(vault_names)
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

    def get_customer_s3_vaults(self, customer_name: str, time_range: dict | None = None, *, cache_ttl: int | None = None) -> dict:
        """Return cached S3 vault metrics for a customer and time range."""
        tr = time_range or default_time_range()
        start_ts, end_ts = time_range_to_bounds(tr)
        cache_key = f"customer_s3:{customer_name}:{tr.get('start','')}:{tr.get('end','')}"
        ttl = cache_ttl if cache_ttl is not None else self._cache_ttl_for_customer(customer_name)

        try:
            return cache.run_singleflight(
                cache_key,
                lambda: self._fetch_customer_s3_vaults(customer_name, start_ts, end_ts),
                ttl=ttl,
            )
        except QueryTimeoutError as exc:
            logger.warning(
                "get_customer_s3_vaults timed out for %s; trying stale cache key=%s: %s",
                customer_name,
                cache_key,
                exc,
            )
            stale = cache.get(cache_key)
            if stale is not None:
                return stale
            return {"vaults": [], "latest": {}, "growth": {}, "trend": []}
        except (OperationalError, PoolError, InterfaceError) as exc:
            logger.warning(
                "get_customer_s3_vaults failed for %s (not cached); correlation key=%s: %s",
                customer_name,
                cache_key,
                exc,
            )
            return {"vaults": [], "latest": {}, "growth": {}, "trend": []}

    # ------------------------------------------------------------------
    # Unique-job inventory (Backup & Replication → per-vendor table view,
    # customer-scoped). Mirrors datacenter-api's DatabaseService.get_dc_unique_jobs*
    # (same row shape / aggregation via shared.backup.unique_jobs) but resolves
    # the customer's own ILIKE patterns instead of DC attribution.
    # ------------------------------------------------------------------

    _UNIQUE_JOBS_VENDORS = ("veeam", "zerto", "netbackup")
    _UNIQUE_JOBS_PATTERN_SOURCE = {
        "veeam": "backup_veeam",
        "zerto": "backup_zerto",
        "netbackup": "backup_netbackup",
    }
    _UNIQUE_JOBS_FRESH_TTL = 2100
    _UNIQUE_JOBS_STALE_TTL = 86400

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _normalize_zerto_status(raw) -> str:
        """Zerto VPG status enum: 1=MeetingSLA (success), 2/3=problematic, 0/5=in-progress, 4=removing.
        Kept in sync with datacenter-api's DatabaseService._normalize_zerto_status."""
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
        """NetBackup exit code: 0=success, 1=partial(warning), other=failed.
        Kept in sync with datacenter-api's DatabaseService._normalize_netbackup_status."""
        try:
            code = int(raw)
        except (TypeError, ValueError):
            return "other"
        if code == 0:
            return "success"
        if code == 1:
            return "warning"
        return "failed"

    @staticmethod
    def _map_veeam_unique_row(row: tuple) -> dict:
        (
            collection_time, id_, name, type_, status, last_result, last_run,
            objects_count, session_id, workload, source_ip,
        ) = row
        return {
            "collection_time": collection_time,
            "id": id_,
            "name": name,
            "type": type_,
            "status": status,
            "last_result": last_result,
            "last_run": last_run,
            "objects_count": objects_count,
            "session_id": session_id,
            "workload": workload,
            "source_ip": source_ip,
        }

    @classmethod
    def _map_zerto_unique_row(cls, row: tuple) -> dict:
        (
            collection_timestamp, id_, name, status, vmscount, source_site,
            target_site, provisioned_storage_mb, used_storage_mb, zerto_host,
        ) = row
        return {
            "collection_timestamp": collection_timestamp,
            "id": id_,
            "name": name,
            "status": cls._normalize_zerto_status(status),
            "vmscount": vmscount,
            "source_site": source_site,
            "target_site": target_site,
            "provisioned_storage_mb": provisioned_storage_mb,
            "used_storage_mb": used_storage_mb,
            "zerto_host": zerto_host,
        }

    @classmethod
    def _map_netbackup_unique_row(cls, row: tuple) -> dict:
        (
            starttime, endtime, jobid, policyname, policytype, jobtype, status,
            workloaddisplayname, clientname, destinationmediaservername,
            kilobytestransferred, dedupratio, percentcomplete,
        ) = row
        return {
            "starttime": starttime,
            "endtime": endtime,
            "jobid": jobid,
            "policyname": policyname,
            "policytype": policytype,
            "jobtype": jobtype,
            "status": cls._normalize_netbackup_status(status),
            "workloaddisplayname": workloaddisplayname,
            "clientname": clientname,
            "destinationmediaservername": destinationmediaservername,
            "kilobytestransferred": kilobytestransferred,
            "dedupratio": dedupratio,
            "percentcomplete": percentcomplete,
            "category": classify_netbackup_policy(policytype),
        }

    def _map_unique_row(self, vendor: str, row: tuple) -> dict:
        if vendor == "veeam":
            return self._map_veeam_unique_row(row)
        if vendor == "zerto":
            return self._map_zerto_unique_row(row)
        if vendor == "netbackup":
            return self._map_netbackup_unique_row(row)
        return {}

    def _unique_jobs_patterns(self, customer_name: str, vendor: str) -> list[str]:
        """Resolved ILIKE pattern(s) for a vendor's backup dataset (name/workload column)."""
        source_key = self._UNIQUE_JOBS_PATTERN_SOURCE.get(vendor)
        if not source_key:
            return []
        try:
            source_patterns = self.resolve_source_patterns(customer_name)
            patterns = source_patterns.ilike_patterns(source_key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Unique-jobs pattern resolve failed for %s/%s: %s", customer_name, vendor, exc)
            patterns = []
        if patterns:
            return list(patterns)
        search_name = self.resolve_infra_search_name(customer_name)
        fallback = (search_name or customer_name or "").strip()
        return [f"%{fallback}%"] if fallback else ["%"]

    def _fetch_customer_unique_jobs(self, customer_name: str, vendor: str, start_ts, end_ts) -> dict:
        """Latest-per-identity rows for a customer (one vendor), pattern-filtered + normalized.

        Mirrors CustomerAdapter's `_resolve_patterns` usage: Veeam/NetBackup use
        only the first (highest-priority) resolved pattern, same as
        `_customer.fetch()` does for `veeam_pattern` / `netbackup_workload_pattern`.
        Zerto merges every resolved pattern (dedup by VPG id) since a customer's
        VPGs can be named after more than one source naming convention.
        """
        sql_map = {
            "veeam": cq.CUSTOMER_VEEAM_UNIQUE_JOBS_LATEST,
            "zerto": cq.CUSTOMER_ZERTO_UNIQUE_VPGS_LATEST,
            "netbackup": cq.CUSTOMER_NETBACKUP_UNIQUE_JOBS_LATEST,
        }
        sql = sql_map.get(vendor)
        if sql is None:
            return {"rows": [], "totals": aggregate_unique_jobs([], vendor), "as_of": "", "vendor": vendor}

        patterns = self._unique_jobs_patterns(customer_name, vendor)
        query_patterns = patterns if vendor == "zerto" else patterns[:1]

        rows: list[dict] = []
        seen_ids: set[str] = set()
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                for pattern in query_patterns:
                    raw = self._run_rows(cur, sql, (pattern, start_ts, end_ts))
                    for r in raw or []:
                        mapped = self._map_unique_row(vendor, r)
                        dedupe_key = str(mapped.get("id") or mapped.get("jobid") or "")
                        if dedupe_key:
                            if dedupe_key in seen_ids:
                                continue
                            seen_ids.add(dedupe_key)
                        rows.append(mapped)

        normalized = normalize_unique_job_rows(rows)
        return {
            "rows": normalized,
            "totals": aggregate_unique_jobs(normalized, vendor),
            "as_of": self._utc_now_iso(),
            "vendor": vendor,
        }

    def _trigger_async_unique_jobs_refresh(self, cache_key: str, factory) -> None:
        sf_key = f"_sf:{cache_key}"

        def _bg() -> None:
            try:
                result = cache.run_singleflight(sf_key, factory, ttl=60)
                cache.set_with_stale(
                    cache_key, result,
                    fresh_ttl=self._UNIQUE_JOBS_FRESH_TTL,
                    stale_ttl=self._UNIQUE_JOBS_STALE_TTL,
                )
            except Exception as exc:  # noqa: BLE001 — background log only
                logger.warning("Stale-revalidate unique_jobs (%s) failed: %s", cache_key, exc)

        threading.Thread(target=_bg, daemon=True, name="cust-unique-jobs-refresh").start()

    def get_customer_unique_jobs(self, customer_name: str, vendor: str, time_range: dict | None = None) -> dict:
        """Cached base row set (rows + totals) for a customer/vendor. SWR + singleflight."""
        vendor_key = (vendor or "").strip().lower()
        tr = time_range or default_time_range()
        start_ts, end_ts = time_range_to_bounds(tr)
        cache_key = f"cust_{vendor_key}_unique_jobs:{customer_name}:{tr.get('start', '')}:{tr.get('end', '')}"

        def factory():
            try:
                return self._fetch_customer_unique_jobs(customer_name, vendor_key, start_ts, end_ts)
            except (OperationalError, PoolError, InterfaceError) as exc:
                logger.warning(
                    "get_customer_unique_jobs failed for %s/%s: %s", customer_name, vendor_key, exc,
                )
                return {
                    "rows": [], "totals": aggregate_unique_jobs([], vendor_key), "as_of": "", "vendor": vendor_key,
                }

        cached_val, is_stale = cache.get_with_stale(cache_key)
        if cached_val is not None:
            if is_stale:
                self._trigger_async_unique_jobs_refresh(cache_key, factory)
            return cached_val

        result = cache.run_singleflight(cache_key, factory)
        cache.set_with_stale(
            cache_key, result,
            fresh_ttl=self._UNIQUE_JOBS_FRESH_TTL,
            stale_ttl=self._UNIQUE_JOBS_STALE_TTL,
        )
        return result

    def get_customer_unique_jobs_table(
        self,
        customer_name: str,
        vendor: str,
        time_range: dict | None = None,
        *,
        page: int = 1,
        page_size: int = 50,
        search: str = "",
        statuses: list[str] | None = None,
        types: list[str] | None = None,
        policy_types: list[str] | None = None,
        categories: list[str] | None = None,
        platforms: list[str] | None = None,
    ) -> dict:
        """Paged/filtered view derived in-process from the cached base row set.

        Filters never bust the cache key; totals are recomputed over the
        filtered set so the customer-view KPI/status/type charts stay in sync
        with whatever rows are currently shown in the table.
        """
        vendor_key = (vendor or "").strip().lower()
        base = self.get_customer_unique_jobs(customer_name, vendor_key, time_range)
        rows = base.get("rows", [])
        filtered = filter_unique_job_rows(
            rows,
            search=search,
            statuses=statuses,
            types=types,
            policy_types=policy_types,
            categories=categories,
            platforms=platforms,
        )
        result = paginate_unique_job_rows(filtered, page, page_size)
        result["totals"] = aggregate_unique_jobs(filtered, vendor_key)
        result["vendor"] = vendor_key
        return result

    def warm_customer_unique_jobs(self, customer_name: str) -> None:
        """Warm the unique-jobs cache for one customer × all 3 vendors × default
        time range. Called from `_rebuild_customer_caches_for_customer` so hot
        (VIP/pinned) and warm (mapped non-VIP) tiers pick it up automatically;
        also callable standalone from a scheduler hook if a dedicated cadence
        is ever needed for this dataset."""
        for vendor in self._UNIQUE_JOBS_VENDORS:
            try:
                self.get_customer_unique_jobs(customer_name, vendor)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "warm_customer_unique_jobs failed for customer=%s vendor=%s: %s",
                    customer_name, vendor, exc,
                )

    def _rebuild_customer_caches_for_warmed_customers(self) -> None:
        """Populate Redis/memory cache for VIP / cache-pinned customers (hot tier)."""
        customers = self._customers_for_cache_rebuild()
        total = len(customers)
        started_at = datetime.now(timezone.utc).isoformat()
        cache.set(
            HOT_WARM_STATUS_KEY,
            {"status": "running", "total": total, "completed": 0, "started_at": started_at},
            ttl=86400,
        )
        customer_summaries: list[dict[str, Any]] = []
        ok_total = 0
        failed_total = 0
        for customer_name in customers:
            row = self._rebuild_customer_caches_for_customer(
                customer_name,
                cache_ttl=CUSTOMER_DATA_CACHE_TTL_HOT,
            )
            customer_summaries.append(row)
            ok_total += int(row.get("ok") or 0)
            failed_total += int(row.get("failed") or 0)
        completed_at = datetime.now(timezone.utc).isoformat()
        status_payload = {
            "status": "idle",
            "total": total,
            "completed": total,
            "started_at": started_at,
            "completed_at": completed_at,
            "ok_total": ok_total,
            "failed_total": failed_total,
            "customers": customer_summaries,
        }
        cache.set(HOT_WARM_STATUS_KEY, status_payload, ttl=86400)
        if failed_total:
            logger.error(
                "VIP hot-tier cache refresh completed with failures: customers=%d ok_ops=%d failed_ops=%d",
                total,
                ok_total,
                failed_total,
            )
        else:
            logger.info(
                "VIP hot-tier cache refresh complete: customers=%d ok_ops=%d",
                total,
                ok_total,
            )

    def refresh_warm_tier_caches(self) -> None:
        """Rebuild mapped non-VIP customer caches (warm tier) without flushing Redis."""
        if self._pool is None:
            logger.warning("refresh_warm_tier_caches skipped: database pool is not available.")
            return
        customers = self._mapped_non_vip_customers_for_warm()
        total = len(customers)
        if total == 0:
            logger.info("Customer API warm-tier refresh: no mapped non-VIP customers.")
            return
        logger.info("Customer API warm-tier refresh started (%d customers).", total)
        for customer_name in customers:
            self._rebuild_customer_caches_for_customer(
                customer_name,
                cache_ttl=CUSTOMER_DATA_CACHE_TTL_WARM,
            )
        logger.info("Customer API warm-tier refresh complete (%d customers).", total)

    def refresh_all_tier_caches(self) -> None:
        """Rebuild hot (VIP/pinned) and warm (mapped non-VIP) tiers — stale until overwrite."""
        if self._pool is None:
            logger.warning("refresh_all_tier_caches skipped: database pool is not available.")
            return
        self._rebuild_customer_caches_for_warmed_customers()
        self.refresh_warm_tier_caches()

    def warm_cache(self) -> None:
        """Synchronous warm-up before serving traffic (VIP/pinned hot tier only)."""
        if self._pool is None:
            logger.warning("warm_cache skipped: database pool is not available.")
            return
        self._rebuild_customer_caches_for_warmed_customers()

    def refresh_all_data(self) -> None:
        """
        Called by the background scheduler every 15 minutes.
        Rebuilds VIP/pinned hot-tier caches only (mapped warm tier uses the 6h batch job).
        """
        logger.info("Customer API background hot-tier cache refresh started.")
        try:
            self._rebuild_customer_caches_for_warmed_customers()
            logger.info("Customer API background hot-tier cache refresh complete.")
        except Exception as exc:
            logger.error("Customer API background hot-tier cache refresh failed: %s", exc)
