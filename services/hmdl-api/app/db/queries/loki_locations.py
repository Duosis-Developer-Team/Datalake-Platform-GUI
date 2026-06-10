"""Read root NetBox locations synced from Loki into public.loki_locations."""

from __future__ import annotations

from typing import Any

from app.db import pool

ROOT_LOCATIONS_SQL = """
SELECT DISTINCT ON (name)
    id,
    name,
    description,
    site_name,
    status_value
FROM public.loki_locations
WHERE parent_id IS NULL
  AND status_value = 'active'
ORDER BY name, collection_time DESC NULLS LAST
"""


def fetch_root_locations() -> list[dict[str, Any]]:
    """Return active top-level Loki locations (excludes DH and other child locations)."""
    rows = pool.fetch_all(ROOT_LOCATIONS_SQL)
    return [dict(r) for r in rows]
