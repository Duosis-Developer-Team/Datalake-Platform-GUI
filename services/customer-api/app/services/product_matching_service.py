"""CRM product ↔ infrastructure matching for Inventory overview (ADR-0024)."""
from __future__ import annotations

import logging
from typing import Any

from app.db.queries import crm_sales as sq
from shared.matching import load_product_matching_registry

logger = logging.getLogger(__name__)


class ProductMatchingService:
    """Join matching registry + global CRM sold + optional inventory panel totals."""

    def __init__(self, customer_svc: Any, inventory_svc: Any | None = None):
        self._db = customer_svc
        self._inventory = inventory_svc

    def is_available(self) -> bool:
        return bool(getattr(self._db, "_pool", None))

    def compute_product_matching(
        self,
        *,
        force_recompute: bool = False,
        panel_by_key: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        registry = load_product_matching_registry()
        sold_rows = self._load_sold_by_productnumber()
        sold_by_pn: dict[str, dict[str, Any]] = {}
        for row in sold_rows:
            pn = str(row.get("productnumber") or "").strip()
            if not pn:
                continue
            prev = sold_by_pn.get(pn)
            if prev is None:
                sold_by_pn[pn] = dict(row)
            else:
                prev["sold_qty"] = float(prev.get("sold_qty") or 0) + float(row.get("sold_qty") or 0)
                prev["sold_amount_tl"] = float(prev.get("sold_amount_tl") or 0) + float(
                    row.get("sold_amount_tl") or 0
                )

        panels = panel_by_key if panel_by_key is not None else self._panel_lookup(
            force_recompute=force_recompute
        )

        products: list[dict[str, Any]] = []
        # Registry entries (with or without sales)
        for pn, meta in sorted(registry.items(), key=lambda kv: kv[0]):
            sold = sold_by_pn.pop(pn, None)
            products.append(self._build_row(meta, sold, panels))

        # Sold products not yet in registry
        for pn, sold in sorted(sold_by_pn.items(), key=lambda kv: -float(kv[1].get("sold_qty") or 0)):
            products.append(
                self._build_row(
                    {
                        "productnumber": pn,
                        "name": str(sold.get("product_name") or pn),
                        "usage_source": "",
                        "matching_rule": "",
                        "match_status": "documented",
                        "panel_key": None,
                        "family": "",
                        "infra_tables": [],
                        "notes": "Sold SKU not yet in matching registry",
                    },
                    sold,
                    panels,
                )
            )

        summary = self._summarize(products)
        return {
            "products": products,
            "summary": summary,
            "registry_version": 1,
            "methodology": "ADR-0024",
        }

    def _load_sold_by_productnumber(self) -> list[dict[str, Any]]:
        try:
            return list(self._db._run_query(sq.SALES_SOLD_BY_PRODUCTNUMBER_GLOBAL) or [])
        except Exception:
            logger.exception("SALES_SOLD_BY_PRODUCTNUMBER_GLOBAL failed")
            return []

    def _panel_lookup(self, *, force_recompute: bool) -> dict[str, dict[str, Any]]:
        if self._inventory is None or not self._inventory.is_available():
            return {}
        try:
            overview = self._inventory.compute_inventory_overview(
                dc_code="*",
                force_recompute=force_recompute,
            )
        except Exception:
            logger.exception("inventory overview for product matching failed")
            return {}
        out: dict[str, dict[str, Any]] = {}
        for row in overview.get("panels") or []:
            key = str(row.get("panel_key") or "").strip()
            if key:
                out[key] = row
        return out

    @staticmethod
    def _build_row(
        meta: dict[str, Any],
        sold: dict[str, Any] | None,
        panel_by_key: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        panel_key = meta.get("panel_key")
        panel = panel_by_key.get(panel_key) if panel_key else None
        sold_qty = float((sold or {}).get("sold_qty") or 0)
        sold_tl = float((sold or {}).get("sold_amount_tl") or 0)
        unit = str((sold or {}).get("resource_unit") or "")
        row: dict[str, Any] = {
            "productnumber": meta["productnumber"],
            "product_name": meta.get("name") or (sold or {}).get("product_name") or meta["productnumber"],
            "resource_unit": unit,
            "crm_sold_qty": sold_qty,
            "crm_sold_tl": sold_tl,
            "usage_source": meta.get("usage_source") or "",
            "matching_rule": meta.get("matching_rule") or "",
            "match_status": meta.get("match_status") or "documented",
            "panel_key": panel_key,
            "family": meta.get("family") or "",
            "infra_tables": list(meta.get("infra_tables") or []),
            "notes": meta.get("notes") or "",
            "in_registry": bool(meta.get("matching_rule") or meta.get("usage_source") or meta.get("panel_key")),
            "infra_total": None,
            "infra_used": None,
            "infra_free": None,
            "panel_status": None,
        }
        if panel:
            row["infra_total"] = panel.get("total")
            row["infra_used"] = panel.get("used_qty")
            row["infra_free"] = panel.get("free_qty")
            row["panel_status"] = panel.get("status")
            if not row["resource_unit"]:
                row["resource_unit"] = str(panel.get("display_unit") or "")
        return row

    @staticmethod
    def _summarize(products: list[dict[str, Any]]) -> dict[str, Any]:
        by_status: dict[str, int] = {}
        with_sold = 0
        for p in products:
            st = str(p.get("match_status") or "documented")
            by_status[st] = by_status.get(st, 0) + 1
            if float(p.get("crm_sold_qty") or 0) > 0:
                with_sold += 1
        return {
            "product_count": len(products),
            "with_sold_count": with_sold,
            "by_status": by_status,
            "capacity_count": by_status.get("capacity", 0),
            "documented_count": by_status.get("documented", 0),
            "customer_phase_count": by_status.get("sold_noted_customer_phase", 0),
        }
