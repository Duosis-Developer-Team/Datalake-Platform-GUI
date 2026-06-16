#!/usr/bin/env python3
"""DC13 memory peak vs allocation verification (7d window)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import psycopg2
except ImportError:
    print("psycopg2 required", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[2]
LOCAL_ENV = ROOT / ".cursor" / "local-environment.local.json"


def _load_db():
    data = json.loads(LOCAL_ENV.read_text(encoding="utf-8"))
    pg = data["datalake_postgresql"]
    return dict(
        host=pg["host"],
        port=pg["port"],
        dbname=pg["database"],
        user=pg["user"],
        password=pg["password"],
        connect_timeout=15,
    )


def main() -> None:
    conn = psycopg2.connect(**_load_db())
    cur = conn.cursor()
    t0 = "2026-06-06 00:00:00+00"
    t1 = "2026-06-12 23:59:59+00"

    cur.execute(
        """
        SELECT ROUND(MAX(CASE WHEN memory_capacity_gb > 0
            THEN 100.0 * memory_used_gb / memory_capacity_gb END)::numeric, 1)
        FROM public.cluster_metrics
        WHERE datacenter ILIKE '%%DC13%%' AND cluster ILIKE '%%KM%%'
          AND timestamp BETWEEN %s AND %s
        """,
        (t0, t1),
    )
    old_max_pct = cur.fetchone()[0]

    cur.execute(
        """
        WITH ts_agg AS (
            SELECT timestamp,
                   SUM(memory_used_gb) AS used_gb,
                   SUM(memory_capacity_gb) AS cap_gb
            FROM public.cluster_metrics
            WHERE datacenter ILIKE '%%DC13%%' AND cluster ILIKE '%%KM%%'
              AND timestamp BETWEEN %s AND %s
            GROUP BY timestamp
        )
        SELECT ROUND(used_gb::numeric, 2), ROUND(cap_gb::numeric, 2),
               ROUND((100.0 * used_gb / NULLIF(cap_gb, 0))::numeric, 1)
        FROM ts_agg WHERE cap_gb > 0
        ORDER BY (used_gb / NULLIF(cap_gb, 0)) DESC, used_gb DESC
        LIMIT 1
        """,
        (t0, t1),
    )
    new_peak = cur.fetchone()

    cur.execute(
        """
        WITH latest AS (
            SELECT DISTINCT ON (vmname) total_memory_capacity_gb
            FROM public.vm_metrics
            WHERE datacenter ILIKE '%%DC13%%' AND cluster ILIKE '%%KM%%'
              AND LEFT(vmname, 1) <> '_'
              AND timestamp BETWEEN %s AND %s
            ORDER BY vmname, timestamp DESC
        )
        SELECT ROUND(COALESCE(SUM(total_memory_capacity_gb), 0)::numeric, 2),
               ROUND(COALESCE(SUM(total_memory_capacity_gb), 0) / 1024.0, 2)
        FROM latest
        """,
        (t0, t1),
    )
    alloc = cur.fetchone()
    conn.close()

    print(json.dumps({
        "window": {"start": t0, "end": t1},
        "old_row_max_pct": float(old_max_pct or 0),
        "new_peak_used_gb": float(new_peak[0] or 0) if new_peak else 0,
        "new_peak_cap_gb": float(new_peak[1] or 0) if new_peak else 0,
        "new_peak_pct": float(new_peak[2] or 0) if new_peak else 0,
        "alloc_gb_window": float(alloc[0] or 0) if alloc else 0,
        "alloc_tb_window": float(alloc[1] or 0) if alloc else 0,
    }, indent=2))


if __name__ == "__main__":
    main()
