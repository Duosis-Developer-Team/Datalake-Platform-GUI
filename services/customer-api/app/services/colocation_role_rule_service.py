"""Colocation sellable rack-role rules — webui-db CRUD + RoleRules loader."""
from __future__ import annotations

import logging
import time
from typing import Any, Mapping, Sequence

from shared.colocation.occupancy import role_catalog as _role_catalog
from shared.colocation.role_rules import DEFAULT_RULES, RoleRules
from app.db.queries import colocation_config as cq
from app.services.webui_db import WebuiPool

logger = logging.getLogger(__name__)

# load_rules() is called on the read path of every colocation/sellable
# request (its etag goes into the cache key), so it must not be a webui
# round-trip each time. 30s is short enough that an operator's save shows up
# on its own even if an explicit invalidate is missed, and long enough that a
# burst of requests costs one query.
_MEMO_TTL_SECONDS = 30.0


class ColocationRoleRuleService:
    def __init__(self, webui: WebuiPool, customer_service: Any = None) -> None:
        self._webui = webui
        self._svc = customer_service
        self._memo: tuple[float, RoleRules] | None = None

    @property
    def is_available(self) -> bool:
        return self._webui is not None and getattr(self._webui, "is_available", False)

    def list_rules(self) -> list[dict[str, Any]]:
        if not self.is_available:
            return []
        try:
            return self._webui.run_rows(cq.LIST_ROLE_RULES)
        except Exception as exc:  # noqa: BLE001
            logger.warning("colocation role rules load failed: %s", exc)
            return []

    def load_rules(self) -> RoleRules:
        """Current rule set, memoised for _MEMO_TTL_SECONDS.

        Returns DEFAULT_RULES when webui is unreachable or the table is empty
        -- never an empty rule set, which every consumer would read as
        "no role is configured, therefore everything is sellable".
        """
        now = time.monotonic()
        if self._memo is not None and now < self._memo[0]:
            return self._memo[1]
        if not self.is_available:
            return DEFAULT_RULES
        rules = RoleRules.from_rows(self.list_rules())
        self._memo = (now + _MEMO_TTL_SECONDS, rules)
        return rules

    def invalidate_memo(self) -> None:
        self._memo = None

    def save_rules(
        self,
        rules: Sequence[Mapping[str, Any]],
        *,
        notes: str | None = None,
        updated_by: str | None = None,
    ) -> RoleRules:
        """Write the FULL rule set (one row per role) and drop the memo.

        Full-set writes, not per-role: a partial write leaves roles the screen
        showed as "off" absent from the table, and an absent role reads back
        as sellable -- the saved state would not match what the operator saw.
        """
        if not self.is_available:
            raise RuntimeError("WebUI configuration DB not available")
        seen: set[str] = set()
        for item in rules or []:
            raw = item.get("role_id")
            key = "" if raw is None else str(raw).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            self._webui.execute(
                cq.UPSERT_ROLE_RULE,
                (key, bool(item.get("sellable")), notes, updated_by or "api"),
            )
        self.invalidate_memo()
        return self.load_rules()

    def role_catalog(self) -> list[dict[str, Any]]:
        """Live rack-role catalogue; empty list if the datalake is unreachable."""
        if self._svc is None:
            return []
        try:
            with self._svc._get_connection() as conn:
                with conn.cursor() as cur:
                    return _role_catalog(cur)
        except Exception as exc:  # noqa: BLE001
            logger.warning("loki role catalog query failed: %s", exc)
            return []


def get_role_rule_service(app) -> ColocationRoleRuleService:
    """App-scoped singleton, created on first use.

    Must be a singleton: the 30s memo lives on the instance, and
    ColocationMatchingService is built PER REQUEST
    (routers/colocation.py). A fresh rule service per request would mean a
    webui round-trip on every colocation call, which is the read path this
    memo exists to protect.
    """
    svc = getattr(app.state, "colocation_role_rules", None)
    if svc is None:
        svc = ColocationRoleRuleService(
            getattr(app.state, "webui", None), getattr(app.state, "db", None)
        )
        app.state.colocation_role_rules = svc
    return svc
