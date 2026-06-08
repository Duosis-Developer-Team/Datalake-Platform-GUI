"""NetBox/Loki visualization exclusion helpers (device role MVP)."""
from __future__ import annotations

import logging
import time
from typing import Any

from app.db.queries import netbox_config as nq

logger = logging.getLogger(__name__)

_SCOPE_CACHE: dict[str, tuple[float, set[str]]] = {}
_CACHE_TTL_SEC = 60.0


def _normalize_role(role: str | None) -> str:
    return (role or "").strip().casefold()


def is_role_excluded(role: str | None, excluded: set[str]) -> bool:
    if not excluded:
        return False
    key = _normalize_role(role)
    if not key:
        return False
    return key in excluded


def load_excluded_roles(webui: Any, scope: str) -> set[str]:
    """Load excluded device roles for a view scope from webui-db (short TTL cache)."""
    scope_key = (scope or "").strip().lower()
    if scope_key not in {"datacenter", "customer"}:
        return set()

    now = time.monotonic()
    cached = _SCOPE_CACHE.get(scope_key)
    if cached is not None and (now - cached[0]) < _CACHE_TTL_SEC:
        return cached[1]

    excluded: set[str] = set()
    if webui is not None and getattr(webui, "is_available", False):
        try:
            rows = webui.run_rows(nq.LIST_EXCLUDED_DEVICE_ROLES, (scope_key,))
            excluded = {_normalize_role(r.get("dimension_value")) for r in rows if r.get("dimension_value")}
            excluded.discard("")
        except Exception as exc:
            logger.warning("Failed to load NetBox viz exclusions for scope=%s: %s", scope_key, exc)

    _SCOPE_CACHE[scope_key] = (now, excluded)
    return excluded


def invalidate_exclusion_cache() -> None:
    _SCOPE_CACHE.clear()


def filter_devices_by_role_exclusion(
    devices: list[dict],
    excluded: set[str],
    *,
    role_key: str = "device_role_name",
) -> list[dict]:
    if not excluded:
        return devices
    return [d for d in devices if not is_role_excluded(d.get(role_key), excluded)]
