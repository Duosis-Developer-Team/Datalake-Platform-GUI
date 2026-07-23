"""Canonical colocation rack-occupancy computation — the single source of truth.

Imported by datacenter-api (endpoints) and customer-api (dc_hosting_u sellable)
so "used vs free U" can never diverge.

Verified read-only against bulutlake 2026-07-23: over_capacity = 0 across 234
racks (total 10,745 U / used 3,998 / free 6,747).

Data model (see the TASK-62 spec §5):
  * CURRENT tables only. The legacy loki_devices/loki_racks timeseries are stale
    (last collected 2026-04-12); discovery_* is the live snapshot.
  * device->rack scoped by (rack_name, site_name): rack names are non-unique
    (182 names / 234 racks) and the two NetBox snapshots use disjoint rack_id
    spaces (0 matches), so neither rack_id nor rack_name-alone is a safe key.
  * used_u = count of distinct FRONT-face U-slots occupied. A device at U=p with
    height h occupies [p .. p+h-1]; COUNT(DISTINCT u) over generate_series caps
    at capacity and absorbs chassis-child overlaps.
"""
from __future__ import annotations

from typing import Any, Sequence

# One row per rack. %(dc_pattern)s: a str glob (e.g. '%DC13%') or None for all.
OCCUPANCY_SQL = """
WITH dev_slots AS (
    SELECT d.rack_name,
           d.site_name,
           generate_series(
               floor(d.position)::int,
               floor(d.position)::int
                   + GREATEST(COALESCE(NULLIF(dt.u_height, 0), 1), 1)::int - 1
           ) AS u,
           d.tenant_name
    FROM discovery_netbox_inventory_device d
    JOIN loki_device_types dt ON dt.id = d.device_type_id
    WHERE d.position IS NOT NULL
      AND lower(coalesce(d.face_value, 'front')) IN ('front', '')
),
rack AS (
    SELECT r.id            AS rack_id,
           r.name          AS rack_name,
           r.u_height::int AS capacity_u,
           l.site_name     AS site_name,
           l.name          AS hall,
           COALESCE(l.parent_name, l.name) AS dc
    FROM discovery_loki_rack r
    LEFT JOIN discovery_loki_location l ON l.id::varchar = r.location_id
)
SELECT r.rack_id,
       r.rack_name,
       r.dc,
       r.hall,
       r.capacity_u,
       COUNT(DISTINCT s.u) FILTER (WHERE s.u BETWEEN 1 AND r.capacity_u) AS used_u,
       GREATEST(
           r.capacity_u
           - COUNT(DISTINCT s.u) FILTER (WHERE s.u BETWEEN 1 AND r.capacity_u),
           0
       ) AS free_u,
       ARRAY_AGG(DISTINCT s.tenant_name)
           FILTER (WHERE s.tenant_name IS NOT NULL AND btrim(s.tenant_name) <> '') AS tenants
FROM rack r
LEFT JOIN dev_slots s
    ON s.rack_name = r.rack_name
   AND COALESCE(s.site_name, '') = COALESCE(r.site_name, '')
WHERE (%(dc_pattern)s IS NULL OR COALESCE(r.dc, '') ILIKE %(dc_pattern)s)
GROUP BY r.rack_id, r.rack_name, r.dc, r.hall, r.capacity_u
ORDER BY r.dc, r.rack_name
"""

OCCUPANCY_COLUMNS = (
    "rack_id", "rack_name", "dc", "hall", "capacity_u", "used_u", "free_u", "tenants",
)

# Tenants that are Bulutistan's own infrastructure, not external colocation
# customers. Matched case-insensitively as a prefix. (Verified prod tenants:
# the "Bulutistan - *" buckets, "Bulut Broker", "CPE-Tenant", switch fabrics.)
INTERNAL_TENANT_PREFIXES = (
    "bulutistan", "bulut broker", "cpe-tenant", "dc11 arista",
)


def row_to_dict(row: Sequence[Any]) -> dict:
    """Map one OCCUPANCY_SQL row tuple to a dict with coerced numeric fields."""
    d = {col: (row[i] if i < len(row) else None) for i, col in enumerate(OCCUPANCY_COLUMNS)}
    d["capacity_u"] = int(d.get("capacity_u") or 0)
    d["used_u"] = int(d.get("used_u") or 0)
    d["free_u"] = int(d.get("free_u") or 0)
    d["tenants"] = list(d.get("tenants") or [])
    return d


def occupancy_rows(cursor, dc_pattern: str | None = None) -> list[dict]:
    """Execute OCCUPANCY_SQL on an open cursor and return per-rack dicts."""
    cursor.execute(OCCUPANCY_SQL, {"dc_pattern": dc_pattern})
    return [row_to_dict(r) for r in (cursor.fetchall() or [])]


def aggregate_by_dc(rows: Sequence[dict]) -> dict:
    """Roll per-rack rows up to per-DC totals."""
    out: dict = {}
    for r in rows:
        dc = r.get("dc") or "UNKNOWN"
        agg = out.setdefault(dc, {"total_u": 0, "used_u": 0, "free_u": 0, "rack_count": 0})
        agg["total_u"] += int(r.get("capacity_u") or 0)
        agg["used_u"] += int(r.get("used_u") or 0)
        agg["free_u"] += int(r.get("free_u") or 0)
        agg["rack_count"] += 1
    return out


def is_internal_tenant(name: str) -> bool:
    """True when the tenant is Bulutistan-internal (excluded from the customer view)."""
    key = (name or "").strip().lower()
    return any(key.startswith(p) for p in INTERNAL_TENANT_PREFIXES)
