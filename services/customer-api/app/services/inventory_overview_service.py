"""Global CRM inventory overview — merges sellable infra panels with CRM entitled sales."""
from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from typing import Any

from app.db.queries import crm_sales as sq
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

    def _mapped_product_ids(self, mapping: dict[str, dict[str, Any]]) -> list[str]:
        return [
            pid
            for pid, row in mapping.items()
            if (row.get("source") or "") != "unmatched" and row.get("category_code")
        ]

    def _panel_unit_index(self, panels: list[PanelResult]) -> dict[str, str]:
        return {p.panel_key: p.display_unit for p in panels if p.panel_key}

    def _build_panel_row(
        self,
        panel: PanelResult,
        entitled: dict[str, Any] | None,
        *,
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
        status = panel_inventory_status(
            crm_sold_qty=crm_sold,
            used_qty=used if panel.has_infra_source else 0.0,
            has_infra_source=panel.has_infra_source,
            under_pct=under_pct,
            over_pct=over_pct,
        )
        delta = (used - crm_sold) if panel.has_infra_source else None
        overage = max(0.0, used - crm_sold) if panel.has_infra_source else 0.0
        return {
            "panel_key": panel.panel_key,
            "label": panel.label,
            "family": panel.family,
            "resource_kind": panel.resource_kind,
            "display_unit": panel.display_unit,
            "total": total,
            "crm_sold_qty": crm_sold,
            "crm_sold_tl": crm_sold_tl,
            "used_qty": used_out,
            "sellable_qty": sellable_out,
            "potential_tl": panel.potential_tl,
            "has_infra_source": panel.has_infra_source,
            "has_price": panel.has_price,
            "status": status,
            "delta_used_vs_crm": delta,
            "overage_qty": overage if panel.has_infra_source else 0.0,
            "efficiency_pct": round((used / crm_sold) * 100.0, 2) if crm_sold > 0 and panel.has_infra_source else None,
        }

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

        panels = self._sellable.compute_all_panels(dc_code=dc_code or "*")
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
                under_pct=under_pct,
                over_pct=over_pct,
            )
            panel_rows.append(row)
            if row["status"] == "crm_only":
                crm_only_panels.append(row)

        for panel_key, bucket in entitled_by_panel.items():
            if panel_key in seen_panels:
                continue
            row = {
                "panel_key": panel_key,
                "label": bucket.get("category_label") or panel_key,
                "family": panel_key.split("_")[0] if "_" in panel_key else "other",
                "resource_kind": "other",
                "display_unit": bucket.get("resource_unit") or "Adet",
                "total": None,
                "crm_sold_qty": float(bucket.get("entitled_qty") or 0.0),
                "crm_sold_tl": float(bucket.get("entitled_amount_tl") or 0.0),
                "used_qty": None,
                "sellable_qty": None,
                "potential_tl": 0.0,
                "has_infra_source": False,
                "has_price": False,
                "status": "crm_only",
                "delta_used_vs_crm": None,
                "overage_qty": 0.0,
                "efficiency_pct": None,
            }
            panel_rows.append(row)
            crm_only_panels.append(row)

        panel_rows.sort(key=lambda r: (-float(r.get("crm_sold_tl") or 0), r.get("panel_key") or ""))

        families_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in panel_rows:
            families_map[str(row.get("family") or "other")].append(row)

        families_out: list[dict[str, Any]] = []
        for family, rows in families_map.items():
            label = rows[0].get("label", "").split(" — ")[0] if rows else family
            crm_by_kind: dict[str, float] = defaultdict(float)
            used_by_kind: dict[str, float] = defaultdict(float)
            sellable_by_kind: dict[str, float] = defaultdict(float)
            for r in rows:
                kind = str(r.get("resource_kind") or "other")
                crm_by_kind[kind] += float(r.get("crm_sold_qty") or 0.0)
                if r.get("used_qty") is not None:
                    used_by_kind[kind] += float(r.get("used_qty") or 0.0)
                if r.get("sellable_qty") is not None:
                    sellable_by_kind[kind] += float(r.get("sellable_qty") or 0.0)
            families_out.append({
                "family": family,
                "label": label or family,
                "dc_code": dc_code or "*",
                "crm_sold_by_kind": dict(crm_by_kind),
                "used_by_kind": dict(used_by_kind),
                "sellable_by_kind": dict(sellable_by_kind),
                "panels": rows,
            })
        families_out.sort(key=lambda f: -sum(float(p.get("crm_sold_tl") or 0) for p in f.get("panels") or []))

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
            "note": "Capacity units are heterogeneous across panels; compare quantities in the panel table.",
        }

        payload = {
            "dc_code": dc_code or "*",
            "summary": summary,
            "families": families_out,
            "panels": panel_rows,
            "crm_only_panels": crm_only_panels,
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
