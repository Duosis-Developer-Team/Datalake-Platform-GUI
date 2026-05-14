"""
Phase 0 — Live schema inspection for backup job tables.

Bu test mock değildir. Bulutlake'e gerçek bağlanır ve raw_veeam_*, raw_zerto_*,
raw_netbackup_* tablolarının varlığını + kolon yapısını + örnek satırlarını
dökerek backup_jobs_schema.md raporunu üretir. DB erişilemezse testler skip olur.

Çalıştırma:
    docker compose run --rm datacenter-api pytest \
        tests/test_backup_jobs_schema.py -s -v
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

import pytest

from app.services.dc_service import DatabaseService


CANDIDATE_TABLES = [
    # Veeam — job-level
    "raw_veeam_jobs_states",
    "raw_veeam_sessions",
    # Zerto — actual table names (replication group / VM level)
    "raw_zerto_vpg_metrics",
    "raw_zerto_vm_metrics",
    "raw_zerto_alert_metrics",
    # NetBackup — actual table name
    "raw_netbackup_jobs_metrics",
]

LIKE_PATTERNS = ("raw_veeam_%", "raw_zerto_%", "raw_netbackup_%")

REPORT_PATH = Path(os.getenv("BACKUP_SCHEMA_REPORT", str(Path(__file__).resolve().parent / "backup_jobs_schema.md")))


@pytest.fixture(scope="module")
def db():
    svc = DatabaseService()
    if svc._pool is None:
        pytest.skip("Bulutlake DB is unreachable from this environment.")
    return svc


@pytest.fixture(scope="module")
def report_lines() -> list[str]:
    lines: list[str] = [
        "# Backup Job Tables — Live Schema Inspection",
        "",
        "Bu rapor `tests/test_backup_jobs_schema.py` koşturulduğunda otomatik üretilir.",
        f"Üretildiği yer: `{REPORT_PATH.relative_to(REPORT_PATH.parents[2])}`",
        "",
    ]
    yield lines
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n[Phase 0] Rapor yazıldı: {REPORT_PATH}")


def _fetch_all(db: DatabaseService, sql: str, params: tuple | None = None) -> list[tuple]:
    with db._get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def _print_section(title: str, rows: Iterable, lines: list[str]) -> None:
    print(f"\n=== {title} ===")
    lines.append("")
    lines.append(f"## {title}")
    lines.append("")
    materialized = list(rows)
    if not materialized:
        print("  (boş)")
        lines.append("_(boş)_")
        return
    for r in materialized:
        print(f"  {r}")
        lines.append(f"- `{r}`")


def test_list_backup_tables(db: DatabaseService, report_lines: list[str]) -> None:
    """Public schema altında raw_veeam_*, raw_zerto_*, raw_netbackup_* ile başlayan tüm tabloları listele."""
    rows = _fetch_all(
        db,
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND (table_name ILIKE %s OR table_name ILIKE %s OR table_name ILIKE %s)
        ORDER BY table_name
        """,
        LIKE_PATTERNS,
    )
    table_names = [r[0] for r in rows]
    _print_section("Mevcut backup tabloları (bulutlake.public)", table_names, report_lines)
    assert table_names, "raw_veeam_/raw_zerto_/raw_netbackup_ prefix'li hiç tablo yok — DB yanlış olabilir."


@pytest.mark.parametrize("table_name", CANDIDATE_TABLES)
def test_table_columns(db: DatabaseService, report_lines: list[str], table_name: str) -> None:
    """Her aday tablo için kolon listesi + tip. Tablo yoksa skip (informational)."""
    exists = _fetch_all(
        db,
        "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
        (table_name,),
    )
    if not exists:
        msg = f"`{table_name}` mevcut değil"
        print(f"\n[skip] {msg}")
        report_lines.append("")
        report_lines.append(f"## `{table_name}` — YOK")
        pytest.skip(msg)

    cols = _fetch_all(
        db,
        """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table_name,),
    )
    _print_section(f"`{table_name}` kolonları", cols, report_lines)
    assert cols, f"{table_name} kolon listesi boş döndü."


@pytest.mark.parametrize("table_name", CANDIDATE_TABLES)
def test_table_sample_rows(db: DatabaseService, report_lines: list[str], table_name: str) -> None:
    """Her aday tablodan en yeni 3 satır (status enum'unu, job_type/policy_type'ı görmek için)."""
    exists = _fetch_all(
        db,
        "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
        (table_name,),
    )
    if not exists:
        pytest.skip(f"`{table_name}` mevcut değil")

    try:
        rows = _fetch_all(db, f"SELECT * FROM public.{table_name} LIMIT 3")
    except Exception as exc:
        msg = f"`{table_name}` SELECT hatası: {exc}"
        print(f"\n[warn] {msg}")
        report_lines.append("")
        report_lines.append(f"## `{table_name}` örnek satırlar — HATA")
        report_lines.append(f"`{exc}`")
        pytest.skip(msg)

    _print_section(f"`{table_name}` örnek 3 satır", rows, report_lines)


@pytest.mark.parametrize(
    "table_name,status_col,time_col",
    [
        ("raw_veeam_jobs_states", "last_result", "last_run"),
        ("raw_veeam_jobs_states", "status", "collection_time"),
        ("raw_veeam_sessions", "result_result", "creation_time"),
        ("raw_zerto_vpg_metrics", "status", "collection_timestamp"),
        ("raw_netbackup_jobs_metrics", "status", "collection_timestamp"),
    ],
)
def test_status_distribution_last_30d(
    db: DatabaseService,
    report_lines: list[str],
    table_name: str,
    status_col: str,
    time_col: str,
) -> None:
    """
    Son 30 günde status değerlerinin dağılımı.
    Eğer tablo / kolon ismi tahminden farklıysa skip — Phase 1'de düzeltilir.
    """
    exists = _fetch_all(
        db,
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s
        """,
        (table_name,),
    )
    if not exists:
        pytest.skip(f"`{table_name}` mevcut değil")
    columns = {r[0] for r in exists}
    if status_col not in columns or time_col not in columns:
        msg = (
            f"`{table_name}` için tahmin edilen kolon yok "
            f"(status='{status_col}', time='{time_col}'); mevcut kolonlar: {sorted(columns)}"
        )
        print(f"\n[skip] {msg}")
        report_lines.append("")
        report_lines.append(f"## `{table_name}` status dağılımı — SKIP")
        report_lines.append(msg)
        pytest.skip(msg)

    rows = _fetch_all(
        db,
        f"""
        SELECT {status_col}, COUNT(*)
        FROM public.{table_name}
        WHERE {time_col} >= NOW() - INTERVAL '30 days'
        GROUP BY 1
        ORDER BY 2 DESC
        """,
    )
    _print_section(f"`{table_name}` status dağılımı (son 30 gün)", rows, report_lines)
