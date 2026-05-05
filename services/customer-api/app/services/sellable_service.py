"""SellableService — orchestrates the C-level CRM Sellable Potential pipeline.

Per panel:
    1. Fetch InfraSource (panel_key, dc_code) from webui-db.
    2. Build a parameterised total / allocated SQL against the datalake DB
       using the descriptor's table/column/filter_clause.
    3. Convert raw values into the panel's display_unit via gui_unit_conversion.
    4. Apply the per-panel / per-resource_type threshold (sellable_raw).
    5. Apply the per-environment ratio (constrained sellable).
    6. Resolve the unit price (override > catalog TL > 0) via webui-db /
       discovery_crm_productpricelevels.
    7. Emit MetricValues into TaggingService cache + (optionally) snapshot.

Design notes:
    * ``datacenter_metrics`` / ``cluster_metrics``: totals use the latest snapshot per
      (dc, datacenter) / (cluster, datacenter) before SUM — same grain as WebUI
      ``datacenter-api`` ``vmware.py`` queries — see ``_sum_sql``.
    * ``vm_metrics`` / ``nutanix_vm_metrics``: **allocated** values are read from the
      datacenter-api Redis cache (``dc_details:{dc_code}:{start}:{end}`` or
      ``global_dashboard:{start}:{end}``), not queried from the datalake DB.
      This avoids expensive full-table VM scans, stale-VM inclusion, and the
      ``uuid = character varying`` type mismatch in the Nutanix JOIN.
    * Each datalake query is small (one SUM per call) so the per-panel cost
      is dominated by network RTT. ``CustomerService`` already pools 8
      connections; the dashboard fetches at most ~70 panels per call.
    * Per-DC results respect the same filter clause; ``dc_code='*'`` returns
      a global aggregate (no filter).
    * Snapshots are written by ``snapshot_all`` which is wired to the
      APScheduler refresh interval.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import re
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Iterable

import httpx

from app.utils.storage_capacity_parse import parse_storage_string_to_gb

if TYPE_CHECKING:
    import redis as _redis_t

# VMware TS tables: WebUI uses latest row per (dc, datacenter) / (cluster, datacenter)
# before SUM — see datacenter-api app/db/queries/vmware.py (BATCH_*, CLASSIC_METRICS).
_SUBQUERY_DATACENTER_METRICS_LATEST = """(
    SELECT DISTINCT ON (dc, datacenter)
        *
    FROM datacenter_metrics
    ORDER BY dc, datacenter, "timestamp" DESC
) AS _infra_dm"""

_SUBQUERY_CLUSTER_METRICS_LATEST = """(
    SELECT DISTINCT ON (cluster, datacenter)
        *
    FROM cluster_metrics
    ORDER BY cluster, datacenter, "timestamp" DESC
) AS _infra_cm"""

# nutanix_cluster_metrics: take the latest row per cluster_uuid before SUM so
# repeated time-series snapshots are not double-counted.
_SUBQUERY_NUTANIX_CLUSTER_LATEST = """(
    SELECT DISTINCT ON (cluster_uuid)
        *
    FROM nutanix_cluster_metrics
    ORDER BY cluster_uuid, collection_time DESC
) AS _infra_ncm"""

# -- Redis-backed allocated lookup (vm_metrics / nutanix_vm_metrics) -----------

# How many days back to use when constructing the dc_details Redis key.
# MUST match the window used by datacenter-api's default_time_range (7 d).
# Override with SELLABLE_REDIS_WINDOW_DAYS env var.
_DC_DETAILS_WINDOW_DAYS: int = int(os.getenv("SELLABLE_REDIS_WINDOW_DAYS", "7"))

# TTL (seconds) for compute_all_panels result in crm-engine Redis (DB 2).
# 0 disables caching. Override with SELLABLE_CACHE_TTL_SECONDS.
_SELLABLE_CACHE_TTL: int = int(os.getenv("SELLABLE_CACHE_TTL_SECONDS", "120"))

# Maps allocated_table → Redis section key for per-DC (dc_details) response.
_VM_TABLE_DC_SECTION: dict[str, str] = {
    "vm_metrics":         "classic",
    "nutanix_vm_metrics": "hyperconv",
}

# Maps allocated_table → Redis section key for global (global_dashboard) response.
_VM_TABLE_GLOBAL_SECTION: dict[str, str] = {
    "vm_metrics":         "classic_totals",
    "nutanix_vm_metrics": "hyperconv_totals",
}

# Maps allocated_column (as configured in gui_panel_infra_source) → Redis field.
# Values are the exact field names present in the dc_details and global_dashboard JSON.
_VM_COLUMN_TO_REDIS_FIELD: dict[str, str] = {
    # vm_metrics — classic KM VMware
    "number_of_cpus":          "cpu_used",
    "total_memory_capacity_gb": "mem_used",
    "provisioned_space_gb":    "stor_used",
    # nutanix_vm_metrics — hyperconverged Nutanix
    "cpu_count":               "cpu_used",
    "memory_capacity":         "mem_used",
    "disk_capacity":           "stor_used",
}

# -- Cluster-aware sellable -----------------------------------------------------
#
# When the caller passes a non-empty cluster list, we bypass datalake DB + Redis
# completely and read both total ("cap") and allocated ("used") from
# datacenter-api's /compute/{kind} endpoint, which is the same source the DC
# view's "Capacity Planning" card uses. This guarantees parity between the
# Sellable card and Capacity Planning numbers.

# Maps panel family → datacenter-api compute endpoint kind.
_FAMILY_COMPUTE_ENDPOINT: dict[str, str] = {
    "virt_classic":         "classic",
    "virt_hyperconverged":  "hyperconverged",
}

# Maps resource_kind → (capacity_field, used_field, source_unit) in the compute response.
_RESOURCE_KIND_TO_COMPUTE_FIELDS: dict[str, tuple[str, str, str]] = {
    "cpu":     ("cpu_cap",  "cpu_used",  "GHz"),
    "ram":     ("mem_cap",  "mem_used",  "GB"),
    "storage": ("stor_cap", "stor_used", "TB"),
}

from app.db.queries import sellable as sq
from app.services.crm_config_service import CrmConfigService
from app.services.currency_service import CurrencyService
from app.services.customer_service import CustomerService
from app.services.tagging_service import TaggingService, build_metric_key
from app.services.webui_db import WebuiPool
from shared.sellable.computation import (
    apply_threshold,
    compute_potential_tl,
    constrain_by_ratio,
    convert_unit,
)
from shared.sellable.models import (
    DashboardSummary,
    FamilyAggregate,
    InfraSource,
    MetricValue,
    PanelDefinition,
    PanelResult,
    ResourceRatio,
    UnitConversion,
)

logger = logging.getLogger(__name__)

_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

DEFAULT_THRESHOLD_PCT = 80.0
KNOWN_RESOURCE_KINDS = {"cpu", "ram", "storage", "other"}


class SellableService:
    def __init__(
        self,
        *,
        customer_service: CustomerService,
        webui: WebuiPool,
        config_service: CrmConfigService,
        currency_service: CurrencyService,
        tagging_service: TaggingService,
        datacenter_redis: "_redis_t.Redis | None" = None,
        datacenter_api_url: str = "",
        crm_redis: "_redis_t.Redis | None" = None,
    ) -> None:
        self._svc = customer_service
        self._webui = webui
        self._config = config_service
        self._currency = currency_service
        self._tags = tagging_service
        self._dc_redis = datacenter_redis
        self._dc_api_url = (datacenter_api_url or "").rstrip("/")
        self._crm_redis = crm_redis  # crm-engine's own Redis (DB 2) for result caching

    # ----------------------------------------------------------------- helpers

    @property
    def is_available(self) -> bool:
        return self._webui is not None and self._webui.is_available and self._svc._pool is not None

    # -- registry loaders (webui-db)

    def list_panel_defs(self) -> list[PanelDefinition]:
        if not self._webui.is_available:
            return []
        rows = self._webui.run_rows(sq.LIST_PANEL_DEFS)
        return [
            PanelDefinition(
                panel_key=r["panel_key"],
                label=r["label"],
                family=r["family"],
                resource_kind=r["resource_kind"],
                display_unit=r["display_unit"],
                sort_order=int(r.get("sort_order") or 100),
                enabled=bool(r.get("enabled", True)),
                notes=r.get("notes"),
            )
            for r in rows
            if r.get("enabled", True)
        ]

    def get_infra_source(self, panel_key: str, dc_code: str = "*") -> InfraSource | None:
        if not self._webui.is_available:
            return None
        row = self._webui.run_one(sq.GET_INFRA_SOURCE, (panel_key, dc_code))
        if not row:
            return InfraSource(panel_key=panel_key, dc_code=dc_code)
        return InfraSource(
            panel_key=row["panel_key"],
            dc_code=row["dc_code"],
            source_table=row.get("source_table"),
            total_column=row.get("total_column"),
            total_unit=row.get("total_unit"),
            allocated_table=row.get("allocated_table"),
            allocated_column=row.get("allocated_column"),
            allocated_unit=row.get("allocated_unit"),
            filter_clause=row.get("filter_clause"),
            notes=row.get("notes"),
        )

    def list_ratios(self) -> list[ResourceRatio]:
        if not self._webui.is_available:
            return []
        rows = self._webui.run_rows(sq.LIST_RATIOS)
        return [
            ResourceRatio(
                family=r["family"],
                dc_code=r["dc_code"],
                cpu_per_unit=float(r["cpu_per_unit"]),
                ram_gb_per_unit=float(r["ram_gb_per_unit"]),
                storage_gb_per_unit=float(r["storage_gb_per_unit"]),
                notes=r.get("notes"),
            )
            for r in rows
        ]

    def get_ratio(self, family: str, dc_code: str = "*") -> ResourceRatio:
        if not self._webui.is_available:
            return ResourceRatio(family=family, dc_code=dc_code)
        row = self._webui.run_one(sq.GET_RATIO_FOR, (family, dc_code))
        if not row:
            return ResourceRatio(family=family, dc_code=dc_code)
        return ResourceRatio(
            family=row["family"],
            dc_code=row["dc_code"],
            cpu_per_unit=float(row["cpu_per_unit"]),
            ram_gb_per_unit=float(row["ram_gb_per_unit"]),
            storage_gb_per_unit=float(row["storage_gb_per_unit"]),
            notes=row.get("notes"),
        )

    def list_unit_conversions(self) -> list[UnitConversion]:
        if not self._webui.is_available:
            return []
        rows = self._webui.run_rows(sq.LIST_UNIT_CONVERSIONS)
        return [
            UnitConversion(
                from_unit=r["from_unit"],
                to_unit=r["to_unit"],
                factor=float(r["factor"]),
                operation=r.get("operation") or "divide",
                ceil_result=bool(r.get("ceil_result")),
                notes=r.get("notes"),
            )
            for r in rows
        ]

    def _build_unit_lookup(self) -> dict[tuple[str, str], UnitConversion]:
        return {(c.from_unit, c.to_unit): c for c in self.list_unit_conversions()}

    # -- bulk loaders (replace N per-panel WebUI round-trips with 3 queries) --

    def _bulk_load_infra_sources(self, dc_code: str) -> "dict[str, InfraSource] | None":
        """Load best infra source for every panel_key in a single SQL.
        Returns None if unavailable so callers fall back to per-panel get_infra_source().
        """
        if not self._webui.is_available:
            return None
        try:
            rows = self._webui.run_rows(sq.BULK_INFRA_SOURCES_FOR_DC, (dc_code,))
            if not isinstance(rows, list):
                return None
            return {
                row["panel_key"]: InfraSource(
                    panel_key=row["panel_key"],
                    dc_code=row.get("dc_code", "*"),
                    source_table=row.get("source_table"),
                    total_column=row.get("total_column"),
                    total_unit=row.get("total_unit"),
                    allocated_table=row.get("allocated_table"),
                    allocated_column=row.get("allocated_column"),
                    allocated_unit=row.get("allocated_unit"),
                    filter_clause=row.get("filter_clause"),
                    notes=row.get("notes"),
                )
                for row in rows
            }
        except Exception:
            logger.debug("_bulk_load_infra_sources failed; will fall back to per-panel")
            return None

    def _bulk_load_thresholds(self, dc_code: str) -> "dict | None":
        """Load all threshold rows for dc_code.

        Returns a dict:
            ``{"_by_panel_key": {panel_key: pct}, "_by_resource_type": {resource_type: pct}}``
        Specific dc_code rows override wildcard ('*') rows.  Returns None on failure.
        """
        if not self._webui.is_available:
            return None
        try:
            rows = self._webui.run_rows(sq.BULK_THRESHOLDS_FOR_DC, (dc_code,))
            if not isinstance(rows, list):
                return None
        except Exception:
            logger.debug("_bulk_load_thresholds failed; will fall back to per-panel")
            return None

        by_panel: dict[str, tuple[float, bool]] = {}
        by_rtype: dict[str, tuple[float, bool]] = {}
        for row in rows:
            pct = float(row.get("sellable_limit_pct") or DEFAULT_THRESHOLD_PCT)
            pk = row.get("panel_key")
            rt = row.get("resource_type")
            is_specific = (row.get("dc_code", "*") or "*") != "*"
            for target, key in ((by_panel, pk), (by_rtype, rt)):
                if not key:
                    continue
                existing = target.get(key)
                if existing is None or (not existing[1] and is_specific):
                    target[key] = (pct, is_specific)  # type: ignore[index]

        return {
            "_by_panel_key":    {k: v[0] for k, v in by_panel.items()},
            "_by_resource_type": {k: v[0] for k, v in by_rtype.items()},
        }

    def _bulk_load_price_overrides(self) -> "dict[str, float] | None":
        """Load best price override per panel_key.  Returns None on failure.
        Panels with no override still go through get_unit_price_tl (catalog fallback).
        """
        if not self._webui.is_available:
            return None
        try:
            rows = self._webui.run_rows(sq.BULK_PRICE_OVERRIDES)
            if not isinstance(rows, list):
                return None
            return {
                row["panel_key"]: float(row["unit_price_tl"])
                for row in rows
                if row.get("panel_key") and row.get("unit_price_tl") is not None
            }
        except Exception:
            logger.debug("_bulk_load_price_overrides failed; will fall back to per-panel")
            return None

    @staticmethod
    def _lookup_conversion(
        unit_lookup: dict[tuple[str, str], UnitConversion],
        from_unit: str | None,
        to_unit: str | None,
    ) -> UnitConversion | None:
        """Resolve gui_unit_conversion row; match is exact first, then case-insensitive."""
        tu = (to_unit or "").strip()
        if not tu:
            return None
        fu = (from_unit or "").strip()
        if not fu:
            fu = tu
        key = (fu, tu)
        c = unit_lookup.get(key)
        if c is not None:
            return c
        flu, tlu = fu.lower(), tu.lower()
        for (a, b), conv in unit_lookup.items():
            if (a or "").strip().lower() == flu and (b or "").strip().lower() == tlu:
                return conv
        return None

    def get_threshold(self, panel_key: str, resource_kind: str, dc_code: str = "*") -> float:
        if not self._webui.is_available:
            return DEFAULT_THRESHOLD_PCT
        row = self._webui.run_one(
            sq.GET_THRESHOLD_FOR_PANEL,
            (panel_key, resource_kind, dc_code, panel_key),
        )
        if not row:
            return DEFAULT_THRESHOLD_PCT
        try:
            return float(row["sellable_limit_pct"])
        except (TypeError, ValueError):
            return DEFAULT_THRESHOLD_PCT

    def get_unit_price_tl(self, panel_key: str) -> tuple[float, bool]:
        """Return (unit_price_tl, has_price). Override first, otherwise the
        catalog TL price for the first mapped product in the panel.
        """
        if not self._webui.is_available:
            return 0.0, False
        try:
            row = self._webui.run_one(sq.GET_PRICE_OVERRIDE_FOR_PANEL, (panel_key,))
        except Exception:  # noqa: BLE001
            logger.exception("get_unit_price_tl override lookup failed (panel=%s)", panel_key)
            row = None
        if row and row.get("unit_price_tl") is not None:
            try:
                return float(row["unit_price_tl"]), True
            except (TypeError, ValueError):
                pass
        # Catalog fallback — pick any mapped productid for this panel.
        productid = self._first_productid_for_panel(panel_key)
        if not productid:
            return 0.0, False
        try:
            with self._svc._get_connection() as conn:
                with conn.cursor() as cur:
                    catalog = self._svc._run_row(cur, sq.CATALOG_TL_PRICE_FOR_PRODUCT, (productid,))
        except Exception:  # noqa: BLE001
            logger.exception("Catalog price lookup failed for product %s", productid)
            return 0.0, False
        if not catalog:
            return 0.0, False
        amount = float(catalog[0] or 0.0)
        currency = catalog[1] or "TL"
        tl = self._currency.to_tl(amount, currency)
        if tl is None:
            return 0.0, False
        return tl, True

    def _first_productid_for_panel(self, panel_key: str) -> str | None:
        if not self._webui.is_available:
            return None
        sql = (
            "SELECT COALESCE(o.productid, sm.productid) AS productid "
            "FROM gui_crm_service_pages sp "
            "JOIN gui_crm_service_mapping_seed sm ON sm.page_key = sp.page_key "
            "LEFT JOIN gui_crm_service_mapping_override o ON o.productid = sm.productid "
            "WHERE sp.panel_key = %s LIMIT 1;"
        )
        row = self._webui.run_one(sql, (panel_key,))
        return (row or {}).get("productid")

    # -- datalake queries

    @staticmethod
    def _bare_table_name(table: str | None) -> str:
        if not table:
            return ""
        t = table.strip()
        if "." in t:
            t = t.split(".")[-1]
        return t.lower()

    @classmethod
    def _sql_ident(cls, name: str | None) -> str:
        if not name or not _IDENTIFIER_RE.match(name):
            raise ValueError(f"invalid SQL identifier: {name!r}")
        return name

    def _sum_sql(
        self,
        *,
        column: str,
        physical_table: str,
        where_sql: str,
        params: list[Any],
    ) -> tuple[str, list[Any]]:
        """Build SELECT SUM(column) ... ; optional WebUI-latest subquery for VMware TS tables."""
        col = self._sql_ident(column)
        base = self._bare_table_name(physical_table)
        if base == "datacenter_metrics":
            sql = (
                f"SELECT COALESCE(SUM(_infra_dm.{col}), 0)::double precision "
                f"FROM {_SUBQUERY_DATACENTER_METRICS_LATEST} {where_sql};"
            )
            return sql, list(params)
        if base == "cluster_metrics":
            sql = (
                f"SELECT COALESCE(SUM(_infra_cm.{col}), 0)::double precision "
                f"FROM {_SUBQUERY_CLUSTER_METRICS_LATEST} {where_sql};"
            )
            return sql, list(params)
        if base == "nutanix_cluster_metrics":
            sql = (
                f"SELECT COALESCE(SUM(_infra_ncm.{col}), 0)::double precision "
                f"FROM {_SUBQUERY_NUTANIX_CLUSTER_LATEST} {where_sql};"
            )
            return sql, list(params)
        sql = (
            f"SELECT COALESCE(SUM({col}), 0)::double precision "
            f"FROM {physical_table}{where_sql};"
        )
        return sql, list(params)

    def _query_ibm_storage_string_totals(self, src: InfraSource, dc_code: str) -> tuple[float, float]:
        """Latest row per storage_ip on raw_ibm_storage_system; sum varchar capacities as GB."""
        if not src.source_table or not src.total_column or not src.allocated_column:
            return 0.0, 0.0
        try:
            tc = self._sql_ident(src.total_column)
            ac = self._sql_ident(src.allocated_column)
        except ValueError:
            return 0.0, 0.0
        tbl = src.source_table.strip()
        params: list[Any] = []
        if src.filter_clause:
            cleaned = src.filter_clause.replace(":dc_pattern", "%s")
            where_sql = f"WHERE ({cleaned})"
            params.append(self._dc_pattern(dc_code))
        else:
            where_sql = ""
        sql = f"""
WITH latest AS (
    SELECT DISTINCT ON (storage_ip)
        storage_ip,
        {tc} AS _tot,
        {ac} AS _used,
        "timestamp"
    FROM {tbl}
    {where_sql}
    ORDER BY storage_ip, "timestamp" DESC
)
SELECT _tot, _used FROM latest
"""
        try:
            with self._svc._get_connection() as conn:
                with conn.cursor() as cur:
                    rows = self._svc._run_rows(cur, sql, tuple(params)) or []
        except Exception:  # noqa: BLE001
            logger.exception(
                "SellableService: IBM storage aggregate failed (panel=%s, dc=%s)",
                src.panel_key,
                dc_code,
            )
            return 0.0, 0.0
        total_gb = sum(parse_storage_string_to_gb(r[0]) for r in rows if r)
        used_gb = sum(parse_storage_string_to_gb(r[1]) for r in rows if r)
        return total_gb, used_gb

    def _query_total_allocated(
        self,
        src: InfraSource,
        dc_code: str,
        *,
        preloaded_dc_payload: "dict | None" = None,
    ) -> tuple[float, float]:
        """Return (total_raw, allocated_raw) in the InfraSource declared units.

        Builds a parameterised SQL on the fly. ``filter_clause`` may reference
        ``:dc_pattern`` which is substituted with ``%s`` and bound to the DC
        glob pattern (``ankara%`` for an Ankara DC, ``%`` for ``*``).

        For ``datacenter_metrics`` and ``cluster_metrics``, SUM applies to the
        WebUI-aligned latest snapshot per (dc, datacenter) / (cluster, datacenter)
        — not a blind SUM over all history rows.
        """
        if not src.source_table or not src.total_column:
            return 0.0, 0.0
        if self._bare_table_name(src.source_table) == "raw_ibm_storage_system":
            return self._query_ibm_storage_string_totals(src, dc_code)
        params: list[Any] = []
        where_total = ""
        where_alloc = ""
        if src.filter_clause:
            cleaned = src.filter_clause.replace(":dc_pattern", "%s")
            where_total = f" WHERE {cleaned}"
            params.append(self._dc_pattern(dc_code))
        try:
            total_sql, total_params = self._sum_sql(
                column=src.total_column,
                physical_table=src.source_table,
                where_sql=where_total,
                params=params,
            )
        except ValueError:
            logger.exception(
                "SellableService: bad total_column for panel=%s",
                src.panel_key,
            )
            return 0.0, 0.0

        alloc_sql: str | None = None
        alloc_params: list[Any] = []
        alloc_table_bare = self._bare_table_name(src.allocated_table)
        alloc_from_redis = alloc_table_bare in _VM_TABLE_DC_SECTION

        if src.allocated_table and src.allocated_column and not alloc_from_redis:
            if src.filter_clause:
                cleaned = src.filter_clause.replace(":dc_pattern", "%s")
                where_alloc = f" WHERE {cleaned}"
                alloc_params.append(self._dc_pattern(dc_code))
            try:
                alloc_sql, alloc_params = self._sum_sql(
                    column=src.allocated_column,
                    physical_table=src.allocated_table,
                    where_sql=where_alloc,
                    params=alloc_params,
                )
            except ValueError:
                logger.exception(
                    "SellableService: bad allocated_column for panel=%s",
                    src.panel_key,
                )
                return 0.0, 0.0

        try:
            with self._svc._get_connection() as conn:
                with conn.cursor() as cur:
                    total_val = float(self._svc._run_value(cur, total_sql, tuple(total_params)) or 0.0)
        except Exception:  # noqa: BLE001
            logger.exception(
                "SellableService: datalake total lookup failed (panel=%s, dc=%s, table=%s)",
                src.panel_key, dc_code, src.source_table,
            )
            return 0.0, 0.0

        if alloc_from_redis and src.allocated_column:
            if preloaded_dc_payload is not None:
                alloc_val = self._extract_allocated_from_payload(preloaded_dc_payload, src, dc_code)
            else:
                alloc_val = self._fetch_allocated_from_redis(src, dc_code)
        elif alloc_sql is not None:
            try:
                with self._svc._get_connection() as conn:
                    with conn.cursor() as cur:
                        alloc_val = float(self._svc._run_value(cur, alloc_sql, tuple(alloc_params)) or 0.0)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "SellableService: datalake allocated lookup failed (panel=%s, dc=%s, table=%s)",
                    src.panel_key, dc_code, src.allocated_table,
                )
                return total_val, 0.0
        else:
            alloc_val = 0.0

        return total_val, alloc_val

    @staticmethod
    def _dc_pattern(dc_code: str) -> str:
        if not dc_code or dc_code == "*":
            return "%"
        return f"%{dc_code.lower()}%"

    def _dc_redis_key(self, dc_code: str) -> tuple[str, str]:
        """Return (redis_key, fallback_url) for the datacenter payload.

        Uses ``SELLABLE_REDIS_WINDOW_DAYS`` (default 7) so the keys match the
        ones populated by datacenter-api's default time range — without that
        alignment Redis returns miss on every sellable lookup.
        """
        today = datetime.date.today()
        days = max(_DC_DETAILS_WINDOW_DAYS, 1)
        start = (today - datetime.timedelta(days=days)).isoformat()
        end = today.isoformat()
        is_global = not dc_code or dc_code == "*"
        preset = f"{days}d"
        if is_global:
            return (
                f"global_dashboard:{start}:{end}",
                f"{self._dc_api_url}/api/v1/dashboard/overview?preset={preset}" if self._dc_api_url else "",
            )
        return (
            f"dc_details:{dc_code}:{start}:{end}",
            f"{self._dc_api_url}/api/v1/datacenters/{dc_code}?preset={preset}" if self._dc_api_url else "",
        )

    def _load_dc_redis_payload(self, dc_code: str) -> dict:
        """Fetch the full datacenter payload from Redis once (or via HTTP fallback).

        Called once per ``compute_all_panels`` invocation so that all panels
        sharing the same dc_code reuse the single JSON blob rather than issuing
        one Redis GET (or HTTP call) per panel.
        """
        redis_key, fallback_url = self._dc_redis_key(dc_code)

        raw: str | None = None
        if self._dc_redis is not None:
            try:
                raw = self._dc_redis.get(redis_key)
            except Exception:
                logger.exception("Redis GET failed for key=%s", redis_key)

        if raw:
            try:
                return json.loads(raw)
            except Exception:
                logger.warning("Redis key %s: JSON decode failed — falling back to HTTP", redis_key)

        if not fallback_url:
            logger.warning(
                "_load_dc_redis_payload: Redis miss and no datacenter_api_url (dc=%s key=%s)",
                dc_code, redis_key,
            )
            return {}
        try:
            resp = httpx.get(fallback_url, timeout=15.0)
            resp.raise_for_status()
            return resp.json() or {}
        except Exception:
            logger.exception("datacenter-api fallback failed dc=%s url=%s", dc_code, fallback_url)
            return {}

    @staticmethod
    def _extract_allocated_from_payload(payload: dict, src: "InfraSource", dc_code: str) -> float:
        """Pull the allocated value from a pre-loaded DC payload dict."""
        alloc_table = SellableService._bare_table_name(src.allocated_table)
        is_global = not dc_code or dc_code == "*"
        section_map = _VM_TABLE_GLOBAL_SECTION if is_global else _VM_TABLE_DC_SECTION
        section = section_map.get(alloc_table)
        redis_field = _VM_COLUMN_TO_REDIS_FIELD.get(src.allocated_column or "")
        if not section or not redis_field:
            return 0.0
        section_data = payload.get(section, {}) if isinstance(payload, dict) else {}
        val = section_data.get(redis_field)
        if val is None:
            return 0.0
        try:
            return float(val)
        except (TypeError, ValueError):
            return 0.0

    def _fetch_allocated_from_redis(self, src: InfraSource, dc_code: str) -> float:
        """Return the allocated value for vm_metrics / nutanix_vm_metrics panels
        by reading the datacenter-api Redis cache instead of querying the datalake DB.

        Calls ``_load_dc_redis_payload`` on every invocation (use the
        ``preloaded_dc_payload`` arg of ``_query_total_allocated`` inside
        ``compute_all_panels`` to avoid repeated fetches).
        """
        alloc_table = self._bare_table_name(src.allocated_table)
        section_map = (
            _VM_TABLE_GLOBAL_SECTION if (not dc_code or dc_code == "*")
            else _VM_TABLE_DC_SECTION
        )
        if not section_map.get(alloc_table) or not _VM_COLUMN_TO_REDIS_FIELD.get(src.allocated_column or ""):
            logger.warning(
                "_fetch_allocated_from_redis: no mapping for table=%r column=%r — returning 0",
                alloc_table, src.allocated_column,
            )
            return 0.0
        payload = self._load_dc_redis_payload(dc_code)
        return self._extract_allocated_from_payload(payload, src, dc_code)

    def _fetch_raw_compute_response(
        self, dc_code: str, family: str, clusters: list[str]
    ) -> "dict | None":
        """Fetch the raw /compute/{kind}?clusters=... JSON once per family.

        Called from ``compute_all_panels`` so the same response is shared by all
        resource_kind panels (cpu/ram/storage) of the same family — 3 HTTP calls
        → 1 HTTP call per family when clusters are provided.
        """
        kind = _FAMILY_COMPUTE_ENDPOINT.get(family)
        if not kind or not clusters or not dc_code or dc_code == "*" or not self._dc_api_url:
            return None
        csv = ",".join(c for c in clusters if c)
        url = f"{self._dc_api_url}/api/v1/datacenters/{dc_code}/compute/{kind}?clusters={csv}"
        try:
            resp = httpx.get(url, timeout=15.0)
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else None
        except Exception:
            logger.exception("compute raw fetch failed dc=%s family=%s url=%s", dc_code, family, url)
            return None

    @staticmethod
    def _extract_compute_metrics(
        raw: dict, resource_kind: str
    ) -> "tuple[float, float, str] | None":
        """Extract (cap, used, source_unit) from a pre-fetched compute response."""
        fields = _RESOURCE_KIND_TO_COMPUTE_FIELDS.get(resource_kind)
        if not fields or not isinstance(raw, dict):
            return None
        cap_field, used_field, source_unit = fields
        try:
            cap = float(raw.get(cap_field) or 0.0)
            used = float(raw.get(used_field) or 0.0)
        except (TypeError, ValueError):
            return None
        return cap, used, source_unit

    def _fetch_compute_metrics_for_clusters(
        self,
        *,
        dc_code: str,
        family: str,
        resource_kind: str,
        clusters: list[str],
    ) -> tuple[float, float, str] | None:
        """Read total_capacity + allocated for a virt panel from datacenter-api
        ``/compute/{kind}?clusters=…`` (the same source the DC view's
        Capacity Planning card uses).

        Returns ``(capacity, allocated, source_unit)`` or ``None`` if the
        family/resource_kind/dc combination cannot be served from the compute
        endpoint (caller should fall back to the legacy datalake + Redis path).
        """
        kind = _FAMILY_COMPUTE_ENDPOINT.get(family)
        fields = _RESOURCE_KIND_TO_COMPUTE_FIELDS.get(resource_kind)
        if not kind or not fields or not clusters:
            return None
        if not dc_code or dc_code == "*":
            # /compute is per-DC; cluster-aware path requires a concrete dc.
            return None
        if not self._dc_api_url:
            logger.warning(
                "_fetch_compute_metrics_for_clusters: datacenter_api_url not configured — "
                "skipping cluster-aware path for panel family=%s dc=%s",
                family, dc_code,
            )
            return None

        cap_field, used_field, source_unit = fields
        csv = ",".join(c for c in clusters if c)
        url = (
            f"{self._dc_api_url}/api/v1/datacenters/{dc_code}/compute/{kind}"
            f"?clusters={csv}"
        )
        try:
            resp = httpx.get(url, timeout=15.0)
            resp.raise_for_status()
            data = resp.json()
        except Exception:  # noqa: BLE001
            logger.exception(
                "datacenter-api compute fetch failed (dc=%s family=%s url=%s)",
                dc_code, family, url,
            )
            return None
        if not isinstance(data, dict):
            return None
        try:
            cap = float(data.get(cap_field) or 0.0)
            used = float(data.get(used_field) or 0.0)
        except (TypeError, ValueError):
            return None
        return cap, used, source_unit

    # ------------------------------------------------------------------ compute

    def _resolve_threshold(
        self,
        panel: PanelDefinition,
        dc_code: str,
        threshold_lookup: "dict | None",
    ) -> float:
        if threshold_lookup:
            by_pk = threshold_lookup.get("_by_panel_key", {})
            if panel.panel_key in by_pk:
                return float(by_pk[panel.panel_key])
            by_rt = threshold_lookup.get("_by_resource_type", {})
            if panel.resource_kind in by_rt:
                return float(by_rt[panel.resource_kind])
            return DEFAULT_THRESHOLD_PCT
        return self.get_threshold(panel.panel_key, panel.resource_kind, dc_code)

    def _resolve_unit_price_tl(
        self,
        panel_key: str,
        price_overrides: "dict[str, float] | None",
    ) -> tuple[float, bool]:
        """Resolve unit price using the bulk override map; falls back to
        the per-panel catalog lookup only when no override exists."""
        if price_overrides is not None:
            if panel_key in price_overrides:
                return float(price_overrides[panel_key]), True
            # No override → catalog fallback (one extra DB hit per panel without override)
            return self.get_unit_price_tl(panel_key)
        return self.get_unit_price_tl(panel_key)

    def compute_panel(
        self,
        panel: PanelDefinition,
        dc_code: str = "*",
        unit_lookup: dict[tuple[str, str], UnitConversion] | None = None,
        *,
        selected_clusters: list[str] | None = None,
        infra_lookup: "dict[str, InfraSource] | None" = None,
        threshold_lookup: "dict | None" = None,
        price_overrides: "dict[str, float] | None" = None,
        compute_response_cache: "dict[tuple, dict | None] | None" = None,
        dc_payload: "dict | None" = None,
    ) -> PanelResult:
        unit_lookup = unit_lookup if unit_lookup is not None else self._build_unit_lookup()
        if infra_lookup is not None:
            src = infra_lookup.get(panel.panel_key) or InfraSource(
                panel_key=panel.panel_key, dc_code=dc_code,
            )
        else:
            src = self.get_infra_source(panel.panel_key, dc_code) or InfraSource(
                panel_key=panel.panel_key, dc_code=dc_code,
            )
        threshold_pct = self._resolve_threshold(panel, dc_code, threshold_lookup)
        unit_price_tl, has_price = self._resolve_unit_price_tl(panel.panel_key, price_overrides)

        notes: list[str] = []
        has_infra = bool(src.source_table and src.total_column)

        # Cluster-aware path: when caller passed concrete clusters and the panel
        # family maps to a /compute endpoint, both cap and allocated come from
        # datacenter-api so the sellable card matches the DC view Capacity Planning
        # card exactly.
        compute_metrics = None
        if selected_clusters and panel.family in _FAMILY_COMPUTE_ENDPOINT:
            # Reuse a per-family raw response when compute_all_panels pre-fetched it.
            raw: dict | None = None
            if compute_response_cache is not None:
                key = (dc_code, panel.family, tuple(c for c in selected_clusters if c))
                if key in compute_response_cache:
                    raw = compute_response_cache[key]
                else:
                    raw = self._fetch_raw_compute_response(dc_code, panel.family, list(selected_clusters))
                    compute_response_cache[key] = raw
                if raw is not None:
                    compute_metrics = self._extract_compute_metrics(raw, panel.resource_kind)
            if compute_metrics is None and raw is None:
                compute_metrics = self._fetch_compute_metrics_for_clusters(
                    dc_code=dc_code,
                    family=panel.family,
                    resource_kind=panel.resource_kind,
                    clusters=selected_clusters,
                )

        if compute_metrics is not None:
            cap, used, source_unit = compute_metrics
            conv = self._lookup_conversion(unit_lookup, source_unit, panel.display_unit)
            du = (panel.display_unit or "").strip().lower()
            if conv is None and source_unit.strip().lower() != du:
                logger.warning(
                    "SellableService: no gui_unit_conversion %r -> %r for panel=%s "
                    "(cluster-aware path)",
                    source_unit, panel.display_unit, panel.panel_key,
                )
            total_disp = convert_unit(cap, conv)
            alloc_disp = convert_unit(used, conv)
            has_infra = True
            notes.append(
                f"cluster-scoped via datacenter-api/compute/{_FAMILY_COMPUTE_ENDPOINT[panel.family]} "
                f"({len(selected_clusters)} cluster)"
            )
        elif not has_infra:
            notes.append("infra-source missing — configure in Settings")
            total_disp = 0.0
            alloc_disp = 0.0
        else:
            # Forward the pre-loaded DC payload only when it actually contains
            # data so the legacy 2-arg signature stays backward-compatible
            # (an empty dict means "Redis cold AND HTTP fallback failed" — at
            # that point the per-panel path returns 0 anyway).
            if dc_payload:
                total_raw, alloc_raw = self._query_total_allocated(
                    src, dc_code, preloaded_dc_payload=dc_payload,
                )
            else:
                total_raw, alloc_raw = self._query_total_allocated(src, dc_code)
            total_from = src.total_unit or panel.display_unit
            alloc_from = src.allocated_unit or src.total_unit or panel.display_unit
            total_conv = self._lookup_conversion(unit_lookup, total_from, panel.display_unit)
            alloc_conv = self._lookup_conversion(unit_lookup, alloc_from, panel.display_unit)
            du = (panel.display_unit or "").strip().lower()
            if total_conv is None and (total_from or "").strip().lower() != du:
                logger.warning(
                    "SellableService: no gui_unit_conversion %r -> %r for panel=%s — "
                    "total stays in raw datalake units (sellable can be absurdly large vs UI capacity)",
                    total_from,
                    panel.display_unit,
                    panel.panel_key,
                )
            if alloc_conv is None and (alloc_from or "").strip().lower() != du:
                logger.warning(
                    "SellableService: no gui_unit_conversion %r -> %r for panel=%s (allocated side)",
                    alloc_from,
                    panel.display_unit,
                    panel.panel_key,
                )
            total_disp = convert_unit(total_raw, total_conv)
            alloc_disp = convert_unit(alloc_raw, alloc_conv)

        sellable_raw = apply_threshold(total_disp, alloc_disp, threshold_pct)

        # constrained will be filled in by the family-pass below; default = raw.
        return PanelResult(
            panel_key=panel.panel_key,
            label=panel.label,
            family=panel.family,
            resource_kind=panel.resource_kind,
            display_unit=panel.display_unit,
            dc_code=dc_code,
            total=total_disp,
            allocated=alloc_disp,
            threshold_pct=threshold_pct,
            sellable_raw=sellable_raw,
            sellable_constrained=sellable_raw,
            unit_price_tl=unit_price_tl,
            potential_tl=compute_potential_tl(sellable_raw, unit_price_tl),
            ratio_bound=False,
            has_infra_source=has_infra,
            has_price=has_price,
            notes=notes,
        )

    # -- result cache (crm-engine Redis DB 2) -----------------------------------

    @staticmethod
    def _result_cache_key(
        dc_code: str,
        selected_clusters: list[str] | None,
        family: str | None,
    ) -> str:
        clusters_part = ""
        if selected_clusters:
            clusters_part = ",".join(sorted(c for c in selected_clusters if c))
        return f"sellable:panels:{dc_code or '*'}:{family or '*'}:{clusters_part}"

    def _result_cache_get(self, key: str) -> "list[PanelResult] | None":
        if self._crm_redis is None or _SELLABLE_CACHE_TTL <= 0:
            return None
        try:
            raw = self._crm_redis.get(key)
        except Exception:
            logger.exception("crm Redis GET failed key=%s", key)
            return None
        if not raw:
            return None
        try:
            payload = json.loads(raw)
            return [self._panel_result_from_dict(d) for d in payload]
        except Exception:
            logger.warning("Sellable cache key=%s decode failed — ignoring", key)
            return None

    def _result_cache_set(self, key: str, results: "list[PanelResult]") -> None:
        if self._crm_redis is None or _SELLABLE_CACHE_TTL <= 0:
            return
        try:
            payload = json.dumps([r.to_dict() for r in results])
            self._crm_redis.setex(key, _SELLABLE_CACHE_TTL, payload)
        except Exception:
            logger.exception("crm Redis SETEX failed key=%s", key)

    def invalidate_result_cache(self, dc_code: str | None = None) -> int:
        """Drop cached compute_all_panels payloads.

        Called by ``snapshot_all`` so the next request after a scheduler tick
        re-reads fresh metrics.  Returns the number of keys deleted.
        """
        if self._crm_redis is None:
            return 0
        pattern = (
            f"sellable:panels:{dc_code}:*" if dc_code and dc_code != "*"
            else "sellable:panels:*"
        )
        deleted = 0
        try:
            for k in self._crm_redis.scan_iter(match=pattern, count=200):
                try:
                    deleted += int(self._crm_redis.delete(k) or 0)
                except Exception:
                    pass
        except Exception:
            logger.exception("invalidate_result_cache scan failed pattern=%s", pattern)
        if deleted:
            logger.info("Sellable cache: deleted %d key(s) matching %s", deleted, pattern)
        return deleted

    @staticmethod
    def _panel_result_from_dict(d: dict) -> PanelResult:
        """Rebuild a PanelResult from its to_dict() output."""
        return PanelResult(
            panel_key=d.get("panel_key", ""),
            label=d.get("label", ""),
            family=d.get("family", ""),
            resource_kind=d.get("resource_kind", "other"),
            display_unit=d.get("display_unit", ""),
            dc_code=d.get("dc_code", "*"),
            total=float(d.get("total", 0.0) or 0.0),
            allocated=float(d.get("allocated", 0.0) or 0.0),
            threshold_pct=float(d.get("threshold_pct", DEFAULT_THRESHOLD_PCT) or DEFAULT_THRESHOLD_PCT),
            sellable_raw=float(d.get("sellable_raw", 0.0) or 0.0),
            sellable_constrained=float(d.get("sellable_constrained", 0.0) or 0.0),
            unit_price_tl=float(d.get("unit_price_tl", 0.0) or 0.0),
            potential_tl=float(d.get("potential_tl", 0.0) or 0.0),
            ratio_bound=bool(d.get("ratio_bound", False)),
            has_infra_source=bool(d.get("has_infra_source", False)),
            has_price=bool(d.get("has_price", False)),
            notes=list(d.get("notes") or []),
        )

    def compute_all_panels(
        self,
        dc_code: str = "*",
        *,
        selected_clusters: list[str] | None = None,
        family: str | None = None,
    ) -> list[PanelResult]:
        # 1. Result cache lookup — short-circuits the entire compute pipeline.
        cache_key = self._result_cache_key(dc_code, selected_clusters, family)
        cached = self._result_cache_get(cache_key)
        if cached is not None:
            return cached

        # 2. Pull panel definitions; filter by family BEFORE any heavy lookup.
        defs = self.list_panel_defs()
        if family:
            defs = [d for d in defs if d.family == family]
        if not defs:
            self._result_cache_set(cache_key, [])
            return []

        # 3. Bulk-load WebUI metadata in 3 queries instead of N×3 round-trips.
        unit_lookup = self._build_unit_lookup()
        infra_lookup = self._bulk_load_infra_sources(dc_code)
        threshold_lookup = self._bulk_load_thresholds(dc_code)
        price_overrides = self._bulk_load_price_overrides()

        # 4. Pre-fetch the DC Redis payload once; every Redis-backed allocated
        #    panel reuses the same JSON instead of issuing one GET per panel.
        needs_dc_payload = any(
            self._bare_table_name(
                (infra_lookup or {}).get(d.panel_key, InfraSource(panel_key=d.panel_key)).allocated_table
            ) in _VM_TABLE_DC_SECTION
            for d in defs
        )
        dc_payload = self._load_dc_redis_payload(dc_code) if needs_dc_payload else None

        # 5. Per-family /compute response cache — 3 cpu/ram/storage panels of
        #    the same family share a single HTTP call when clusters are set.
        compute_response_cache: dict[tuple, dict | None] = {}

        results = [
            self.compute_panel(
                d,
                dc_code=dc_code,
                unit_lookup=unit_lookup,
                selected_clusters=selected_clusters,
                infra_lookup=infra_lookup,
                threshold_lookup=threshold_lookup,
                price_overrides=price_overrides,
                compute_response_cache=compute_response_cache,
                dc_payload=dc_payload,
            )
            for d in defs
        ]

        # 6. Apply ratio per family.
        by_family: dict[str, list[PanelResult]] = defaultdict(list)
        for r in results:
            by_family[r.family].append(r)
        ratio_lookup = {(r.family, r.dc_code): r for r in self.list_ratios()}

        constrained: list[PanelResult] = []
        for fam, group in by_family.items():
            ratio = ratio_lookup.get((fam, dc_code)) or ratio_lookup.get((fam, "*")) or ResourceRatio(family=fam)
            new_group = constrain_by_ratio(group, ratio)
            for new in new_group:
                new.potential_tl = compute_potential_tl(new.sellable_constrained, new.unit_price_tl)
                constrained.append(new)
        constrained.sort(key=lambda p: (p.family, p.resource_kind, p.panel_key))

        self._result_cache_set(cache_key, constrained)
        return constrained

    def compute_summary(
        self,
        dc_code: str = "*",
        *,
        selected_clusters: list[str] | None = None,
        family: str | None = None,
    ) -> DashboardSummary:
        panels = self.compute_all_panels(
            dc_code=dc_code,
            selected_clusters=selected_clusters,
            family=family,
        )

        by_family: dict[str, list[PanelResult]] = defaultdict(list)
        for p in panels:
            by_family[p.family].append(p)

        family_aggs: list[FamilyAggregate] = []
        total_potential = 0.0
        constrained_loss = 0.0
        for family, group in by_family.items():
            label_lookup = group[0].label.split(" — ")[0] if group else family
            agg = FamilyAggregate(family=family, label=label_lookup, dc_code=dc_code, panels=group)
            family_potential = sum(p.potential_tl for p in group)
            family_raw_potential = sum(compute_potential_tl(p.sellable_raw, p.unit_price_tl) for p in group)
            agg.total_potential_tl = family_potential
            agg.constrained_loss_tl = max(family_raw_potential - family_potential, 0.0)
            agg.total_sellable_constrained_units = {
                p.resource_kind: agg.total_sellable_constrained_units.get(p.resource_kind, 0.0) + p.sellable_constrained
                for p in group
            }
            family_aggs.append(agg)
            total_potential += family_potential
            constrained_loss += agg.constrained_loss_tl

        family_aggs.sort(key=lambda a: -a.total_potential_tl)
        ytd_sales_tl = self._compute_ytd_sales_tl()
        unmapped_count = self._count_unmapped_products()
        return DashboardSummary(
            dc_code=dc_code,
            total_potential_tl=total_potential,
            constrained_loss_tl=constrained_loss,
            ytd_sales_tl=ytd_sales_tl,
            unmapped_product_count=unmapped_count,
            families=family_aggs,
        )

    def _compute_ytd_sales_tl(self) -> float:
        try:
            with self._svc._get_connection() as conn:
                with conn.cursor() as cur:
                    rows = self._svc._run_rows(cur, sq.YTD_REALIZED_SALES)
        except Exception:  # noqa: BLE001
            logger.exception("YTD realized sales lookup failed")
            return 0.0
        total_tl = 0.0
        for r in rows or []:
            ccy, amount = r[0], r[1]
            tl = self._currency.to_tl(amount, ccy)
            if tl is not None:
                total_tl += tl
        return total_tl

    def _count_unmapped_products(self) -> int:
        try:
            with self._svc._get_connection() as conn:
                with conn.cursor() as cur:
                    val = self._svc._run_value(cur, sq.UNMAPPED_PRODUCT_COUNT)
        except Exception:  # noqa: BLE001
            logger.exception("Unmapped product count failed")
            return 0
        return int(val or 0)

    # ------------------------------------------------------------------ snapshot

    def snapshot_all(self) -> int:
        """Compute the global dashboard, push every metric into TaggingService
        cache + persist a snapshot row. Returns the number of metrics emitted.

        Also invalidates the compute_all_panels result cache so the next user
        request after the scheduler tick picks up fresh values.
        """
        # Drop stale cache before re-computing so the scheduler-driven write
        # repopulates fresh keys (and any concurrent user request also misses).
        self.invalidate_result_cache()
        try:
            summary = self.compute_summary("*")
        except Exception:  # noqa: BLE001
            logger.exception("snapshot_all: compute_summary failed")
            return 0
        metrics: list[MetricValue] = []
        for fam in summary.families:
            for panel in fam.panels:
                for measure, value, unit in TaggingService.measures_from_panel(panel):
                    metric_key = build_metric_key(panel.family, panel.resource_kind, measure)
                    mv = MetricValue(
                        metric_key=metric_key,
                        value=float(value),
                        unit=unit,
                        scope_type="global",
                        scope_id="*",
                    )
                    metrics.append(mv)
                    self._tags.set(mv)
        # Top-level dashboard metrics
        top = [
            MetricValue("crm.sellable_potential.total_tl",       summary.total_potential_tl,    "TL"),
            MetricValue("crm.sellable_potential.constrained_loss_tl", summary.constrained_loss_tl, "TL"),
            MetricValue("crm.sellable_potential.ytd_sales_tl",   summary.ytd_sales_tl,          "TL"),
            MetricValue("crm.sellable_potential.unmapped_count", float(summary.unmapped_product_count), "Adet"),
        ]
        for mv in top:
            metrics.append(mv)
            self._tags.set(mv)
        written = self._tags.snapshot(metrics)
        logger.info(
            "SellableService.snapshot_all: emitted=%d, written=%d, total_tl=%.2f",
            len(metrics), written, summary.total_potential_tl,
        )
        return len(metrics)

    # ------------------------------------------------------------------ tags API

    def get_metric_dict(
        self,
        prefix: str | None = None,
        scope_type: str = "global",
        scope_id: str = "*",
    ) -> dict[str, MetricValue]:
        return self._tags.all_with_prefix(prefix=prefix, scope_type=scope_type, scope_id=scope_id)

    def list_metric_snapshots(self, metric_key: str, scope_id: str = "*", hours: int = 720) -> list[dict[str, Any]]:
        if not self._webui.is_available:
            return []
        rows = self._webui.run_rows(sq.LIST_METRIC_SNAPSHOTS, (metric_key, scope_id, str(int(hours))))
        return rows
