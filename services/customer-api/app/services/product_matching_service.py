"""CRM product ↔ infrastructure matching for Inventory overview (ADR-0024 / ADR-0032 §41)."""
from __future__ import annotations

import logging
from typing import Any

from app.db.queries import crm_sales as sq
from shared.matching import load_product_matching_registry

logger = logging.getLogger(__name__)


class ProductMatchingService:
    """Join matching registry + full CRM catalog + sold + optional inventory panels.

    Checklist mode: every CRM product appears (matched or not). No default
    row drops for inventory_visible or registry status.
    """

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
        catalog_rows = self._load_all_products()
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

        infra_by_panel = self._load_infra_source_columns()
        products: list[dict[str, Any]] = []
        seen: set[str] = set()

        # 1) Registry entries (with or without sales)
        for pn, meta in sorted(registry.items(), key=lambda kv: kv[0]):
            sold = sold_by_pn.pop(pn, None)
            products.append(self._build_row(meta, sold, panels, infra_by_panel))
            seen.add(pn)

        # 2) Sold products not yet in registry
        for pn, sold in sorted(sold_by_pn.items(), key=lambda kv: -float(kv[1].get("sold_qty") or 0)):
            if pn in seen:
                continue
            products.append(
                self._build_row(
                    {
                        "productnumber": pn,
                        "name": str(sold.get("product_name") or pn),
                        "usage_source": "",
                        "matching_rule": "",
                        "match_status": "crm_only",
                        "panel_key": None,
                        "family": "",
                        "infra_tables": [],
                        "infra_columns": [],
                        "notes": "Sold SKU not yet in matching registry",
                    },
                    sold,
                    panels,
                    infra_by_panel,
                )
            )
            seen.add(pn)

        # 3) Full CRM catalog remainder (zero sold, unmatched) — checklist completeness
        for cat in catalog_rows:
            pn = str(cat.get("product_number") or cat.get("productnumber") or "").strip()
            if not pn or pn in seen:
                continue
            products.append(
                self._build_row(
                    {
                        "productnumber": pn,
                        "name": str(cat.get("product_name") or pn),
                        "usage_source": "",
                        "matching_rule": "",
                        "match_status": "crm_only",
                        "panel_key": None,
                        "family": "",
                        "infra_tables": [],
                        "infra_columns": [],
                        "notes": "CRM catalog product (no active sold qty / not in registry)",
                    },
                    {
                        "productnumber": pn,
                        "product_name": cat.get("product_name"),
                        "resource_unit": cat.get("default_unit") or "Adet",
                        "sold_qty": 0.0,
                        "sold_amount_tl": 0.0,
                    },
                    panels,
                    infra_by_panel,
                )
            )
            seen.add(pn)

        summary = self._summarize(products)
        return {
            "products": products,
            "summary": summary,
            "registry_version": 1,
            "methodology": "ADR-0024+ADR-0032-checklist",
        }

    def _load_sold_by_productnumber(self) -> list[dict[str, Any]]:
        try:
            return list(self._db._run_query(sq.SALES_SOLD_BY_PRODUCTNUMBER_GLOBAL, ()) or [])
        except Exception:
            logger.exception("SALES_SOLD_BY_PRODUCTNUMBER_GLOBAL failed")
            return []

    def _load_all_products(self) -> list[dict[str, Any]]:
        try:
            return list(self._db._run_query(sq.ALL_PRODUCTS, ()) or [])
        except Exception:
            logger.exception("ALL_PRODUCTS failed for product matching checklist")
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

    def _load_infra_source_columns(self) -> dict[str, dict[str, Any]]:
        """panel_key → tables/columns from gui_panel_infra_source (approved binding)."""
        webui = getattr(self._inventory, "_webui", None) if self._inventory else None
        if webui is None or not getattr(webui, "is_available", False):
            return {}
        try:
            rows = webui.run_rows(
                """
                SELECT panel_key, source_table, total_column,
                       allocated_table, allocated_column
                FROM   gui_panel_infra_source
                WHERE  source_table IS NOT NULL
                ORDER BY panel_key, (dc_code = '*') DESC
                """,
            )
        except Exception:
            logger.exception("gui_panel_infra_source load for product matching failed")
            return {}
        out: dict[str, dict[str, Any]] = {}
        for r in rows or []:
            key = str(r.get("panel_key") or "").strip()
            if not key or key in out:
                continue
            tables: list[str] = []
            columns: list[str] = []
            for t in (r.get("source_table"), r.get("allocated_table")):
                if t and str(t) not in tables:
                    tables.append(str(t))
            for c in (r.get("total_column"), r.get("allocated_column")):
                if c and str(c) not in columns:
                    columns.append(str(c))
            out[key] = {"infra_tables": tables, "infra_columns": columns}
        return out

    @staticmethod
    def _build_row(
        meta: dict[str, Any],
        sold: dict[str, Any] | None,
        panel_by_key: dict[str, dict[str, Any]],
        infra_by_panel: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        panel_key = meta.get("panel_key")
        panel = panel_by_key.get(panel_key) if panel_key else None
        sold_qty = float((sold or {}).get("sold_qty") or 0)
        sold_tl = float((sold or {}).get("sold_amount_tl") or 0)
        unit = str((sold or {}).get("resource_unit") or "")
        tables = list(meta.get("infra_tables") or [])
        columns = list(meta.get("infra_columns") or [])
        live = (infra_by_panel or {}).get(str(panel_key or ""))
        if live:
            for t in live.get("infra_tables") or []:
                if t not in tables:
                    tables.append(t)
            for c in live.get("infra_columns") or []:
                if c not in columns:
                    columns.append(c)
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
            "infra_tables": tables,
            "infra_columns": columns,
            "notes": meta.get("notes") or "",
            "in_registry": bool(
                meta.get("matching_rule") or meta.get("usage_source") or meta.get("panel_key")
            ),
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
            # Approved capacity match with live infra binding → green fill signal
            if (
                row["match_status"] == "capacity"
                and panel.get("has_infra_source")
                and (tables or columns)
            ):
                row["match_approved"] = True
            if not row["notes"] and row.get("match_approved"):
                via = row["usage_source"] or row["matching_rule"] or "infra binding"
                if tables and columns:
                    target = f"{tables[0]}.{columns[0]}"
                elif tables:
                    target = tables[0]
                else:
                    target = str(panel_key or "panel")
                row["notes"] = f"Matched via {via} → {target}"
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
            "crm_only_count": by_status.get("crm_only", 0),
        }
