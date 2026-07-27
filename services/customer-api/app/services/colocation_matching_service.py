"""Assemble the colocation payload for the DC 'Colocation' tab: per-DC U
aggregate + per-customer footprint (device tenant -> CRM account)."""
from __future__ import annotations

import logging

from shared.colocation.occupancy import (
    INTERNAL_TENANT_PREFIXES,
    occupancy_rows,
    aggregate_by_dc,
    tenant_occupancy_rows,
    used_u_breakdown,
)
from shared.colocation.matching import build_customer_footprint, build_internal_footprint
from app.db.queries import service_mapping as sm
from app.services.colocation_price_service import (
    potential_tl,
    resolve_colocation_unit_price,
)

logger = logging.getLogger(__name__)

# Reserved account id the Administration "Internal (Bulutistan) source mappings"
# editor writes under. Mirrors INTERNAL_ACCOUNT_ID in the GUI editor.
INTERNAL_ACCOUNT_ID = "INTERNAL"


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

    def _internal_prefixes(self) -> tuple[str, ...]:
        """Bulutistan-internal tenant prefixes: the built-in seed unioned with the
        enabled Administration -> Internal (Bulutistan) source mappings.

        Before this existed the internal/external split ignored Administration
        entirely, so operator edits had no effect on the Colocation tab. Built-ins
        stay in the union so an empty or unreachable mapping table degrades to
        today's behaviour rather than reclassifying every internal rack as an
        external customer.
        """
        prefixes = list(INTERNAL_TENANT_PREFIXES)
        if self._webui is None or not getattr(self._webui, "is_available", False):
            return tuple(prefixes)
        try:
            rows = self._webui.run_rows(
                sm.LIST_SOURCE_MAPPINGS_FOR_ACCOUNT, (INTERNAL_ACCOUNT_ID,)
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("internal mapping load failed: %s", exc)
            return tuple(prefixes)
        for r in rows or []:
            if not r.get("enabled", True):
                continue
            value = (r.get("match_value") or "").strip().lower()
            if value and value not in prefixes:
                prefixes.append(value)
        return tuple(prefixes)

    def get_colocation(self, dc_code: str) -> dict:
        pattern = None if not dc_code or dc_code == "*" else f"%{dc_code.strip()}%"
        # Computed once, up front: _internal_prefixes() talks to webui, not the
        # datalake connection opened below, and is reused for the summary-bar
        # breakdown AND both footprint builders so all three agree on exactly
        # the same internal/external split.
        internal_prefixes = self._internal_prefixes()
        rows: list = []
        tenant_rows: list = []
        breakdown: dict = {}
        unit_price: float | None = None
        price_source = "unavailable"
        try:
            with self._svc._get_connection() as conn:
                with conn.cursor() as cur:
                    rows = occupancy_rows(cur, dc_pattern=pattern)
                    tenant_rows = tenant_occupancy_rows(cur, dc_pattern=pattern)
                    breakdown = used_u_breakdown(
                        cur, dc_pattern=pattern, internal_prefixes=internal_prefixes
                    )
                    unit_price, price_source = resolve_colocation_unit_price(
                        cur, self._webui
                    )
        except Exception as exc:  # noqa: BLE001
            logger.error("colocation occupancy query failed for %s: %s", dc_code, exc)
            rows = []
            tenant_rows = []
            breakdown = {}
            unit_price = None
            price_source = "unavailable"
        agg_by_dc = aggregate_by_dc(rows)
        aggregate = {"total_u": 0, "used_u": 0, "free_u": 0, "rack_count": 0}
        for a in agg_by_dc.values():
            for k in aggregate:
                aggregate[k] += a[k]
        aggregate.update({
            "external_u": int(breakdown.get("external_u") or 0),
            "internal_u": int(breakdown.get("internal_u") or 0),
            "untagged_u": int(breakdown.get("untagged_u") or 0),
            "external_customer_count": int(breakdown.get("external_customer_count") or 0),
            "unit_price_tl": unit_price,
            "price_source": price_source,
            "free_u_potential_tl": potential_tl(aggregate["free_u"], unit_price),
            "used_u_potential_tl": potential_tl(aggregate["used_u"], unit_price),
        })
        customers = build_customer_footprint(
            tenant_rows, self._alias_index(), internal_prefixes=internal_prefixes
        )
        internal = build_internal_footprint(
            tenant_rows, internal_prefixes=internal_prefixes
        )
        for row in customers:
            row["potential_tl"] = potential_tl(row.get("used_u"), unit_price)
        for row in internal:
            row["potential_tl"] = potential_tl(row.get("used_u"), unit_price)
        return {"aggregate": aggregate, "customers": customers, "internal": internal, "racks": rows}
