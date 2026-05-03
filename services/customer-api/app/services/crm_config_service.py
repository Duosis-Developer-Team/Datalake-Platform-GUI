"""CRM configuration service — thin wrapper around webui-db config tables.

Reads and writes thresholds, price overrides, and calc variables. All values
are stored as text in calc_config; this service casts them based on `value_type`.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.db.queries import crm_config as cq
from app.services.webui_db import WebuiPool

logger = logging.getLogger(__name__)


def _cast_value(value: str, value_type: str) -> Any:
    if value is None:
        return None
    if value_type == "float":
        try:
            return float(value)
        except ValueError:
            return None
    if value_type == "int":
        try:
            return int(value)
        except ValueError:
            return None
    if value_type == "bool":
        return str(value).strip().lower() in ("true", "1", "yes", "on")
    return value


class CrmConfigService:
    def __init__(self, webui: WebuiPool) -> None:
        self._webui = webui

    @property
    def is_available(self) -> bool:
        return self._webui is not None and self._webui.is_available

    # ---- thresholds -----------------------------------------------------

    def list_thresholds(self) -> List[Dict[str, Any]]:
        if not self.is_available:
            return []
        return self._webui.run_rows(cq.LIST_THRESHOLDS)

    def get_threshold_for(self, resource_type: str, dc_code: str = "*") -> Optional[float]:
        if not self.is_available:
            return None
        row = self._webui.run_one(cq.GET_THRESHOLD_FOR, (resource_type, dc_code))
        if not row:
            return None
        return float(row["sellable_limit_pct"])

    def upsert_threshold(
        self,
        resource_type: str,
        dc_code: str,
        sellable_limit_pct: float,
        notes: Optional[str],
        updated_by: Optional[str],
    ) -> int:
        return self._webui.execute(
            cq.UPSERT_THRESHOLD,
            (resource_type, dc_code or "*", sellable_limit_pct, notes, updated_by or "api"),
        )

    def delete_threshold(self, threshold_id: int) -> int:
        return self._webui.execute(cq.DELETE_THRESHOLD_BY_ID, (threshold_id,))

    # ---- price overrides ------------------------------------------------

    def list_price_overrides(self) -> List[Dict[str, Any]]:
        if not self.is_available:
            return []
        return self._webui.run_rows(cq.LIST_PRICE_OVERRIDES)

    def upsert_price_override(
        self,
        productid: str,
        product_name: Optional[str],
        unit_price_tl: float,
        resource_unit: Optional[str],
        currency: Optional[str],
        notes: Optional[str],
        updated_by: Optional[str],
    ) -> int:
        return self._webui.execute(
            cq.UPSERT_PRICE_OVERRIDE,
            (
                productid,
                product_name,
                float(unit_price_tl),
                resource_unit,
                currency or "TL",
                notes,
                updated_by or "api",
            ),
        )

    def delete_price_override(self, productid: str) -> int:
        return self._webui.execute(cq.DELETE_PRICE_OVERRIDE, (productid,))

    # ---- calc config ----------------------------------------------------

    def list_calc_config(self) -> List[Dict[str, Any]]:
        if not self.is_available:
            return []
        return self._webui.run_rows(cq.LIST_CALC_CONFIG)

    def get_calc_dict(self) -> Dict[str, Any]:
        """Return casted {config_key: typed_value}."""
        out: Dict[str, Any] = {}
        for row in self.list_calc_config():
            out[row["config_key"]] = _cast_value(row["config_value"], row.get("value_type") or "string")
        return out

    def upsert_calc_config(
        self,
        config_key: str,
        config_value: str,
        value_type: Optional[str],
        description: Optional[str],
        updated_by: Optional[str],
    ) -> int:
        return self._webui.execute(
            cq.UPSERT_CALC_CONFIG,
            (config_key, config_value, value_type or "string", description, updated_by or "api"),
        )
