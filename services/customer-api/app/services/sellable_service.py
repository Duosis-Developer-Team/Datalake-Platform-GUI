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
# ruff: noqa: E402

import datetime
import json
import logging
import os
import re
from collections import defaultdict
from typing import TYPE_CHECKING, Any

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
# Timeout for datacenter-api DC list fetch during snapshot prewarm.
_SELLABLE_DC_CODES_TIMEOUT: float = float(os.getenv("SELLABLE_DC_CODES_TIMEOUT", "30"))

# TTL (seconds) for compute_all_panels result in crm-engine Redis (DB 2).
# 0 disables caching. Override with SELLABLE_CACHE_TTL_SECONDS.
_SELLABLE_CACHE_TTL: int = int(os.getenv("SELLABLE_CACHE_TTL_SECONDS", "3600"))

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
    # vm_metrics — classic KM VMware (allocated = sales GHz: 1 vCPU = 1 GHz)
    "number_of_cpus":          "cpu_alloc_ghz_sales",
    "total_memory_capacity_gb": "mem_alloc_gb_vm",
    "provisioned_space_gb":    "stor_provisioned_gb",
    # nutanix_vm_metrics — hyperconverged Nutanix (sales ≈ real for Nutanix vCPU)
    "cpu_count":               "cpu_alloc_ghz_sales",
    "memory_capacity":         "mem_alloc_gb_vm",
    "disk_capacity":           "stor_provisioned_gb",
}

# Maps (bare_source_table, total_column) → (dc_details section, redis field).
# datacenter-api writes these into dc_details / global_dashboard Redis keys.
_TOTAL_COLUMN_TO_REDIS: dict[tuple[str, str], tuple[str, str]] = {
    ("cluster_metrics", "cpu_ghz_capacity"): ("classic", "cpu_cap"),
    ("cluster_metrics", "memory_capacity_gb"): ("classic", "mem_cap"),
    ("cluster_metrics", "total_capacity_gb"): ("classic", "stor_cap"),
    ("datacenter_metrics", "total_cpu_ghz_capacity"): ("classic", "cpu_cap"),
    ("datacenter_metrics", "total_memory_capacity_gb"): ("classic", "mem_cap"),
    ("datacenter_metrics", "total_storage_capacity_gb"): ("classic", "stor_cap"),
    ("nutanix_cluster_metrics", "total_cpu_capacity"): ("hyperconv", "cpu_cap"),
    ("nutanix_cluster_metrics", "total_memory_capacity"): ("hyperconv", "mem_cap"),
    ("nutanix_cluster_metrics", "storage_capacity"): ("hyperconv", "stor_cap"),
    ("ibm_server_general", "server_processor_totalprocunits"): ("power", "cpu_total_procunits"),
    ("ibm_server_general", "server_memory_totalmem"): ("power", "memory_total"),
}

# IBM LPAR allocated totals live in the same power section (not vm_metrics Redis path).
_ALLOCATED_COLUMN_TO_REDIS: dict[tuple[str, str], tuple[str, str]] = {
    ("ibm_lpar_general", "lpar_processor_entitledprocunits"): ("power", "cpu_assigned"),
    ("ibm_lpar_general", "lpar_memory_logicalmem"): ("power", "memory_assigned"),
}

# global_dashboard ibm_totals uses shorter field names than dc_details power section.
_POWER_GLOBAL_FIELD_ALIASES: dict[str, str] = {
    "memory_total": "mem_total",
    "memory_assigned": "mem_assigned",
    "memory_available": "mem_available",
}

# Unit carried by datacenter-api Redis payload fields. These are normalized
# dashboard units, not necessarily the original datalake column units configured
# in gui_panel_infra_source.
_REDIS_FIELD_UNITS: dict[tuple[str, str], str] = {
    ("classic", "cpu_cap"): "GHz",
    ("classic", "cpu_used"): "GHz",
    ("classic", "mem_cap"): "GB",
    ("classic", "mem_used"): "GB",
    ("classic", "stor_cap"): "TB",
    ("classic", "stor_used"): "TB",
    ("hyperconv", "cpu_cap"): "GHz",
    ("hyperconv", "cpu_used"): "GHz",
    ("hyperconv", "mem_cap"): "GB",
    ("hyperconv", "mem_used"): "GB",
    ("hyperconv", "stor_cap"): "TB",
    ("hyperconv", "stor_used"): "TB",
    ("power", "cpu_total_procunits"): "procunit",
    ("power", "cpu_assigned"): "procunit",
    ("power", "cpu_used"): "procunit",
    ("power", "cpu_available_procunits"): "procunit",
    ("power", "memory_total"): "GB",
    ("power", "memory_assigned"): "GB",
    ("power", "memory_available"): "GB",
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

# Families whose CPU/RAM sellable is computed host-by-host (ADR: host-based
# CRM calculation). Each host is evaluated on its own min(CPU, RAM) ratio
# constraint and the family unit count is the sum across hosts. Storage is
# excluded from the per-host min() and handled by the architecture-aware
# storage range model below.
_HOST_BASED_FAMILIES: frozenset[str] = frozenset({"virt_classic", "virt_hyperconverged"})

# Families whose storage panel carries a [min, max] sellable range because
# IBM storage free space is shared between KM datastores and native Power.
_STORAGE_RANGE_FAMILIES: frozenset[str] = frozenset({"virt_classic", "virt_power"})

# gui_crm_calc_config keys for dual CPU sellable tracks.
_CALC_EFFECTIVE_GHZ_KEY = "sellable.cpu.effective_ghz_per_unit"
_CALC_PHYSICAL_PRICE_UNIT_KEY = "sellable.cpu.physical_price_unit"
_CALC_POWER_CORE_GHZ_KEY = "power.core_to_ghz_factor"

# Maps resource_kind → (capacity_field, used_field, source_unit) in the compute response.
_RESOURCE_KIND_TO_COMPUTE_FIELDS: dict[str, tuple[str, str, str]] = {
    "cpu":     ("cpu_cap",  "cpu_alloc_ghz_sales",  "GHz"),
    "ram":     ("mem_cap",  "mem_alloc_gb_vm",  "GB"),
    "storage": ("stor_cap", "stor_provisioned_gb", "TB"),
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
    compute_storage_range,
    constrain_by_ratio,
    constrain_by_ratio_dual_cpu_cluster,
    constrain_by_ratio_per_host,
    constrain_by_ratio_per_host_dual,
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
            manual_total=(
                float(row["manual_total"]) if row.get("manual_total") is not None else None
            ),
            manual_allocated=(
                float(row["manual_allocated"]) if row.get("manual_allocated") is not None else None
            ),
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
                    manual_total=(
                        float(row["manual_total"]) if row.get("manual_total") is not None else None
                    ),
                    manual_allocated=(
                        float(row["manual_allocated"])
                        if row.get("manual_allocated") is not None
                        else None
                    ),
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

    @staticmethod
    def _escape_filter_clause(filter_clause: str) -> str:
        """Escape literal % for psycopg2, then bind :dc_pattern."""
        return filter_clause.replace("%", "%%").replace(":dc_pattern", "%s")

    @staticmethod
    def _infra_uses_dc_redis_payload(src: InfraSource) -> bool:
        """True when total or allocated can be read from datacenter-api Redis cache."""
        total_key = (
            SellableService._bare_table_name(src.source_table),
            (src.total_column or "").strip(),
        )
        if total_key in _TOTAL_COLUMN_TO_REDIS:
            return True
        alloc_key = (
            SellableService._bare_table_name(src.allocated_table),
            (src.allocated_column or "").strip(),
        )
        if alloc_key in _ALLOCATED_COLUMN_TO_REDIS:
            return True
        return SellableService._bare_table_name(src.allocated_table) in _VM_TABLE_DC_SECTION

    @staticmethod
    def _redis_section_data(
        payload: dict,
        dc_code: str,
        section_key: str,
    ) -> dict:
        """Return the JSON object for classic/hyperconv/power (per-DC or global totals)."""
        if not isinstance(payload, dict):
            return {}
        is_global = not dc_code or dc_code == "*"
        if is_global:
            if section_key == "classic":
                return payload.get("classic_totals") or {}
            if section_key == "hyperconv":
                return payload.get("hyperconv_totals") or {}
            if section_key == "power":
                return payload.get("ibm_totals") or {}
            return {}
        return payload.get(section_key) or {}

    @classmethod
    def _extract_mapped_field_from_payload(
        cls,
        payload: dict,
        dc_code: str,
        section_key: str,
        field: str,
        target_unit: str | None = None,
    ) -> float | None:
        is_global = not dc_code or dc_code == "*"
        lookup_field = field
        if is_global and section_key == "power":
            lookup_field = _POWER_GLOBAL_FIELD_ALIASES.get(field, field)
        section_data = cls._redis_section_data(payload, dc_code, section_key)
        val = section_data.get(lookup_field)
        if val is None:
            return None
        try:
            numeric = float(val)
        except (TypeError, ValueError):
            return None
        return cls._convert_redis_field_unit(numeric, section_key, field, target_unit)

    @staticmethod
    def _convert_redis_field_unit(
        value: float,
        section_key: str,
        field: str,
        target_unit: str | None,
    ) -> float:
        """Convert normalized datacenter-api Redis field units to infra config units."""
        if not target_unit:
            return value
        source_unit = _REDIS_FIELD_UNITS.get((section_key, field))
        if not source_unit or source_unit == target_unit:
            return value
        pair = (source_unit.lower(), target_unit.lower())
        if pair == ("tb", "gb"):
            return value * 1024.0
        if pair == ("gb", "tb"):
            return value / 1024.0
        if pair == ("ghz", "hz"):
            return value * 1_000_000_000.0
        if pair == ("hz", "ghz"):
            return value / 1_000_000_000.0
        if pair == ("gb", "bytes"):
            return value * 1_073_741_824.0
        if pair == ("bytes", "gb"):
            return value / 1_073_741_824.0
        if pair == ("tb", "bytes"):
            return value * 1_099_511_627_776.0
        if pair == ("bytes", "tb"):
            return value / 1_099_511_627_776.0
        if pair == ("gb", "mb"):
            return value * 1024.0
        if pair == ("mb", "gb"):
            return value / 1024.0
        logger.debug(
            "SellableService: no Redis unit conversion source=%s target=%s section=%s field=%s",
            source_unit,
            target_unit,
            section_key,
            field,
        )
        return value

    @classmethod
    def _extract_total_from_payload(
        cls,
        payload: dict,
        source_table: str,
        total_column: str,
        dc_code: str,
        total_unit: str | None = None,
    ) -> float | None:
        """Return total capacity from dc_details / global_dashboard payload; None on miss."""
        key = (cls._bare_table_name(source_table), total_column)
        mapping = _TOTAL_COLUMN_TO_REDIS.get(key)
        if not mapping:
            return None
        section_key, field = mapping
        return cls._extract_mapped_field_from_payload(payload, dc_code, section_key, field, total_unit)

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
        if base == "ibm_server_general":
            pattern = params[0] if params else "%"
            sql = f"""
SELECT COALESCE(SUM(latest.{col}), 0)::double precision
FROM (
    SELECT DISTINCT ON (server_details_servername)
        {col}
    FROM public.ibm_server_general
    WHERE server_details_servername ILIKE %s
    ORDER BY server_details_servername, time DESC
) latest;
"""
            return sql, [pattern]
        if base == "ibm_lpar_general":
            pattern = params[0] if params else "%"
            sql = f"""
SELECT COALESCE(SUM(latest.{col}), 0)::double precision
FROM (
    SELECT DISTINCT ON (lparname)
        {col}
    FROM public.ibm_lpar_general
    WHERE lpar_details_servername ILIKE %s
    ORDER BY lparname, time DESC
) latest;
"""
            return sql, [pattern]
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
            cleaned = self._escape_filter_clause(src.filter_clause)
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
        if src.manual_total is not None:
            return float(src.manual_total or 0.0), float(src.manual_allocated or 0.0)
        if self._bare_table_name(src.source_table) == "raw_ibm_storage_system":
            return self._query_ibm_storage_string_totals(src, dc_code)

        payload = preloaded_dc_payload
        if payload is None and self._infra_uses_dc_redis_payload(src):
            loaded = self._load_dc_redis_payload(dc_code)
            if loaded:
                payload = loaded

        if payload:
            total_from_redis = self._extract_total_from_payload(
                payload,
                src.source_table or "",
                src.total_column or "",
                dc_code,
                src.total_unit,
            )
            if total_from_redis is not None:
                alloc_val = self._resolve_allocated_for_panel(src, dc_code, payload)
                return total_from_redis, alloc_val
            if self._infra_uses_dc_redis_payload(src):
                logger.debug(
                    "SellableService: Redis total miss panel=%s dc=%s table=%s column=%s — datalake fallback",
                    src.panel_key,
                    dc_code,
                    src.source_table,
                    src.total_column,
                )

        params: list[Any] = []
        where_total = ""
        where_alloc = ""
        total_table_bare = self._bare_table_name(src.source_table)
        if total_table_bare in ("ibm_server_general", "ibm_lpar_general"):
            params = [self._dc_pattern(dc_code)]
        elif src.filter_clause:
            cleaned = self._escape_filter_clause(src.filter_clause)
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
            if alloc_table_bare in ("ibm_server_general", "ibm_lpar_general"):
                alloc_params = [self._dc_pattern(dc_code)]
            elif src.filter_clause:
                cleaned = self._escape_filter_clause(src.filter_clause)
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
            if payload is not None:
                alloc_val = self._extract_allocated_from_payload(payload, src, dc_code)
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

    def _resolve_allocated_for_panel(
        self,
        src: InfraSource,
        dc_code: str,
        payload: dict,
    ) -> float:
        """Resolve allocated_raw from Redis payload when total came from cache."""
        alloc_table_bare = self._bare_table_name(src.allocated_table)
        if alloc_table_bare in _VM_TABLE_DC_SECTION and src.allocated_column:
            return self._extract_allocated_from_payload(payload, src, dc_code)
        alloc_key = (alloc_table_bare, (src.allocated_column or "").strip())
        if alloc_key in _ALLOCATED_COLUMN_TO_REDIS:
            section_key, field = _ALLOCATED_COLUMN_TO_REDIS[alloc_key]
            val = self._extract_mapped_field_from_payload(
                payload, dc_code, section_key, field, src.allocated_unit,
            )
            return float(val or 0.0)
        return 0.0

    @staticmethod
    def _dc_pattern(dc_code: str) -> str:
        if not dc_code or dc_code == "*":
            return "%"
        return f"%{dc_code.lower()}%"

    @staticmethod
    def _utc_today() -> datetime.date:
        """UTC calendar date — must match datacenter-api ``_today_utc()`` for Redis keys."""
        return datetime.datetime.now(datetime.timezone.utc).date()

    @staticmethod
    def _payload_section_hints(payload: dict) -> str:
        """Compact summary of which dc_details / global_dashboard sections are present."""
        if not isinstance(payload, dict) or not payload:
            return "none"
        hints: list[str] = []
        for section in (
            "classic",
            "hyperconv",
            "power",
            "classic_totals",
            "hyperconv_totals",
            "ibm_totals",
            "intel",
        ):
            block = payload.get(section)
            if isinstance(block, dict) and block:
                hints.append(section)
        return ",".join(hints) if hints else "empty"

    def _dc_redis_keys_for_span(self, dc_code: str, span_days: int) -> tuple[str, str]:
        """Return (redis_key, fallback_url) for an inclusive UTC calendar span.

        datacenter-api 7d preset uses ``start = today - (span_days - 1)`` (7 days inclusive).
        """
        today = self._utc_today()
        span = max(span_days, 1)
        start = (today - datetime.timedelta(days=span - 1)).isoformat()
        end = today.isoformat()
        is_global = not dc_code or dc_code == "*"
        preset = f"{max(_DC_DETAILS_WINDOW_DAYS, 1)}d"
        if is_global:
            return (
                f"global_dashboard:{start}:{end}",
                f"{self._dc_api_url}/api/v1/dashboard/overview?preset={preset}"
                if self._dc_api_url
                else "",
            )
        return (
            f"dc_details:{dc_code}:{start}:{end}",
            f"{self._dc_api_url}/api/v1/datacenters/{dc_code}?preset={preset}"
            if self._dc_api_url
            else "",
        )

    def _dc_redis_key(self, dc_code: str) -> tuple[str, str]:
        """Primary Redis key aligned with datacenter-api default 7d window (UTC, inclusive)."""
        days = max(_DC_DETAILS_WINDOW_DAYS, 1)
        return self._dc_redis_keys_for_span(dc_code, days)

    def _dc_redis_key_alternates(self, dc_code: str) -> list[str]:
        """Extra Redis keys (legacy off-by-one span, neighbors) before HTTP fallback."""
        days = max(_DC_DETAILS_WINDOW_DAYS, 1)
        primary, _ = self._dc_redis_key(dc_code)
        out: list[str] = []
        for span in (days + 1, days - 1):
            if span < 1:
                continue
            key, _ = self._dc_redis_keys_for_span(dc_code, span)
            if key != primary and key not in out:
                out.append(key)
        return out

    def _redis_get_json(self, redis_key: str) -> dict | None:
        if self._dc_redis is None:
            return None
        try:
            raw = self._dc_redis.get(redis_key)
        except Exception:
            logger.exception("Redis GET failed for key=%s", redis_key)
            return None
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            logger.warning("Redis key %s: JSON decode failed", redis_key)
            return None

    def _load_dc_redis_payload(self, dc_code: str) -> dict:
        """Fetch the full datacenter payload from Redis once (or via HTTP fallback).

        Called once per ``compute_all_panels`` invocation so that all panels
        sharing the same dc_code reuse the single JSON blob rather than issuing
        one Redis GET (or HTTP call) per panel.
        """
        redis_key, fallback_url = self._dc_redis_key(dc_code)
        keys_to_try = [redis_key, *self._dc_redis_key_alternates(dc_code)]

        for key in keys_to_try:
            payload = self._redis_get_json(key)
            if payload is not None:
                logger.info(
                    "_load_dc_redis_payload: dc=%s key=%s redis_hit=True sections=%s",
                    dc_code,
                    key,
                    self._payload_section_hints(payload),
                )
                return payload

        logger.info(
            "_load_dc_redis_payload: dc=%s key=%s redis_hit=False sections=none",
            dc_code,
            redis_key,
        )
        if not fallback_url:
            logger.warning(
                "_load_dc_redis_payload: Redis miss and no datacenter_api_url (dc=%s key=%s)",
                dc_code,
                redis_key,
            )
            return {}
        try:
            resp = httpx.get(fallback_url, timeout=15.0)
            resp.raise_for_status()
            payload = resp.json() or {}
            logger.info(
                "_load_dc_redis_payload: dc=%s http_fallback=True sections=%s",
                dc_code,
                self._payload_section_hints(payload if isinstance(payload, dict) else {}),
            )
            return payload if isinstance(payload, dict) else {}
        except Exception:
            logger.warning(
                "_load_dc_redis_payload: datacenter-api fallback failed dc=%s url=%s",
                dc_code,
                fallback_url,
            )
            return {}

    @classmethod
    def _extract_allocated_from_payload(
        cls, payload: dict, src: "InfraSource", dc_code: str,
    ) -> float:
        """Pull the allocated value from a pre-loaded DC payload dict."""
        alloc_table = cls._bare_table_name(src.allocated_table)
        alloc_key = (alloc_table, (src.allocated_column or "").strip())
        if alloc_key in _ALLOCATED_COLUMN_TO_REDIS:
            section_key, field = _ALLOCATED_COLUMN_TO_REDIS[alloc_key]
            val = cls._extract_mapped_field_from_payload(
                payload, dc_code, section_key, field, src.allocated_unit,
            )
            return float(val or 0.0)
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
            numeric = float(val)
        except (TypeError, ValueError):
            return 0.0
        return cls._convert_redis_field_unit(
            numeric,
            "classic" if section in ("classic", "classic_totals") else "hyperconv",
            redis_field,
            src.allocated_unit,
        )

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
            if resource_kind == "storage" and used_field == "stor_provisioned_gb":
                used = used / 1024.0
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
        return self._extract_compute_metrics(data, resource_kind)

    # ----------------------------------------------- host-based sellable path

    def _fetch_host_rows(
        self,
        dc_code: str,
        family: str,
        clusters: list[str] | None,
        *,
        preset: str = "30d",
    ) -> tuple[list[dict] | None, str]:
        """Fetch per-host compute rows from datacenter-api /compute/{kind}/hosts.

        Returns ``(hosts, status)`` where status is ``ok`` | ``empty`` | ``unavailable``.
        """
        kind = _FAMILY_COMPUTE_ENDPOINT.get(family)
        if not kind or not dc_code or dc_code == "*" or not self._dc_api_url:
            return None, "unavailable"
        params: list[str] = [f"preset={preset}"]
        cl = [c for c in (clusters or []) if c]
        if cl:
            params.append(f"clusters={','.join(cl)}")
        url = (
            f"{self._dc_api_url}/api/v1/datacenters/{dc_code}/compute/{kind}/hosts"
            f"?{'&'.join(params)}"
        )
        try:
            resp = httpx.get(url, timeout=15.0)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            logger.warning("host rows fetch failed dc=%s family=%s url=%s", dc_code, family, url)
            return None, "unavailable"
        if not isinstance(data, dict):
            return None, "unavailable"
        hosts = data.get("hosts")
        if not isinstance(hosts, list):
            return None, "unavailable"
        if not hosts:
            logger.info(
                "host rows empty dc=%s family=%s clusters=%s — cluster fallback",
                dc_code,
                family,
                cl or "all",
            )
            return [], "empty"
        return hosts, "ok"

    def _get_sellable_calc_config(self) -> dict[str, float | str]:
        """Load dual-CPU sellable calc variables from gui_crm_calc_config."""
        defaults: dict[str, float | str] = {
            "effective_ghz_per_unit": 1.0,
            "physical_price_unit": "GHz",
            "power_core_to_ghz": 3.3,
        }
        if not self._webui.is_available:
            return defaults
        keys = (_CALC_EFFECTIVE_GHZ_KEY, _CALC_PHYSICAL_PRICE_UNIT_KEY, _CALC_POWER_CORE_GHZ_KEY)
        try:
            rows = self._webui.run_rows(
                "SELECT config_key, config_value FROM gui_crm_calc_config WHERE config_key = ANY(%s)",
                (list(keys),),
            )
        except Exception:
            logger.exception("sellable calc config load failed")
            return defaults
        by_key = {str(r["config_key"]): r.get("config_value") for r in rows or []}
        try:
            defaults["effective_ghz_per_unit"] = float(
                by_key.get(_CALC_EFFECTIVE_GHZ_KEY, defaults["effective_ghz_per_unit"])
            )
        except (TypeError, ValueError):
            pass
        defaults["physical_price_unit"] = str(
            by_key.get(_CALC_PHYSICAL_PRICE_UNIT_KEY, defaults["physical_price_unit"]) or "GHz"
        )
        try:
            defaults["power_core_to_ghz"] = float(
                by_key.get(_CALC_POWER_CORE_GHZ_KEY, defaults["power_core_to_ghz"])
            )
        except (TypeError, ValueError):
            pass
        return defaults

    def _fetch_compute_response(
        self, dc_code: str, family: str, clusters: list[str] | None
    ) -> dict | None:
        """Fetch datacenter-api /compute/{kind} JSON (optional cluster filter)."""
        kind = _FAMILY_COMPUTE_ENDPOINT.get(family)
        if not kind or not dc_code or dc_code == "*" or not self._dc_api_url:
            return None
        params = ["preset=30d"]
        cl = [c for c in (clusters or []) if c]
        if cl:
            params.append(f"clusters={','.join(cl)}")
        url = (
            f"{self._dc_api_url}/api/v1/datacenters/{dc_code}/compute/{kind}"
            f"?{'&'.join(params)}"
        )
        try:
            resp = httpx.get(url, timeout=15.0)
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else None
        except Exception:
            logger.warning("compute fetch failed dc=%s family=%s url=%s", dc_code, family, url)
            return None

    def _apply_host_based_constraints(
        self,
        group: "list[PanelResult]",
        ratio: ResourceRatio,
        host_rows: "list[dict]",
        unit_lookup: dict[tuple[str, str], UnitConversion],
        *,
        effective_ghz_per_unit: float = 1.0,
    ) -> "list[PanelResult]":
        """Recompute CPU/RAM panel totals + dual-track sellable from per-host rows."""
        by_kind = {p.resource_kind: p for p in group}
        cpu_p = by_kind.get("cpu")
        ram_p = by_kind.get("ram")
        if cpu_p is None or ram_p is None:
            return constrain_by_ratio(group, ratio)

        cpu_conv = self._lookup_conversion(unit_lookup, "GHz", cpu_p.display_unit)
        ram_conv = self._lookup_conversion(unit_lookup, "GB", ram_p.display_unit)

        host_units: list[dict] = []
        cpu_total = cpu_alloc = cpu_total_phys = cpu_alloc_phys = 0.0
        ram_total = ram_alloc = 0.0
        cpu_raw_sum = cpu_raw_phys_sum = ram_raw_sum = 0.0
        for h in host_rows:
            ghz = float(h.get("ghz_per_core") or 1.0)
            cap_ghz = float(h.get("cpu_cap_ghz") or 0.0)
            alloc_sales = float(h.get("cpu_alloc_ghz") or 0.0)
            alloc_phys = float(h.get("cpu_alloc_ghz_physical") or alloc_sales * ghz)
            hc = convert_unit(cap_ghz, cpu_conv)
            ha = convert_unit(alloc_sales, cpu_conv)
            mc = convert_unit(float(h.get("mem_cap_gb") or 0.0), ram_conv)
            ma = convert_unit(float(h.get("mem_alloc_gb") or 0.0), ram_conv)
            host_units.append({
                "cpu_total": hc,
                "cpu_alloc": ha,
                "cpu_total_phys": cap_ghz,
                "cpu_alloc_phys": alloc_phys,
                "ghz_per_core": ghz,
                "ram_total": mc,
                "ram_alloc": ma,
            })
            cpu_total += hc
            cpu_alloc += ha
            cpu_total_phys += cap_ghz
            cpu_alloc_phys += alloc_phys
            ram_total += mc
            ram_alloc += ma
            cpu_raw_sum += apply_threshold(hc, ha, cpu_p.threshold_pct)
            cpu_raw_phys_sum += apply_threshold(cap_ghz, alloc_phys, cpu_p.threshold_pct)
            ram_raw_sum += apply_threshold(mc, ma, ram_p.threshold_pct)

        note = f"host-based ({len(host_units)} host)"
        rebuilt: list[PanelResult] = []
        for p in group:
            if p.resource_kind == "cpu":
                p.total = cpu_total
                p.allocated = cpu_alloc
                p.sellable_raw = cpu_raw_sum
                p.sellable_physical = cpu_raw_phys_sum
                p.sellable_effective = cpu_raw_sum
                p.notes = [*p.notes, note]
                p.computation_mode = "host_based"
            elif p.resource_kind == "ram":
                p.total = ram_total
                p.allocated = ram_alloc
                p.sellable_raw = ram_raw_sum
                p.notes = [*p.notes, note]
            rebuilt.append(p)

        return constrain_by_ratio_per_host_dual(
            rebuilt,
            ratio,
            host_units,
            cpu_threshold_pct=cpu_p.threshold_pct,
            ram_threshold_pct=ram_p.threshold_pct,
            effective_ghz_per_unit=effective_ghz_per_unit,
        )

    def _apply_cluster_fallback_dual(
        self,
        group: "list[PanelResult]",
        ratio: ResourceRatio,
        dc_code: str,
        family: str,
        clusters: list[str] | None,
        *,
        host_status: str,
        effective_ghz_per_unit: float = 1.0,
        decouple_resource_kinds: frozenset[str] | None = None,
    ) -> "list[PanelResult]":
        """Cluster-level fallback with dual CPU when host rows are unavailable."""
        cpu_p = next((p for p in group if p.resource_kind == "cpu"), None)
        if cpu_p is None:
            return constrain_by_ratio(group, ratio, decouple_resource_kinds=decouple_resource_kinds)

        raw = self._fetch_compute_response(dc_code, family, clusters)
        cpu_raw_phys = cpu_raw_eff = cpu_p.sellable_raw
        if raw:
            cap = float(raw.get("cpu_cap") or cpu_p.total or 0.0)
            alloc_phys = float(raw.get("cpu_alloc_ghz_vm") or 0.0)
            alloc_eff = float(raw.get("cpu_alloc_ghz_sales") or cpu_p.allocated or 0.0)
            cpu_raw_phys = apply_threshold(cap, alloc_phys, cpu_p.threshold_pct)
            cpu_raw_eff = apply_threshold(cap, alloc_eff, cpu_p.threshold_pct)
            cpu_conv = None
            if cpu_p.display_unit.lower() not in ("ghz",):
                cpu_conv = UnitConversion("GHz", cpu_p.display_unit, 1.0, "divide", False)
            if cpu_conv:
                cpu_p.total = convert_unit(cap, cpu_conv)
                cpu_p.allocated = convert_unit(alloc_eff, cpu_conv)
            else:
                cpu_p.total = cap
                cpu_p.allocated = alloc_eff
            cpu_p.sellable_raw = cpu_raw_eff
            cpu_p.sellable_effective = cpu_raw_eff
            cpu_p.sellable_physical = cpu_raw_phys

        note = f"cluster_fallback ({host_status})"
        for p in group:
            if p.resource_kind == "cpu":
                p.notes = [*p.notes, note]
            p.computation_mode = "cluster_fallback"

        return constrain_by_ratio_dual_cpu_cluster(
            group,
            ratio,
            cpu_raw_physical=cpu_raw_phys,
            cpu_raw_effective=cpu_raw_eff,
            decouple_resource_kinds=decouple_resource_kinds,
        )

    def _apply_dual_cpu_pricing(self, panel: PanelResult, calc_cfg: dict[str, float | str]) -> None:
        """Populate potential_tl_physical / potential_tl_effective on CPU panels."""
        if panel.resource_kind != "cpu":
            return
        price_eff = panel.unit_price_tl
        price_phys = price_eff
        phys_unit = str(calc_cfg.get("physical_price_unit") or "GHz").upper()
        if phys_unit == "GHZ" and panel.display_unit.upper() in ("VCPU", "CORE", "CPU"):
            ghz_factor = float(calc_cfg.get("effective_ghz_per_unit") or 1.0)
            if ghz_factor > 0:
                price_phys = price_eff / ghz_factor
        if panel.sellable_physical is not None:
            panel.potential_tl_physical = compute_potential_tl(panel.sellable_physical, price_phys)
        if panel.sellable_effective is not None:
            panel.potential_tl_effective = compute_potential_tl(panel.sellable_effective, price_eff)
        phys_tl = panel.potential_tl_physical if panel.potential_tl_physical is not None else panel.potential_tl
        eff_tl = panel.potential_tl_effective if panel.potential_tl_effective is not None else panel.potential_tl
        panel.potential_tl_min = min(phys_tl, eff_tl)
        panel.potential_tl_max = max(phys_tl, eff_tl)
        panel.potential_tl = (panel.potential_tl_min + panel.potential_tl_max) / 2.0

    # ------------------------------------------- architecture storage range

    def _query_storage_range_inputs(self, dc_code: str) -> "dict | None":
        """Fetch KM datastore backing aggregates + IBM storage totals (GB).

        Returns None when the datalake is unreachable so callers keep the
        legacy single-value storage sellable.
        """
        pattern = self._dc_pattern(dc_code)
        try:
            with self._svc._get_connection() as conn:
                with conn.cursor() as cur:
                    backing_rows = self._svc._run_rows(
                        cur, sq.KM_DATASTORE_BACKING_AGG, (pattern,)
                    ) or []
                    ibm_rows = self._svc._run_rows(
                        cur, sq.IBM_STORAGE_SYSTEM_TOTALS, (pattern,)
                    ) or []
        except Exception:
            logger.exception("storage range inputs failed dc=%s", dc_code)
            return None

        _gb = 1024.0 ** 3
        out = {
            "intel_cap_gb": 0.0, "intel_used_gb": 0.0,
            "ibm_ds_cap_gb": 0.0, "ibm_ds_used_gb": 0.0,
            "ibm_total_gb": 0.0, "ibm_used_gb": 0.0,
        }
        for r in backing_rows:
            backing = (r[0] or "").strip().lower()
            cap_gb = float(r[1] or 0) / _gb
            used_gb = float(r[2] or 0) / _gb
            if backing == "ibm":
                out["ibm_ds_cap_gb"] += cap_gb
                out["ibm_ds_used_gb"] += used_gb
            else:
                out["intel_cap_gb"] += cap_gb
                out["intel_used_gb"] += used_gb
        for r in ibm_rows:
            out["ibm_total_gb"] += parse_storage_string_to_gb(r[2])
            out["ibm_used_gb"] += parse_storage_string_to_gb(r[3])
        return out

    def _apply_storage_range(
        self,
        group: "list[PanelResult]",
        family: str,
        range_inputs: "dict | None",
        unit_lookup: dict[tuple[str, str], UnitConversion],
    ) -> None:
        """Populate the family's storage panel with the [min, max] sellable range.

        KM (virt_classic): min = Intel-backed datastore free, max = + IBM-backed
        datastore free. Power (virt_power): min = IBM storage free − KM-exposed
        IBM datastore free, max = full IBM storage free. The conservative min is
        published as ``sellable_constrained`` (headline number); the range is
        carried in ``sellable_min`` / ``sellable_max``.
        """
        if not range_inputs:
            return
        sto_p = next((p for p in group if p.resource_kind == "storage"), None)
        if sto_p is None:
            return

        thr = sto_p.threshold_pct
        intel_free = apply_threshold(range_inputs["intel_cap_gb"], range_inputs["intel_used_gb"], thr)
        ibm_ds_free = apply_threshold(range_inputs["ibm_ds_cap_gb"], range_inputs["ibm_ds_used_gb"], thr)
        ibm_free = apply_threshold(range_inputs["ibm_total_gb"], range_inputs["ibm_used_gb"], thr)
        rng = compute_storage_range(
            intel_free=intel_free,
            ibm_backed_datastore_free=ibm_ds_free,
            ibm_storage_free=ibm_free,
        )

        conv = self._lookup_conversion(unit_lookup, "GB", sto_p.display_unit)
        if family == "virt_classic":
            total_gb = range_inputs["intel_cap_gb"] + range_inputs["ibm_ds_cap_gb"]
            used_gb = range_inputs["intel_used_gb"] + range_inputs["ibm_ds_used_gb"]
            lo, hi = rng["km_min"], rng["km_max"]
            note = "KM storage range: min=Intel-backed, max=+IBM-backed datastore free"
        else:  # virt_power
            total_gb = range_inputs["ibm_total_gb"]
            # Realized attribution: KM-exposed datastore usage belongs to KM.
            used_gb = max(range_inputs["ibm_used_gb"] - range_inputs["ibm_ds_used_gb"], 0.0)
            lo, hi = rng["power_min"], rng["power_max"]
            note = "Power storage range: min=IBM free − KM-exposed, max=full IBM free"
        if total_gb <= 0:
            sto_p.notes = [*sto_p.notes, "storage range skipped: no backing capacity data"]
            return

        sto_p.total = convert_unit(total_gb, conv)
        sto_p.allocated = convert_unit(used_gb, conv)
        sto_p.sellable_min = convert_unit(lo, conv)
        sto_p.sellable_max = convert_unit(hi, conv)
        sto_p.sellable_raw = sto_p.sellable_max
        sto_p.sellable_constrained = sto_p.sellable_min
        sto_p.ratio_bound = False
        sto_p.has_infra_source = True
        sto_p.potential_tl_min = compute_potential_tl(sto_p.sellable_min, sto_p.unit_price_tl)
        sto_p.potential_tl_max = compute_potential_tl(sto_p.sellable_max, sto_p.unit_price_tl)
        sto_p.potential_tl = sto_p.potential_tl_min
        sto_p.notes = [*sto_p.notes, note]

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
        has_infra = bool(
            src.manual_total is not None
            or (src.source_table and src.total_column)
        )

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

    # -- result cache (crm-engine Redis DB 2) + Tier-2 durable webui-db ---------

    @staticmethod
    def _clusters_csv(selected_clusters: list[str] | None) -> str:
        if not selected_clusters:
            return ""
        return ",".join(sorted(c for c in selected_clusters if c))

    @staticmethod
    def _snapshot_family_key(family: str | None) -> str:
        return family if family else "*"

    def _snapshot_db_get(
        self,
        dc_code: str,
        family: str,
        clusters_csv: str,
    ) -> list[PanelResult] | None:
        if not self._webui.is_available:
            return None
        try:
            row = self._webui.run_one(
                sq.GET_PANEL_RESULT_SNAPSHOT,
                (dc_code or "*", family, clusters_csv),
            )
        except Exception:
            logger.debug("_snapshot_db_get failed dc=%s family=%s", dc_code, family)
            return None
        if not row or not row.get("payload"):
            return None
        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        if not isinstance(payload, list):
            return None
        try:
            results = [self._panel_result_from_dict(d) for d in payload]
        except Exception:
            logger.warning("_snapshot_db_get decode failed dc=%s family=%s", dc_code, family)
            return None
        logger.info(
            "Sellable cache hit tier=tier2 dc=%s family=%s clusters=%s panels=%d total_tl=%.2f",
            dc_code,
            family,
            clusters_csv,
            len(results),
            self._panel_results_total_tl(results),
        )
        return results

    def _snapshot_db_set(
        self,
        dc_code: str,
        family: str,
        clusters_csv: str,
        results: list[PanelResult],
    ) -> None:
        if not self._webui.is_available or not results:
            return
        try:
            payload = json.dumps([r.to_dict() for r in results])
            self._webui.execute(
                sq.UPSERT_PANEL_RESULT_SNAPSHOT,
                (dc_code or "*", family, clusters_csv, payload),
            )
        except Exception:
            logger.exception(
                "_snapshot_db_set failed dc=%s family=%s clusters=%s",
                dc_code, family, clusters_csv,
            )

    def _snapshot_db_invalidate(self, dc_code: str | None = None) -> None:
        webui = getattr(self, "_webui", None)
        if webui is None or not webui.is_available:
            return
        try:
            code = dc_code if dc_code and dc_code != "*" else None
            self._webui.execute(sq.DELETE_PANEL_RESULT_SNAPSHOTS, (code, code))
        except Exception:
            logger.exception("_snapshot_db_invalidate failed dc=%s", dc_code)

    def snapshot_meta(
        self,
        dc_code: str = "*",
        family: str | None = None,
        clusters: list[str] | None = None,
    ) -> dict[str, Any]:
        """Return latest Tier-2 snapshot timestamp for the given scope."""
        if not self._webui.is_available:
            return {"computed_at": None, "dc_code": dc_code, "family": family or "*"}
        fam_key = self._snapshot_family_key(family)
        clusters_csv = self._clusters_csv(clusters)
        try:
            row = self._webui.run_one(
                sq.GET_PANEL_RESULT_SNAPSHOT,
                (dc_code or "*", fam_key, clusters_csv),
            )
        except Exception:
            row = None
        if row and row.get("computed_at"):
            ts = row["computed_at"]
            return {
                "computed_at": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                "dc_code": dc_code or "*",
                "family": fam_key,
                "clusters_csv": clusters_csv,
            }
        try:
            row = self._webui.run_one(
                sq.GET_LATEST_SNAPSHOT_META,
                (dc_code if dc_code != "*" else None, dc_code if dc_code != "*" else None,
                 fam_key if family else None, fam_key if family else None),
            )
        except Exception:
            row = None
        if not row:
            return {"computed_at": None, "dc_code": dc_code, "family": fam_key}
        ts = row.get("computed_at")
        return {
            "computed_at": ts.isoformat() if hasattr(ts, "isoformat") else (str(ts) if ts else None),
            "dc_code": row.get("dc_code") or dc_code,
            "family": row.get("family") or fam_key,
            "clusters_csv": row.get("clusters_csv") or clusters_csv,
        }

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

    @staticmethod
    def _panel_results_total_tl(results: "list[PanelResult]") -> float:
        return sum(float(r.potential_tl or 0.0) for r in results)

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
            results = [self._panel_result_from_dict(d) for d in payload]
        except Exception:
            logger.warning("Sellable cache key=%s decode failed — ignoring", key)
            return None
        logger.info(
            "Sellable cache hit tier=redis key=%s panels=%d total_tl=%.2f",
            key,
            len(results),
            self._panel_results_total_tl(results),
        )
        return results

    def _result_cache_set(self, key: str, results: "list[PanelResult]") -> None:
        if self._crm_redis is None or _SELLABLE_CACHE_TTL <= 0:
            return
        try:
            payload = json.dumps([r.to_dict() for r in results])
            self._crm_redis.setex(key, _SELLABLE_CACHE_TTL, payload)
        except Exception:
            logger.exception("crm Redis SETEX failed key=%s", key)

    def invalidate_result_cache(self, dc_code: str | None = None) -> int:
        """Drop cached compute_all_panels payloads (Redis Tier-1 + webui Tier-2).

        Called after CRM config changes (panels, thresholds, infra sources, etc.).
        Scheduled ``snapshot_all`` does **not** call this — it overwrites keys in place
        so readers keep serving the last published snapshot until recompute succeeds.
        Returns the number of Redis keys deleted.
        """
        self._snapshot_db_invalidate(dc_code)
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
            sellable_min=(float(d["sellable_min"]) if d.get("sellable_min") is not None else None),
            sellable_max=(float(d["sellable_max"]) if d.get("sellable_max") is not None else None),
            potential_tl_min=(
                float(d["potential_tl_min"]) if d.get("potential_tl_min") is not None else None
            ),
            potential_tl_max=(
                float(d["potential_tl_max"]) if d.get("potential_tl_max") is not None else None
            ),
            sellable_physical=(
                float(d["sellable_physical"]) if d.get("sellable_physical") is not None else None
            ),
            sellable_effective=(
                float(d["sellable_effective"]) if d.get("sellable_effective") is not None else None
            ),
            potential_tl_physical=(
                float(d["potential_tl_physical"]) if d.get("potential_tl_physical") is not None else None
            ),
            potential_tl_effective=(
                float(d["potential_tl_effective"]) if d.get("potential_tl_effective") is not None else None
            ),
            computation_mode=d.get("computation_mode"),
        )

    def compute_all_panels(
        self,
        dc_code: str = "*",
        *,
        selected_clusters: list[str] | None = None,
        family: str | None = None,
        force_recompute: bool = False,
    ) -> list[PanelResult]:
        fam_key = self._snapshot_family_key(family)
        clusters_csv = self._clusters_csv(selected_clusters)

        # 1. Tier-1 Redis result cache lookup.
        cache_key = self._result_cache_key(dc_code, selected_clusters, family)
        if force_recompute:
            logger.info(
                "compute_all_panels: force_recompute=True dc=%s family=%s clusters=%s",
                dc_code,
                fam_key,
                clusters_csv,
            )
        else:
            cached = self._result_cache_get(cache_key)
            if cached is not None:
                return cached

        # 2. Tier-2 durable webui-db snapshot (repopulate Redis on hit).
        if not force_recompute:
            db_cached = self._snapshot_db_get(dc_code or "*", fam_key, clusters_csv)
            if db_cached is not None:
                self._result_cache_set(cache_key, db_cached)
                return db_cached

        # 3. Pull panel definitions; filter by family BEFORE any heavy lookup.
        defs = self.list_panel_defs()
        if family:
            defs = [d for d in defs if d.family == family]
        if not defs:
            self._result_cache_set(cache_key, [])
            self._snapshot_db_set(dc_code or "*", fam_key, clusters_csv, [])
            return []

        # 4. Bulk-load WebUI metadata in 3 queries instead of N×3 round-trips.
        unit_lookup = self._build_unit_lookup()
        infra_lookup = self._bulk_load_infra_sources(dc_code)
        threshold_lookup = self._bulk_load_thresholds(dc_code)
        price_overrides = self._bulk_load_price_overrides()

        # 5. Pre-fetch datacenter-api Redis payload once (totals + allocated).
        needs_redis_payload = any(
            self._infra_uses_dc_redis_payload(
                infra_lookup.get(d.panel_key) or InfraSource(panel_key=d.panel_key, dc_code=dc_code)
            )
            for d in defs
        )
        dc_payload = self._load_dc_redis_payload(dc_code) if needs_redis_payload else None

        # 6. Per-family /compute response cache — 3 cpu/ram/storage panels of
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

        # 7. Apply ratio per family — host-based for virt_classic / virt_hyperconverged
        #    (per-host min(CPU, RAM), summed across hosts), aggregate otherwise.
        by_family: dict[str, list[PanelResult]] = defaultdict(list)
        for r in results:
            by_family[r.family].append(r)
        ratio_lookup = {(r.family, r.dc_code): r for r in self.list_ratios()}

        # Architecture storage range inputs are shared by virt_classic + virt_power.
        # Only hit the datalake when a storage panel of a range family is present.
        range_inputs: dict | None = None
        needs_range = any(
            r.resource_kind == "storage" and r.family in _STORAGE_RANGE_FAMILIES
            for r in results
        )
        if dc_code and dc_code != "*" and needs_range:
            range_inputs = self._query_storage_range_inputs(dc_code)

        constrained: list[PanelResult] = []
        virt_power_storage_decouple = frozenset({"storage"})
        calc_cfg = self._get_sellable_calc_config()
        effective_ghz = float(calc_cfg.get("effective_ghz_per_unit") or 1.0)
        for fam, group in by_family.items():
            ratio = ratio_lookup.get((fam, dc_code)) or ratio_lookup.get((fam, "*")) or ResourceRatio(family=fam)

            host_rows: list[dict] | None = None
            host_status = "unavailable"
            if fam in _HOST_BASED_FAMILIES:
                host_rows, host_status = self._fetch_host_rows(dc_code, fam, selected_clusters)

            if host_rows:
                new_group = self._apply_host_based_constraints(
                    group, ratio, host_rows, unit_lookup, effective_ghz_per_unit=effective_ghz
                )
            elif fam in _HOST_BASED_FAMILIES:
                decouple = None
                new_group = self._apply_cluster_fallback_dual(
                    group,
                    ratio,
                    dc_code,
                    fam,
                    selected_clusters,
                    host_status=host_status,
                    effective_ghz_per_unit=effective_ghz,
                    decouple_resource_kinds=decouple,
                )
            else:
                decouple = virt_power_storage_decouple if fam == "virt_power" else None
                new_group = constrain_by_ratio(group, ratio, decouple_resource_kinds=decouple)

            if fam in _STORAGE_RANGE_FAMILIES and range_inputs:
                self._apply_storage_range(new_group, fam, range_inputs, unit_lookup)
            elif fam in _STORAGE_RANGE_FAMILIES and needs_range and range_inputs is None:
                sto_p = next((p for p in new_group if p.resource_kind == "storage"), None)
                if sto_p is not None:
                    sto_p.notes = [*sto_p.notes, "storage range skipped: datalake inputs unavailable"]

            for new in new_group:
                if new.resource_kind == "cpu" and (
                    new.sellable_physical is not None or new.sellable_effective is not None
                ):
                    self._apply_dual_cpu_pricing(new, calc_cfg)
                else:
                    new.potential_tl = compute_potential_tl(new.sellable_constrained, new.unit_price_tl)
                if new.sellable_min is not None and new.potential_tl_min is None:
                    new.potential_tl_min = compute_potential_tl(new.sellable_min, new.unit_price_tl)
                if new.sellable_max is not None and new.potential_tl_max is None:
                    new.potential_tl_max = compute_potential_tl(new.sellable_max, new.unit_price_tl)
                constrained.append(new)
        constrained.sort(key=lambda p: (p.family, p.resource_kind, p.panel_key))

        self._result_cache_set(cache_key, constrained)
        self._snapshot_db_set(dc_code or "*", fam_key, clusters_csv, constrained)
        if family:
            total_tl = sum(r.potential_tl for r in constrained)
            logger.info(
                "compute_all_panels: dc=%s family=%s force_recompute=%s panels=%d total_tl=%.2f",
                dc_code,
                family,
                force_recompute,
                len(constrained),
                total_tl,
            )
        return constrained

    @staticmethod
    def _panel_summary_dict(panel: PanelResult) -> dict:
        """Slim panel payload for rollup-only summary responses."""
        return {
            "panel_key": panel.panel_key,
            "label": panel.label,
            "resource_kind": panel.resource_kind,
            "display_unit": panel.display_unit,
            "total": panel.total,
            "allocated": panel.allocated,
            "threshold_pct": panel.threshold_pct,
            "sellable_constrained": panel.sellable_constrained,
            "sellable_raw": panel.sellable_raw,
            "sellable_min": panel.sellable_min,
            "sellable_max": panel.sellable_max,
            "sellable_physical": panel.sellable_physical,
            "sellable_effective": panel.sellable_effective,
            "potential_tl": panel.potential_tl,
            "potential_tl_min": panel.potential_tl_min,
            "potential_tl_max": panel.potential_tl_max,
            "computation_mode": panel.computation_mode,
            "has_infra_source": panel.has_infra_source,
            "has_price": panel.has_price,
        }

    def compute_summary(
        self,
        dc_code: str = "*",
        *,
        selected_clusters: list[str] | None = None,
        family: str | None = None,
        force_recompute: bool = False,
        include_panel_details: bool = True,
    ) -> DashboardSummary:
        panels = self.compute_all_panels(
            dc_code=dc_code,
            selected_clusters=selected_clusters,
            family=family,
            force_recompute=force_recompute,
        )

        by_family: dict[str, list[PanelResult]] = defaultdict(list)
        for p in panels:
            by_family[p.family].append(p)

        family_aggs: list[FamilyAggregate] = []
        total_potential = 0.0
        total_potential_min = 0.0
        total_potential_max = 0.0
        constrained_loss = 0.0
        computation_modes: dict[str, str] = {}
        mapped_count = 0
        for family, group in by_family.items():
            label_lookup = group[0].label.split(" — ")[0] if group else family
            mode = next(
                (p.computation_mode for p in group if p.computation_mode),
                None,
            )
            if mode:
                computation_modes[family] = mode
            agg = FamilyAggregate(
                family=family,
                label=label_lookup,
                dc_code=dc_code,
                panels=group,
                computation_mode=mode,
                mapped_panel_count=sum(1 for p in group if p.has_infra_source or p.has_price),
            )
            family_potential = sum(p.potential_tl for p in group)
            family_min = sum(
                (p.potential_tl_min if p.potential_tl_min is not None else p.potential_tl) for p in group
            )
            family_max = sum(
                (p.potential_tl_max if p.potential_tl_max is not None else p.potential_tl) for p in group
            )
            family_raw_potential = sum(compute_potential_tl(p.sellable_raw, p.unit_price_tl) for p in group)
            agg.total_potential_tl = family_potential
            agg.total_potential_tl_min = family_min
            agg.total_potential_tl_max = family_max
            agg.constrained_loss_tl = max(family_raw_potential - family_potential, 0.0)
            agg.total_sellable_constrained_units = {
                p.resource_kind: agg.total_sellable_constrained_units.get(p.resource_kind, 0.0) + p.sellable_constrained
                for p in group
            }
            for p in group:
                kind = (p.resource_kind or "other").lower()
                if kind in {"cpu", "ram", "storage", "other"} and kind not in agg.panel_summaries:
                    agg.panel_summaries[kind] = self._panel_summary_dict(p)
            mapped_count += agg.mapped_panel_count
            family_aggs.append(agg)
            total_potential += family_potential
            total_potential_min += family_min
            total_potential_max += family_max
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
            total_potential_tl_min=total_potential_min,
            total_potential_tl_max=total_potential_max,
            mapped_panel_count=mapped_count,
            computation_modes=computation_modes,
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
        mapped_ids: set[str] = set()
        if self._webui.is_available:
            try:
                rows = self._webui.run_rows(
                    "SELECT productid FROM gui_crm_service_mapping_seed "
                    "UNION SELECT productid FROM gui_crm_service_mapping_override"
                )
                mapped_ids = {str(r["productid"]) for r in rows if r.get("productid")}
            except Exception:  # noqa: BLE001
                logger.exception("Unmapped count: webui mapping fetch failed")
                return 0
        bind_ids = list(mapped_ids) if mapped_ids else ["__none__"]
        try:
            with self._svc._get_connection() as conn:
                with conn.cursor() as cur:
                    val = self._svc._run_value(
                        cur,
                        "SELECT COUNT(*)::bigint FROM discovery_crm_products "
                        "WHERE productid != ALL(%s::text[])",
                        (bind_ids,),
                    )
        except Exception:  # noqa: BLE001
            logger.exception("Unmapped product count failed")
            return 0
        return int(val or 0)

    # ------------------------------------------------------------------ snapshot

    def _fetch_datacenter_codes_from_redis(self) -> list[str]:
        """Discover DC codes from datacenter-api Redis keys when HTTP summary fails."""
        if self._dc_redis is None:
            return []
        codes: set[str] = set()
        try:
            for key in self._dc_redis.scan_iter(match="dc_details:*", count=200):
                parts = str(key).split(":")
                if len(parts) >= 2 and parts[1]:
                    codes.add(parts[1])
        except Exception:
            logger.exception("_fetch_datacenter_codes_from_redis scan failed")
            return []
        out = sorted(codes)
        if out:
            logger.info("_fetch_datacenter_codes: resolved %d DC(s) from Redis scan", len(out))
        return out

    def _fetch_datacenter_codes(self) -> list[str]:
        """List active DC codes from datacenter-api (for scheduler prewarm)."""
        if not self._dc_api_url:
            return self._fetch_datacenter_codes_from_redis()
        days = max(_DC_DETAILS_WINDOW_DAYS, 1)
        url = f"{self._dc_api_url}/api/v1/datacenters/summary?preset={days}d"
        try:
            resp = httpx.get(url, timeout=_SELLABLE_DC_CODES_TIMEOUT)
            resp.raise_for_status()
            rows = resp.json()
        except Exception:
            logger.warning(
                "_fetch_datacenter_codes HTTP failed url=%s timeout=%.0fs — Redis scan fallback",
                url,
                _SELLABLE_DC_CODES_TIMEOUT,
            )
            return self._fetch_datacenter_codes_from_redis()
        if not isinstance(rows, list):
            return self._fetch_datacenter_codes_from_redis()
        out: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            dc_id = row.get("id") or row.get("dc_code") or row.get("name")
            if dc_id:
                out.append(str(dc_id))
        if not out:
            return self._fetch_datacenter_codes_from_redis()
        logger.info("_fetch_datacenter_codes: resolved %d DC(s) from summary API", len(out))
        return out

    def _prewarm_dc_virt_snapshots(self) -> int:
        """Compute and persist per-DC virt family snapshots for the DC list page.

        Matches ``datacenters._virt_sellable_tl_for_dc`` which passes ``clusters=None``
        (dc-wide datalake + Redis path, not cluster-scoped compute).
        """
        dc_codes = self._fetch_datacenter_codes()
        if not dc_codes:
            return 0
        warmed = 0
        for dc in dc_codes:
            for family in (
                "virt_classic",
                "virt_hyperconverged",
                "virt_power",
                "virt_power_hana",
            ):
                try:
                    self.compute_all_panels(
                        dc_code=dc,
                        family=family,
                        force_recompute=True,
                    )
                    warmed += 1
                except Exception:
                    logger.exception(
                        "_prewarm_dc_virt_snapshots failed dc=%s family=%s",
                        dc, family,
                    )
        return warmed

    def snapshot_all(self) -> int:
        """Compute the global dashboard, push every metric into TaggingService
        cache + persist a snapshot row. Returns the number of metrics emitted.

        Prewarms per-DC virt snapshots and overwrites Tier-1/Tier-2 panel caches
        per successful scope. Does not invalidate existing caches up front — readers
        keep the last published values until a scope recomputes successfully.
        """
        prewarmed = self._prewarm_dc_virt_snapshots()
        logger.info("SellableService.snapshot_all: prewarmed %d per-DC family snapshots", prewarmed)
        try:
            summary = self.compute_summary("*", force_recompute=True)
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
