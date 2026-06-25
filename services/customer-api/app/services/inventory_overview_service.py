"""Global CRM inventory overview — merges sellable infra panels with CRM entitled sales."""
from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from typing import Any

from app.db.queries import crm_sales as sq
from app.db.queries import sellable as sellable_sq
from app.db.queries import service_mapping as smq
from app.services.crm_config_service import CrmConfigService
from app.services.sales_service import SalesService
from app.services.sellable_service import SellableService
from app.services.webui_db import WebuiPool
from app.utils.usage_comparison import (
    aggregate_entitled_by_panel_key,
    panel_inventory_status,
)
from shared.sellable.models import PanelResult

logger = logging.getLogger(__name__)

_INVENTORY_CACHE_TTL_SEC = 300.0
_INVENTORY_REDIS_PREFIX = "crm:inventory_overview:"

_VIRT_FAMILY_LABELS: dict[str, str] = {
    "virt_classic": "Klasik Mimari",
    "virt_hyperconverged": "Hyperconverged",
    "virt_power": "Power",
    "virt_power_hana": "Power HANA",
    "virt_intel_hana": "Intel HANA",
}

_RESOURCE_SUFFIXES = ("_cpu", "_ram", "_storage")


def _humanize_token(value: str) -> str:
    return (value or "").replace("_", " ").replace(".", " ").strip().title()


def _infer_family_key(panel_key: str, panel_defs: dict[str, dict[str, Any]]) -> str:
    if panel_key in panel_defs:
        return str(panel_defs[panel_key].get("family") or panel_key)
    for suffix in _RESOURCE_SUFFIXES:
        if panel_key.endswith(suffix):
            return panel_key[: -len(suffix)]
    return panel_key


def _family_label(
    family_key: str,
    *,
    service_label: str,
    gui_tab_binding: str | None,
) -> str:
    if family_key in _VIRT_FAMILY_LABELS:
        return _VIRT_FAMILY_LABELS[family_key]
    if " — " in service_label:
        return service_label.split(" — ", 1)[0].strip()
    if gui_tab_binding:
        parts = [p for p in gui_tab_binding.split(".") if p]
        if len(parts) >= 2:
            return _humanize_token(parts[-1])
        if parts:
            return _humanize_token(parts[0])
    return _humanize_token(family_key)


def _crm_product_names_summary(names: list[str] | None, limit: int = 3) -> str:
    items = [n for n in (names or []) if n]
    if not items:
        return ""
    if len(items) <= limit:
        return ", ".join(items)
    rest = len(items) - limit
    return f"{', '.join(items[:limit])} (+{rest} more)"


def _merge_panel_results(existing: PanelResult | None, incoming: PanelResult) -> PanelResult:
    """Sum total/allocated across DC-scoped PanelResult rows; sellable is recomputed later."""
    if existing is None:
        mode = incoming.computation_mode
        if incoming.has_infra_source and not mode:
            mode = "aggregated"
        return PanelResult(
            panel_key=incoming.panel_key,
            label=incoming.label,
            family=incoming.family,
            resource_kind=incoming.resource_kind,
            display_unit=incoming.display_unit,
            dc_code="*",
            total=float(incoming.total or 0.0),
            allocated=float(incoming.allocated or 0.0),
            threshold_pct=incoming.threshold_pct,
            sellable_raw=0.0,
            sellable_constrained=0.0,
            unit_price_tl=incoming.unit_price_tl,
            potential_tl=0.0,
            ratio_bound=False,
            gate_blocked=False,
            has_infra_source=incoming.has_infra_source,
            has_price=incoming.has_price,
            notes=list(incoming.notes or []),
            computation_mode=mode,
            constraint_reason=incoming.constraint_reason,
        )

    notes = list(existing.notes or [])
    for note in incoming.notes or []:
        if note and note not in notes:
            notes.append(note)

    mode = "aggregated"
    if existing.computation_mode == "host_based" or incoming.computation_mode == "host_based":
        mode = "host_based"

    return PanelResult(
        panel_key=existing.panel_key,
        label=existing.label,
        family=existing.family,
        resource_kind=existing.resource_kind,
        display_unit=existing.display_unit,
        dc_code="*",
        total=float(existing.total or 0.0) + float(incoming.total or 0.0),
        allocated=float(existing.allocated or 0.0) + float(incoming.allocated or 0.0),
        threshold_pct=existing.threshold_pct,
        sellable_raw=0.0,
        sellable_constrained=0.0,
        unit_price_tl=existing.unit_price_tl or incoming.unit_price_tl,
        potential_tl=0.0,
        ratio_bound=False,
        gate_blocked=False,
        has_infra_source=existing.has_infra_source or incoming.has_infra_source,
        has_price=existing.has_price or incoming.has_price,
        notes=notes,
        computation_mode=mode,
        constraint_reason="none",
    )


def _assess_data_quality(
    panel: PanelResult,
    *,
    crm_sold: float,
) -> str | None:
    """Return 'suspect' when merged infra numbers look inconsistent."""
    if not panel.has_infra_source:
        return None
    total = float(panel.total or 0.0)
    allocated = float(panel.allocated or 0.0)
    crm = max(float(crm_sold or 0.0), 1.0)
    if total > 1e9 or total > 100.0 * crm:
        return "suspect"
    if (
        allocated <= 0.0
        and total > 0.0
        and (panel.computation_mode or "") in ("aggregated", "cluster_fallback")
    ):
        return "suspect"
    return None


class InventoryOverviewService:
    """Build global capacity vs CRM sold vs infra used overview."""

    def __init__(
        self,
        *,
        sellable: SellableService,
        sales: SalesService,
        webui: WebuiPool,
        config: CrmConfigService | None = None,
        crm_redis=None,
    ):
        self._sellable = sellable
        self._sales = sales
        self._webui = webui
        self._config = config or CrmConfigService(webui)
        self._crm_redis = crm_redis
        self._mapping_cache: tuple[float, dict[str, dict[str, Any]]] | None = None
        self._pages_cache: tuple[float, dict[str, dict[str, Any]]] | None = None
        self._panel_defs_cache: tuple[float, dict[str, dict[str, Any]]] | None = None

    def is_available(self) -> bool:
        return self._sellable.is_available

    def _load_product_mapping(self) -> dict[str, dict[str, Any]]:
        now = time.perf_counter()
        if self._mapping_cache and (now - self._mapping_cache[0]) < 120.0:
            return self._mapping_cache[1]
        if not self._webui or not self._webui.is_available:
            return {}
        rows = self._webui.run_rows(smq.LIST_SERVICE_MAPPINGS_WEBUI)
        mapping = {str(r["productid"]): r for r in rows if r.get("productid")}
        self._mapping_cache = (now, mapping)
        return mapping

    def _load_service_pages(self) -> dict[str, dict[str, Any]]:
        now = time.perf_counter()
        if self._pages_cache and (now - self._pages_cache[0]) < 120.0:
            return self._pages_cache[1]
        if not self._webui or not self._webui.is_available:
            return {}
        rows = self._webui.run_rows(smq.LIST_SERVICE_PAGES)
        pages = {str(r["page_key"]): r for r in rows if r.get("page_key")}
        self._pages_cache = (now, pages)
        return pages

    def _load_panel_defs(self) -> dict[str, dict[str, Any]]:
        now = time.perf_counter()
        if self._panel_defs_cache and (now - self._panel_defs_cache[0]) < 120.0:
            return self._panel_defs_cache[1]
        if not self._webui or not self._webui.is_available:
            return {}
        rows = self._webui.run_rows(sellable_sq.LIST_PANEL_DEFS)
        defs = {str(r["panel_key"]): r for r in rows if r.get("panel_key")}
        self._panel_defs_cache = (now, defs)
        return defs

    def _mapped_product_ids(self, mapping: dict[str, dict[str, Any]]) -> list[str]:
        return [
            pid
            for pid, row in mapping.items()
            if (row.get("source") or "") != "unmatched" and row.get("category_code")
        ]

    def _panel_unit_index(self, panels: list[PanelResult]) -> dict[str, str]:
        return {p.panel_key: p.display_unit for p in panels if p.panel_key}

    def _list_infra_dc_codes(self) -> list[str]:
        """Return DC codes that have configured infra bindings in webui-db."""
        if not self._webui or not self._webui.is_available:
            return []
        rows = self._webui.run_rows(sellable_sq.LIST_INFRA_DC_CODES)
        return [
            str(r["dc_code"]).strip()
            for r in rows
            if r.get("dc_code") and str(r["dc_code"]).strip() not in ("", "*")
        ]

    def _load_global_only_panel_keys(self) -> frozenset[str]:
        """Panels with wildcard-only infra bindings and no per-DC filter."""
        if not self._webui or not self._webui.is_available:
            return frozenset()
        rows = self._webui.run_rows(sellable_sq.LIST_GLOBAL_ONLY_PANEL_KEYS)
        return frozenset(
            str(r["panel_key"]).strip()
            for r in rows
            if r.get("panel_key")
        )

    def _load_sellable_panels(
        self,
        dc_code: str,
        *,
        force_recompute: bool = False,
    ) -> list[PanelResult]:
        """Load sellable panels; global '*' aggregates per-DC infra across all bound DCs."""
        norm = (dc_code or "*").strip() or "*"
        if norm != "*":
            return self._sellable.compute_all_panels(
                dc_code=norm,
                force_recompute=force_recompute,
            )

        dc_codes = self._list_infra_dc_codes()
        global_only_keys = self._load_global_only_panel_keys()
        if not dc_codes:
            return self._sellable.compute_all_panels(
                dc_code="*",
                force_recompute=force_recompute,
            )

        merged: dict[str, PanelResult] = {}
        for code in dc_codes:
            for panel in self._sellable.compute_all_panels(
                dc_code=code,
                force_recompute=force_recompute,
            ):
                if not panel.has_infra_source:
                    if panel.panel_key not in merged:
                        merged[panel.panel_key] = panel
                    continue
                if panel.panel_key in global_only_keys:
                    continue
                merged[panel.panel_key] = _merge_panel_results(
                    merged.get(panel.panel_key),
                    panel,
                )

        wildcard_panels = self._sellable.compute_all_panels(
            dc_code="*",
            force_recompute=force_recompute,
        )
        for panel in wildcard_panels:
            key = panel.panel_key
            if key in global_only_keys:
                if panel.has_infra_source:
                    merged[key] = panel
                elif key not in merged:
                    merged[key] = panel
                continue
            if key not in merged:
                merged[key] = panel
            elif panel.has_infra_source and not merged[key].has_infra_source:
                merged[key] = _merge_panel_results(merged.get(key), panel)

        merged_list = list(merged.values())
        recomputed = self._sellable.recompute_family_constraints(
            merged_list,
            dc_code="*",
            infra_dc_codes=dc_codes,
        )
        logger.info(
            "inventory overview: aggregated sellable panels from %d DC(s), %d panel keys",
            len(dc_codes),
            len(recomputed),
        )
        return recomputed

    def _resolve_labels(
        self,
        panel_key: str,
        *,
        panel: PanelResult | None,
        entitled: dict[str, Any] | None,
        panel_defs: dict[str, dict[str, Any]],
        service_pages: dict[str, dict[str, Any]],
    ) -> tuple[str, str, str, str | None]:
        page = service_pages.get(panel_key) or {}
        pdef = panel_defs.get(panel_key) or {}
        service_label = (
            page.get("category_label")
            or (entitled or {}).get("category_label")
            or (panel.label if panel else None)
            or pdef.get("label")
            or panel_key
        )
        family_key = (
            (panel.family if panel else None)
            or pdef.get("family")
            or _infer_family_key(panel_key, panel_defs)
        )
        family_key = str(family_key or panel_key)
        gui_tab = page.get("gui_tab_binding")
        family_label = _family_label(
            family_key,
            service_label=str(service_label),
            gui_tab_binding=str(gui_tab) if gui_tab else None,
        )
        display_unit = (
            (panel.display_unit if panel else None)
            or pdef.get("display_unit")
            or page.get("resource_unit")
            or (entitled or {}).get("resource_unit")
            or "Adet"
        )
        return str(service_label), family_key, family_label, str(display_unit)

    def _enrich_row(
        self,
        base: dict[str, Any],
        *,
        service_label: str,
        family_key: str,
        family_label: str,
        entitled: dict[str, Any] | None,
        panel: PanelResult | None,
    ) -> dict[str, Any]:
        product_names = list((entitled or {}).get("product_names") or [])
        has_infra = bool(base.get("has_infra_source"))
        infra_binding = "bound" if has_infra else "crm_only"
        row = {
            **base,
            "service_label": service_label,
            "family": family_key,
            "family_label": family_label,
            "label": service_label,
            "crm_product_names": product_names,
            "crm_products_summary": _crm_product_names_summary(product_names),
            "infra_binding": infra_binding,
            "computation_mode": panel.computation_mode if panel else None,
        }
        return row

    def _build_panel_row(
        self,
        panel: PanelResult,
        entitled: dict[str, Any] | None,
        *,
        panel_defs: dict[str, dict[str, Any]],
        service_pages: dict[str, dict[str, Any]],
        under_pct: float,
        over_pct: float,
    ) -> dict[str, Any]:
        crm_sold = float((entitled or {}).get("entitled_qty") or 0.0)
        crm_sold_tl = float((entitled or {}).get("entitled_amount_tl") or 0.0)
        used = float(panel.allocated or 0.0)
        sellable = float(panel.sellable_constrained or 0.0)
        total = float(panel.total or 0.0) if panel.has_infra_source else None
        used_out = used if panel.has_infra_source else None
        sellable_out = sellable if panel.has_infra_source else None
        free_out = max(float(total or 0) - used, 0.0) if panel.has_infra_source and total is not None else None
        status = panel_inventory_status(
            crm_sold_qty=crm_sold,
            used_qty=used if panel.has_infra_source else 0.0,
            has_infra_source=panel.has_infra_source,
            under_pct=under_pct,
            over_pct=over_pct,
        )
        delta = (used - crm_sold) if panel.has_infra_source else None
        overage = max(0.0, used - crm_sold) if panel.has_infra_source else 0.0
        service_label, family_key, family_label, display_unit = self._resolve_labels(
            panel.panel_key,
            panel=panel,
            entitled=entitled,
            panel_defs=panel_defs,
            service_pages=service_pages,
        )
        base = {
            "panel_key": panel.panel_key,
            "label": service_label,
            "family": family_key,
            "resource_kind": panel.resource_kind,
            "display_unit": display_unit,
            "total": total,
            "crm_sold_qty": crm_sold,
            "crm_sold_tl": crm_sold_tl,
            "used_qty": used_out,
            "sellable_qty": sellable_out,
            "free_qty": free_out,
            "potential_tl": panel.potential_tl,
            "has_infra_source": panel.has_infra_source,
            "has_price": panel.has_price,
            "status": status,
            "delta_used_vs_crm": delta,
            "overage_qty": overage if panel.has_infra_source else 0.0,
            "efficiency_pct": round((used / crm_sold) * 100.0, 2) if crm_sold > 0 and panel.has_infra_source else None,
            "data_quality": _assess_data_quality(panel, crm_sold=crm_sold),
        }
        return self._enrich_row(
            base,
            service_label=service_label,
            family_key=family_key,
            family_label=family_label,
            entitled=entitled,
            panel=panel,
        )

    def _build_entitled_only_row(
        self,
        panel_key: str,
        bucket: dict[str, Any],
        *,
        panel_defs: dict[str, dict[str, Any]],
        service_pages: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        service_label, family_key, family_label, display_unit = self._resolve_labels(
            panel_key,
            panel=None,
            entitled=bucket,
            panel_defs=panel_defs,
            service_pages=service_pages,
        )
        base = {
            "panel_key": panel_key,
            "label": service_label,
            "family": family_key,
            "resource_kind": (panel_defs.get(panel_key) or {}).get("resource_kind") or "other",
            "display_unit": display_unit,
            "total": None,
            "crm_sold_qty": float(bucket.get("entitled_qty") or 0.0),
            "crm_sold_tl": float(bucket.get("entitled_amount_tl") or 0.0),
            "used_qty": None,
            "sellable_qty": None,
            "free_qty": None,
            "potential_tl": 0.0,
            "has_infra_source": False,
            "has_price": False,
            "status": "crm_only",
            "delta_used_vs_crm": None,
            "overage_qty": 0.0,
            "efficiency_pct": None,
        }
        return self._enrich_row(
            base,
            service_label=service_label,
            family_key=family_key,
            family_label=family_label,
            entitled=bucket,
            panel=None,
        )

    def compute_inventory_overview(
        self,
        dc_code: str = "*",
        *,
        force_recompute: bool = False,
    ) -> dict[str, Any]:
        cache_key = f"{_INVENTORY_REDIS_PREFIX}{dc_code or '*'}"
        if not force_recompute and self._crm_redis is not None:
            try:
                raw = self._crm_redis.get(cache_key)
                if raw:
                    return json.loads(raw)
            except Exception:  # noqa: BLE001
                logger.debug("inventory overview cache read failed", exc_info=True)

        calc = self._config.get_calc_dict() if self._config else {}
        under_pct = float(calc.get("efficiency.under_pct", 80.0))
        over_pct = float(calc.get("efficiency.over_pct", 110.0))

        panel_defs = self._load_panel_defs()
        service_pages = self._load_service_pages()
        panels = self._load_sellable_panels(dc_code or "*", force_recompute=force_recompute)
        mapping = self._load_product_mapping()
        panel_units = self._panel_unit_index(panels)

        entitled_raw = self._sales._run_query(sq.SALES_ENTITLED_RAW_GLOBAL, ())
        entitled_by_panel = aggregate_entitled_by_panel_key(
            entitled_raw, mapping, panel_units=panel_units
        )

        panel_rows: list[dict[str, Any]] = []
        crm_only_panels: list[dict[str, Any]] = []
        seen_panels: set[str] = set()

        for panel in panels:
            seen_panels.add(panel.panel_key)
            row = self._build_panel_row(
                panel,
                entitled_by_panel.get(panel.panel_key),
                panel_defs=panel_defs,
                service_pages=service_pages,
                under_pct=under_pct,
                over_pct=over_pct,
            )
            panel_rows.append(row)
            if row.get("infra_binding") == "crm_only":
                crm_only_panels.append(row)

        for panel_key, bucket in entitled_by_panel.items():
            if panel_key in seen_panels:
                continue
            row = self._build_entitled_only_row(
                panel_key,
                bucket,
                panel_defs=panel_defs,
                service_pages=service_pages,
            )
            panel_rows.append(row)
            crm_only_panels.append(row)

        panel_rows.sort(key=lambda r: (-float(r.get("crm_sold_tl") or 0), r.get("service_label") or ""))

        families_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in panel_rows:
            if row.get("infra_binding") == "crm_only":
                continue
            families_map[str(row.get("family") or "other")].append(row)

        families_out: list[dict[str, Any]] = []
        for family_key, rows in families_map.items():
            family_label = rows[0].get("family_label") or family_key if rows else family_key
            rows_sorted = sorted(rows, key=lambda r: r.get("service_label") or "")
            families_out.append({
                "family": family_key,
                "label": family_label,
                "family_label": family_label,
                "dc_code": dc_code or "*",
                "panels": rows_sorted,
                "panel_count": len(rows_sorted),
                "has_infra": any(r.get("has_infra_source") for r in rows_sorted),
            })
        families_out.sort(key=lambda f: (f.get("family_label") or f.get("family") or "").lower())

        mapped_ids = self._mapped_product_ids(mapping)
        bind_ids = mapped_ids if mapped_ids else ["__none__"]
        unmapped_products = self._sales._run_query(sq.UNMAPPED_ENTITLED_PRODUCTS, (bind_ids,))

        infra_panels = [r for r in panel_rows if r.get("has_infra_source")]
        overage_count = sum(1 for r in infra_panels if r.get("status") == "over")
        unsold_count = sum(1 for r in infra_panels if r.get("status") == "unsold_usage")
        crm_entitled_tl = sum(float(r.get("crm_sold_tl") or 0) for r in panel_rows)
        unmapped_count = self._sellable._count_unmapped_products()

        summary = {
            "dc_code": dc_code or "*",
            "infra_panel_count": len(infra_panels),
            "panel_count": len(panel_rows),
            "crm_only_count": len(crm_only_panels),
            "crm_entitled_tl": crm_entitled_tl,
            "unmapped_product_count": unmapped_count,
            "unmapped_entitled_count": len(unmapped_products),
            "overage_panel_count": overage_count,
            "unsold_usage_count": unsold_count,
            "total_potential_tl": sum(float(r.get("potential_tl") or 0) for r in panel_rows),
            "note": (
                "Capacity units are heterogeneous across panels; compare quantities in the service list."
                + (
                    " Global view sums DC-scoped infra totals across bound DCs, then "
                    "recomputes sellable per family; global-only panels (e.g. NetBackup) "
                    "are counted once."
                    if (dc_code or "*") == "*"
                    else ""
                )
            ),
        }

        payload = {
            "dc_code": dc_code or "*",
            "summary": summary,
            "families": families_out,
            "panels": panel_rows,
            "crm_only_panels": sorted(
                crm_only_panels,
                key=lambda r: r.get("service_label") or r.get("panel_key") or "",
            ),
            "unmapped_products": unmapped_products,
        }

        if self._crm_redis is not None:
            try:
                self._crm_redis.setex(
                    cache_key,
                    int(_INVENTORY_CACHE_TTL_SEC),
                    json.dumps(payload, default=str),
                )
            except Exception:  # noqa: BLE001
                logger.debug("inventory overview cache write failed", exc_info=True)

        return payload
