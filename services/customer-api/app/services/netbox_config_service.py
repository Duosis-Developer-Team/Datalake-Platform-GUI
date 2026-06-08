"""NetBox/Loki visualization exclusion config — webui-db CRUD."""
from __future__ import annotations

import logging
from typing import Any

from app.db.queries import netbox_config as nq
from app.services.webui_db import WebuiPool

logger = logging.getLogger(__name__)

VALID_SCOPES = frozenset({"datacenter", "customer"})
VALID_DIMENSIONS = frozenset({"device_role"})


class NetboxConfigService:
    def __init__(self, webui: WebuiPool) -> None:
        self._webui = webui

    @property
    def is_available(self) -> bool:
        return self._webui is not None and self._webui.is_available

    def list_exclusions(self) -> list[dict[str, Any]]:
        if not self.is_available:
            return []
        return self._webui.run_rows(nq.LIST_VIZ_EXCLUSIONS)

    def upsert_exclusion(
        self,
        *,
        view_scope: str,
        dimension: str,
        dimension_value: str,
        notes: str | None,
        updated_by: str | None,
    ) -> dict[str, Any]:
        scope = (view_scope or "").strip().lower()
        dim = (dimension or "device_role").strip().lower()
        value = (dimension_value or "").strip()
        if scope not in VALID_SCOPES:
            raise ValueError(f"view_scope must be one of {sorted(VALID_SCOPES)}")
        if dim not in VALID_DIMENSIONS:
            raise ValueError(f"dimension must be one of {sorted(VALID_DIMENSIONS)}")
        if not value:
            raise ValueError("dimension_value is required")

        self._webui.execute(
            nq.UPSERT_VIZ_EXCLUSION,
            (scope, dim, value, notes, updated_by or "api"),
        )
        return {"view_scope": scope, "dimension": dim, "dimension_value": value}

    def delete_exclusion(self, exclusion_id: int) -> int:
        return self._webui.execute(nq.DELETE_VIZ_EXCLUSION_BY_ID, (exclusion_id,))
