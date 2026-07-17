#!/usr/bin/env python3
"""Read-only report: which alias rules change behaviour under the match fix?

Answers three questions before the fix reaches production:
  1. Which rules contain LIKE wildcards (_ or %) that are about to become literal?
     These match MORE rows today than they will afterwards.
  2. Which rules use `exact`? They are silently dropped today (the display-name
     fallback runs in their place) and start filtering once the fix ships.
  3. Which rules use a method that is invalid for their data source? These are
     the silent hole: the SQL path drops them, the classifier read them as
     `contains`. They must be corrected or deleted before the CHECK constraint
     added in migration 028 can be validated.

Usage:
    <venv>/bin/python scripts/alias_match_impact_report.py

Reads the same DB env vars customer-api uses. Runs SELECTs only — it never
writes, and it is safe to run against production.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import psycopg2.extras

from shared.customer import match

QUERY = """
SELECT crm_account_name, data_source, match_method, match_value, enabled
FROM gui_crm_customer_source_mapping
WHERE enabled = TRUE
ORDER BY crm_account_name, data_source, priority
"""


def dsn() -> str:
    return (
        f"host={os.environ.get('WEBUI_DB_HOST', os.environ.get('DB_HOST', 'localhost'))} "
        f"port={os.environ.get('WEBUI_DB_PORT', os.environ.get('DB_PORT', '5432'))} "
        f"dbname={os.environ.get('WEBUI_DB_NAME', os.environ.get('DB_NAME', 'webui'))} "
        f"user={os.environ.get('WEBUI_DB_USER', os.environ.get('DB_USER', 'postgres'))} "
        f"password={os.environ.get('WEBUI_DB_PASS', os.environ.get('DB_PASS', ''))}"
    )


def old_sql_pattern(method: str, value: str) -> str:
    """What the pattern looked like before the fix: no escaping, exact dropped."""
    cleaned = (value or "").strip()
    key = (method or "contains").strip().lower()
    if key == "exact":
        return "<dropped — fallback ran instead>"
    if key == "id_exact":
        return "<tenant id>"
    if key == "prefix":
        return f"{cleaned}%"
    if key == "suffix":
        return f"%{cleaned}"
    return f"%{cleaned}%"


def dump(title: str, rows: list, note: str) -> None:
    print("=" * 78)
    print(f"{title}: {len(rows)} rule(s)")
    print(note)
    print("=" * 78)
    for row in rows:
        before = old_sql_pattern(row["match_method"], row["match_value"])
        _kind, after = match.sql_pattern(row["match_method"], row["match_value"])
        print(f"  {str(row['crm_account_name'])[:28]:28s} {str(row['data_source'])[:20]:20s} "
              f"{str(row['match_method']):9s} {str(row['match_value'])[:24]}")
        print(f"      before: {before}")
        print(f"      after : {after!r}")
    if not rows:
        print("  (none)")
    print()


def main() -> int:
    conn = psycopg2.connect(dsn())
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(QUERY)
            rows = cur.fetchall()
    finally:
        conn.close()

    wildcard_rows = []
    exact_rows = []
    invalid_rows = []

    for row in rows:
        value = str(row["match_value"] or "")
        method = str(row["match_method"] or "")
        source = str(row["data_source"] or "")

        if ("_" in value or "%" in value) and method in match.TEXT_METHODS:
            wildcard_rows.append(row)
        if method == "exact":
            exact_rows.append(row)
        if not match.is_allowed(source, method):
            invalid_rows.append(row)

    print(f"\nTotal enabled rules: {len(rows)}\n")
    dump("WILDCARD -> LITERAL", wildcard_rows,
         "Today '_' matches any character. After the fix it is literal, so these\n"
         "match fewer rows — resources may leave a customer's view.")
    dump("EXACT (currently dropped)", exact_rows,
         "These do nothing today; the display-name fallback runs instead.\n"
         "After the fix they start filtering — usually adding correct data back.")
    dump("INVALID method for source", invalid_rows,
         "The silent hole: dropped by SQL, read as `contains` by the classifier.\n"
         "Fix or delete these, then VALIDATE the constraint from migration 028.")

    print("=" * 78)
    print(f"SUMMARY  wildcard={len(wildcard_rows)}  exact={len(exact_rows)}  "
          f"invalid={len(invalid_rows)}  total={len(rows)}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
