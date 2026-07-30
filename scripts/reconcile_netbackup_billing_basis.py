#!/usr/bin/env python3
"""NetBackup billing-basis validation (TASK-B1 / K-01 dual-basis check).

Reads DB credentials from env or optional JSON path. Never prints passwords.
Writes markdown report under task/GUI/reports/.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "task" / "GUI" / "reports"
REPORT_PATH = REPORT_DIR / "netbackup-fatura-tabani-mutabakat.md"


def _conn_params() -> dict:
    host = os.environ.get("DATALAKE_DB_HOST", "10.134.16.6")
    port = int(os.environ.get("DATALAKE_DB_PORT", "5000"))
    db = os.environ.get("DATALAKE_DB_NAME", "bulutlake")
    user = os.environ.get("DATALAKE_DB_USER", "bulutlake")
    password = os.environ.get("DATALAKE_DB_PASSWORD", "")
    cfg = os.environ.get("LOCAL_ENV_JSON")
    if not password and cfg and Path(cfg).is_file():
        data = json.loads(Path(cfg).read_text(encoding="utf-8"))
        pg = data.get("datalake_postgresql") or {}
        host = pg.get("host", host)
        port = int(pg.get("port", port))
        db = pg.get("database", db)
        user = pg.get("user", user)
        password = pg.get("password", "")
    if not password:
        raise SystemExit("Set DATALAKE_DB_PASSWORD or LOCAL_ENV_JSON")
    return {"host": host, "port": port, "dbname": db, "user": user, "password": password}


def _q(cur, sql: str) -> list[dict]:
    cur.execute(sql)
    return list(cur.fetchall())


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with psycopg2.connect(**_conn_params()) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            sold = _q(
                cur,
                """
                SELECT p.productnumber, p.name, d.uomid_name,
                       ROUND(SUM(d.quantity)::numeric, 1) AS sold_qty,
                       ROUND(SUM(d.extendedamount)::numeric, 0) AS sold_tl,
                       COUNT(DISTINCT so.customerid) AS customers
                FROM discovery_crm_salesorderdetails d
                JOIN discovery_crm_salesorders so ON so.salesorderid = d.salesorderid
                JOIN discovery_crm_products p ON p.productid = d.productid
                WHERE so.statecode = 0
                  AND p.productnumber IN ('000BLT-203', '000BLT-142')
                GROUP BY 1, 2, 3
                ORDER BY 1
                """,
            )
            jobs = _q(
                cur,
                """
                SELECT CASE WHEN upper(COALESCE(policytype,'')) = 'VMWARE'
                            THEN 'image' ELSE 'application' END AS category,
                       COUNT(*) AS jobs,
                       ROUND(SUM(kilobytestransferred)/1024.0/1024.0, 1) AS pre_dedup_gb,
                       ROUND(SUM(kilobytestransferred / NULLIF(dedupratio,0))/1024.0/1024.0, 1)
                         AS post_dedup_gb,
                       ROUND(AVG(NULLIF(dedupratio,0))::numeric, 2) AS avg_dedup
                FROM public.raw_netbackup_jobs_metrics
                WHERE starttime > now() - interval '30 days'
                  AND jobtype = 'BACKUP'
                  AND COALESCE(percentcomplete, 100) = 100
                GROUP BY 1
                ORDER BY 1
                """,
            )
            pools = _q(
                cur,
                """
                WITH latest AS (
                  SELECT DISTINCT ON (netbackup_host, name)
                         usablesizebytes, usedcapacitybytes, availablespacebytes
                  FROM public.raw_netbackup_disk_pools_metrics
                  ORDER BY netbackup_host, name, collection_timestamp DESC
                )
                SELECT ROUND(SUM(usablesizebytes)/1024.0^3, 1) AS usable_gb,
                       ROUND(SUM(usedcapacitybytes)/1024.0^3, 1) AS used_gb,
                       ROUND(SUM(availablespacebytes)/1024.0^3, 1) AS free_gb
                FROM latest
                """,
            )
            dq = _q(
                cur,
                """
                SELECT COUNT(*) FILTER (WHERE dedupratio IS NULL) AS null_dedup,
                       COUNT(*) FILTER (WHERE dedupratio = 0) AS zero_dedup,
                       COUNT(*) AS total_jobs,
                       ROUND(MIN(NULLIF(dedupratio,0))::numeric, 2) AS min_r,
                       ROUND(MAX(dedupratio)::numeric, 2) AS max_r,
                       ROUND(AVG(NULLIF(dedupratio,0))::numeric, 2) AS avg_r
                FROM public.raw_netbackup_jobs_metrics
                WHERE starttime > now() - interval '30 days'
                  AND jobtype = 'BACKUP'
                """,
            )

    lines = [
        "# NetBackup fatura tabanı mutabakatı",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Decision context (K-01 dual basis)",
        "",
        "- Customer / CRM sold semantics → **PreDedup**",
        "- DC / real cost → **PostDedup**",
        "- Inventory shows both",
        "",
        "## (A) CRM sold",
        "",
        "| SKU | Name | UOM | Sold | TL | Customers |",
        "|-----|------|-----|------|----|-----------|",
    ]
    for r in sold:
        lines.append(
            f"| {r['productnumber']} | {r['name']} | {r['uomid_name']} | "
            f"{r['sold_qty']} | {r['sold_tl']} | {r['customers']} |"
        )
    lines += [
        "",
        "## (B/C) Jobs 30d pre vs post (GiB as GB proxy)",
        "",
        "| Category | Jobs | PreDedup GB | PostDedup GB | Avg dedup |",
        "|----------|------|-------------|--------------|-----------|",
    ]
    pre_total = post_total = 0.0
    for r in jobs:
        pre_total += float(r["pre_dedup_gb"] or 0)
        post_total += float(r["post_dedup_gb"] or 0)
        lines.append(
            f"| {r['category']} | {r['jobs']} | {r['pre_dedup_gb']} | "
            f"{r['post_dedup_gb']} | {r['avg_dedup']} |"
        )
    pool = pools[0] if pools else {}
    used_pool = float(pool.get("used_gb") or 0)
    lines += [
        "",
        f"**Totals:** pre={pre_total} GB, post={post_total} GB",
        "",
        "## (D) Physical pools (latest)",
        "",
        f"- usable_gb={pool.get('usable_gb')}",
        f"- used_gb={pool.get('used_gb')}",
        f"- free_gb={pool.get('free_gb')}",
        "",
        f"**Post vs pool used delta:** post={post_total}, pool_used={used_pool}, "
        f"delta={round(post_total - used_pool, 1)}",
        "",
        "## (F) dedupratio DQ",
        "",
    ]
    if dq:
        d = dq[0]
        lines.append(
            f"- null={d['null_dedup']}, zero={d['zero_dedup']}, total={d['total_jobs']}, "
            f"min={d['min_r']}, max={d['max_r']}, avg={d['avg_r']}"
        )
    lines += [
        "",
        "## Recommendation",
        "",
        "Use **dual basis** (not single pick): PreDedup for sold/customer; "
        "PostDedup for cost. Expect post ≈ pool used when job window and pool "
        "freshness align; large gaps indicate DQ or window mismatch.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
