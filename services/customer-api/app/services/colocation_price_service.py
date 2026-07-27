"""Resolve the colocation per-rack-U unit price and derive potential TL.

Precedence: operator override (webui-db) -> CRM list price (bulutlake) -> None.

An unresolved price is None, never 0.0. Zero renders as "0 TL" and reads as
"this rack space is worth nothing"; None renders as an em dash and reads as
"we do not know the price". A deliberate 0.0 override is still honoured as 0.0.
"""
from __future__ import annotations

import logging

from app.db.queries import colocation_price as q

logger = logging.getLogger(__name__)

# "Veri Merkezi Barindirma Hizmeti (U)" — the only CRM product priced per rack-U.
COLOCATION_PRODUCT_ID = "ee635018-5c6d-f011-b4cc-6045bd93381c"


def _override_price(webui) -> float | None:
    if webui is None or not getattr(webui, "is_available", False):
        return None
    try:
        rows = webui.run_rows(q.COLOCATION_PRICE_OVERRIDE, (COLOCATION_PRODUCT_ID,))
    except Exception as exc:  # noqa: BLE001
        logger.warning("colocation price override lookup failed: %s", exc)
        return None
    for r in rows or []:
        value = r.get("unit_price_tl") if isinstance(r, dict) else r[0]
        if value is not None:
            return float(value)
    return None


def _crm_price(cursor) -> float | None:
    try:
        cursor.execute(q.COLOCATION_CRM_UNIT_PRICE, (COLOCATION_PRODUCT_ID,))
        rows = cursor.fetchall()
    except Exception as exc:  # noqa: BLE001
        logger.warning("colocation CRM price lookup failed: %s", exc)
        return None
    for r in rows or []:
        value = r[0] if not isinstance(r, dict) else r.get("amount")
        if value is not None:
            return float(value)
    return None


def resolve_colocation_unit_price(cursor, webui) -> tuple[float | None, str]:
    """Return (unit_price_tl, source) with source in
    {"override", "crm", "unavailable"}."""
    override = _override_price(webui)
    if override is not None:
        return override, "override"
    crm = _crm_price(cursor)
    if crm is not None:
        return crm, "crm"
    return None, "unavailable"


def potential_tl(u, unit_price: float | None) -> float | None:
    """U count x unit price. None price propagates as None (unknown), while a
    missing/zero U count is a real zero."""
    if unit_price is None:
        return None
    return float(u or 0) * float(unit_price)
