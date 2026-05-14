"""
Phase 1 tests for backup job statistics.

Karma test seti:
- Unit: status/granularity normalization helpers — DB gerekmez.
- Integration: gerçek bulutlake'e bağlanır; her vendor için service fonksiyonunu
  çağırır, response şeması ve aggregation tutarlılığını doğrular.

Çalıştırma:
    docker compose run --rm -v "$(pwd)/services/datacenter-api/tests:/app/tests" \
        datacenter-api pytest tests/test_backup_jobs.py -s -v
"""

from __future__ import annotations

import pytest

from app.services.dc_service import DatabaseService


# ---------------------------------------------------------------------------
# Unit tests — pure helpers (no DB)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "input_value,expected",
    [
        ("day", "day"),
        ("daily", "day"),
        ("week", "week"),
        ("weekly", "week"),
        ("month", "month"),
        ("monthly", "month"),
        (None, "day"),
        ("", "day"),
        ("bogus", "day"),
        ("DAILY", "day"),
    ],
)
def test_normalize_granularity(input_value, expected):
    assert DatabaseService._normalize_granularity(input_value) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Success", "success"),
        ("Failed", "failed"),
        ("Warning", "warning"),
        ("None", "running"),
        (None, "other"),
        ("", "other"),
        ("Anything", "other"),
    ],
)
def test_normalize_veeam_result(raw, expected):
    assert DatabaseService._normalize_veeam_result(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        (1, "success"),
        (2, "failed"),
        (3, "failed"),
        (0, "running"),
        (5, "running"),
        (4, "warning"),
        (None, "other"),
        ("not-int", "other"),
    ],
)
def test_normalize_zerto_status(raw, expected):
    assert DatabaseService._normalize_zerto_status(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        (0, "success"),
        (1, "warning"),
        (2, "failed"),
        (150, "failed"),
        (None, "other"),
    ],
)
def test_normalize_netbackup_status(raw, expected):
    assert DatabaseService._normalize_netbackup_status(raw) == expected


def test_finalize_job_stats_computes_totals_and_rate():
    svc_cls = DatabaseService
    series = [
        {"period": "2026-04-01", "status": "success", "job_type": "Full", "policy_type": None, "count": 80},
        {"period": "2026-04-01", "status": "failed", "job_type": "Full", "policy_type": None, "count": 10},
        {"period": "2026-04-02", "status": "success", "job_type": "Full", "policy_type": None, "count": 90},
        {"period": "2026-04-02", "status": "warning", "job_type": "Full", "policy_type": None, "count": 5},
    ]
    out = svc_cls._finalize_job_stats(
        series,
        "veeam",
        "day",
        {"start": "2026-04-01", "end": "2026-04-02"},
    )
    assert out["vendor"] == "veeam"
    assert out["totals"]["total"] == 185
    assert out["totals"]["success"] == 170
    assert out["totals"]["failed"] == 10
    assert out["totals"]["warning"] == 5
    assert out["totals"]["period_count"] == 2
    # 170 / 185 ≈ 91.89
    assert out["totals"]["success_rate"] == pytest.approx(91.89, abs=0.01)
    assert out["totals"]["avg_per_period"] == pytest.approx(92.5, abs=0.01)


def test_empty_job_stats_shape():
    out = DatabaseService._empty_job_stats("veeam", "day", {"start": "x", "end": "y"})
    assert out["vendor"] == "veeam"
    assert out["series"] == []
    assert out["totals"]["total"] == 0
    assert out["totals"]["success_rate"] == 0.0
    assert out["as_of"] and out["as_of"].endswith("Z")


def test_finalize_job_stats_uses_provided_as_of():
    out = DatabaseService._finalize_job_stats(
        [], "veeam", "day", {"start": "x", "end": "y"}, as_of="2026-05-14T12:00:00Z"
    )
    assert out["as_of"] == "2026-05-14T12:00:00Z"


def test_finalize_job_stats_defaults_as_of_to_now():
    out = DatabaseService._finalize_job_stats([], "veeam", "day", {"start": "x", "end": "y"})
    assert out["as_of"].endswith("Z") and len(out["as_of"]) >= 16


# ---------------------------------------------------------------------------
# Integration tests — live bulutlake
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def db():
    svc = DatabaseService()
    if svc._pool is None:
        pytest.skip("Bulutlake DB is unreachable from this environment.")
    return svc


def _assert_jobstats_shape(payload: dict, vendor: str, granularity: str) -> None:
    assert payload["vendor"] == vendor
    assert payload["granularity"] == granularity
    assert "range" in payload
    assert isinstance(payload["series"], list)
    assert isinstance(payload.get("as_of"), str) and payload["as_of"], "as_of must be a non-empty ISO timestamp"
    totals = payload["totals"]
    series_total = sum(int(p["count"]) for p in payload["series"])
    assert totals["total"] == series_total, "totals.total must equal sum of series counts"
    # success + failed + warning + other == total
    assert (
        totals["success"] + totals["failed"] + totals["warning"] + totals["other"]
        == totals["total"]
    )
    if totals["total"] > 0:
        # success_rate must be sensible
        assert 0.0 <= totals["success_rate"] <= 100.0


@pytest.mark.parametrize("granularity", ["day", "week", "month"])
def test_veeam_jobs_live(db: DatabaseService, granularity: str):
    # Look back 14 days (small window) to keep test fast
    time_range = {"start": "2026-04-30", "end": "2026-05-14", "preset": "custom"}
    payload = db.get_dc_veeam_jobs("DC13", time_range, granularity)
    print(f"\n[VEEAM/{granularity}] series rows: {len(payload['series'])}, totals: {payload['totals']}")
    _assert_jobstats_shape(payload, "veeam", granularity)


@pytest.mark.parametrize("granularity", ["day", "week", "month"])
def test_zerto_jobs_live(db: DatabaseService, granularity: str):
    time_range = {"start": "2026-04-30", "end": "2026-05-14", "preset": "custom"}
    payload = db.get_dc_zerto_jobs("DC13", time_range, granularity)
    print(f"\n[ZERTO/{granularity}] series rows: {len(payload['series'])}, totals: {payload['totals']}")
    _assert_jobstats_shape(payload, "zerto", granularity)


@pytest.mark.parametrize("granularity", ["day", "week", "month"])
def test_netbackup_jobs_live(db: DatabaseService, granularity: str):
    time_range = {"start": "2026-04-30", "end": "2026-05-14", "preset": "custom"}
    payload = db.get_dc_netbackup_jobs("DC13", time_range, granularity)
    print(f"\n[NETBACKUP/{granularity}] series rows: {len(payload['series'])}, totals: {payload['totals']}")
    _assert_jobstats_shape(payload, "netbackup", granularity)


def test_veeam_jobs_dc_isolation(db: DatabaseService):
    """İki farklı DC için sorgu at; toplamlar farklı olmalı (aynı DB filter çalışıyorsa)."""
    time_range = {"start": "2026-04-30", "end": "2026-05-14", "preset": "custom"}
    a = db.get_dc_veeam_jobs("DC13", time_range, "day")
    b = db.get_dc_veeam_jobs("DC14", time_range, "day")
    print(f"\nDC13 total={a['totals']['total']}, DC14 total={b['totals']['total']}")
    # Toplamlar aynı olabilir ama series yapısı genelde farklı olmalı.
    # Filter çalışmıyorsa ikisi BIREBIR aynı olur — buna karşı assert.
    same_series = a["series"] == b["series"]
    same_total = a["totals"]["total"] == b["totals"]["total"]
    if a["totals"]["total"] == 0 and b["totals"]["total"] == 0:
        pytest.skip("Bu zaman aralığında her iki DC için veri yok.")
    assert not (same_series and same_total), (
        "DC13 ve DC14 için sonuçlar BIREBIR aynı — DC filter çalışmıyor olabilir."
    )


def test_veeam_jobs_caches_second_call(db: DatabaseService):
    """İkinci çağrı cache'den dönmeli (aynı obje referansı veya eşit içerik)."""
    time_range = {"start": "2026-05-01", "end": "2026-05-08", "preset": "custom"}
    first = db.get_dc_veeam_jobs("DC13", time_range, "day")
    second = db.get_dc_veeam_jobs("DC13", time_range, "day")
    assert first == second
