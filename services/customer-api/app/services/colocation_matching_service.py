"""Assemble the colocation payload for the DC 'Kolokasyon' tab: per-DC U
aggregate + per-customer footprint (device tenant -> CRM account)."""
from __future__ import annotations

import logging

from shared.colocation.occupancy import occupancy_rows, aggregate_by_dc
from shared.colocation.matching import build_customer_footprint
from app.db.queries import service_mapping as sm

logger = logging.getLogger(__name__)


class ColocationMatchingService:
    def __init__(self, customer_service, webui):
        self._svc = customer_service
        self._webui = webui

    def _alias_index(self) -> dict:
        """{lowercased tenant string -> {crm_accountid, crm_account_name}} from
        gui_crm_customer_alias, indexed by netbox_musteri_value AND account name."""
        index: dict = {}
        if self._webui is None or not getattr(self._webui, "is_available", False):
            return index
        try:
            rows = self._webui.run_rows(sm.GET_ALL_ALIASES, ())
        except Exception as exc:  # noqa: BLE001
            logger.warning("alias index load failed: %s", exc)
            return index
        for r in rows or []:
            payload = {
                "crm_accountid": r.get("crm_accountid"),
                "crm_account_name": r.get("crm_account_name"),
            }
            for key in (r.get("netbox_musteri_value"), r.get("crm_account_name"),
                        r.get("canonical_customer_key")):
                if key and str(key).strip():
                    index.setdefault(str(key).strip().lower(), payload)
        return index

    def get_colocation(self, dc_code: str) -> dict:
        pattern = None if not dc_code or dc_code == "*" else f"%{dc_code.strip()}%"
        try:
            with self._svc._get_connection() as conn:
                with conn.cursor() as cur:
                    rows = occupancy_rows(cur, dc_pattern=pattern)
        except Exception as exc:  # noqa: BLE001
            logger.error("colocation occupancy query failed for %s: %s", dc_code, exc)
            rows = []
        agg_by_dc = aggregate_by_dc(rows)
        aggregate = {"total_u": 0, "used_u": 0, "free_u": 0, "rack_count": 0}
        for a in agg_by_dc.values():
            for k in aggregate:
                aggregate[k] += a[k]
        customers = build_customer_footprint(rows, self._alias_index())
        return {"aggregate": aggregate, "customers": customers, "racks": rows}
