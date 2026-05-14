"""
Unit tests for the sidebar 'Backup için ekstra' helpers — pure functions only.

İmport edilen yardımcılar app.py içinde tanımlı ama saf fonksiyon — Dash app
state'i veya scheduler tetiklemez. İzolasyonu doğrulamak için: bu modülden
yalnızca iki helper çıkar ve test eder; app-time-range akışına dokunmaz.
"""
from __future__ import annotations

from datetime import date, timedelta, timezone

import pytest


# app.py modülünü tam yüklemeden saf fonksiyonları import etmek zor
# (üst seviyede DB/scheduler dokunmaları var). Mock fixture'ı ile çevirmek
# yerine fonksiyonu doğrudan dosyadan exec ile çıkar — yan etkisi yok.
def _load_helpers():
    """app.py'den yalnızca saf helper fonksiyonları yükler."""
    import ast
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "app.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    keep = {"_compute_backup_tr", "_should_show_backup_section", "_extract_dc_id"}
    new_body = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in keep
    ]
    module = ast.Module(body=new_body, type_ignores=[])
    code = compile(module, str(src), "exec")
    ns: dict = {}
    exec(code, ns)
    return ns["_compute_backup_tr"], ns["_should_show_backup_section"], ns["_extract_dc_id"]


_compute_backup_tr, _should_show_backup_section, _extract_dc_id = _load_helpers()


# ---- _compute_backup_tr -----------------------------------------------------


@pytest.mark.parametrize(
    "preset,expected_days",
    [
        ("1m", 30),
        ("2m", 60),
        ("3m", 90),
        ("6m", 180),
        ("bogus", 30),  # fallback
    ],
)
def test_compute_backup_tr_days(preset: str, expected_days: int):
    tr = _compute_backup_tr(preset)
    start = date.fromisoformat(tr["start"])
    end = date.fromisoformat(tr["end"])
    assert (end - start).days == expected_days
    assert tr["preset"] == (preset if preset in ("1m", "2m", "3m", "6m") else "bogus")


def test_compute_backup_tr_custom_returns_empty_range():
    tr = _compute_backup_tr("custom")
    assert tr["preset"] == "custom"
    assert tr["start"] == ""
    assert tr["end"] == ""


def test_compute_backup_tr_end_is_today_utc():
    from datetime import datetime, timezone

    tr = _compute_backup_tr("1m")
    today_utc = datetime.now(timezone.utc).date()
    assert tr["end"] == today_utc.isoformat()


# ---- _should_show_backup_section --------------------------------------------


@pytest.mark.parametrize(
    "pathname,expected",
    [
        ("/datacenter/DC13", True),
        ("/datacenter/DC13/", True),
        ("/dc-detail/DC13", True),
        ("/", False),
        ("/datacenters", False),
        ("/customer-view", False),
        ("/global-view", False),
        ("/query-explorer", False),
        ("/settings/iam/users", False),
        (None, False),
        ("", False),
    ],
)
def test_should_show_backup_section(pathname, expected):
    assert _should_show_backup_section(pathname) is expected


# ---- _extract_dc_id ---------------------------------------------------------


@pytest.mark.parametrize(
    "pathname,expected",
    [
        ("/datacenter/DC13", "DC13"),
        ("/datacenter/DC13/", "DC13"),
        ("/dc-detail/UZ11", "UZ11"),
        ("/dc-detail/ICT21/", "ICT21"),
        ("/datacenter/", None),
        ("/datacenter", None),
        ("/home", None),
        ("/", None),
        ("", None),
        (None, None),
    ],
)
def test_extract_dc_id(pathname, expected):
    assert _extract_dc_id(pathname) == expected
