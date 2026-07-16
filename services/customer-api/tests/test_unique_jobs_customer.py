"""
Unit tests for the customer-scoped unique-job inventory (Backup & Replication
table view, customer-api side): row mappers, pattern resolution, cache key
shape, and paged/filtered table totals.

No live DB / Redis required — `_get_connection`/`_run_rows` are stubbed and
`resolve_source_patterns` is monkeypatched per test.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from psycopg2 import OperationalError

from app.db.queries import customer as cq
from app.services import cache_service as cache
from app.services.customer_mapping_resolver import ResolvedSourcePatterns
from app.services.customer_service import CustomerService


def _make_service() -> CustomerService:
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = CustomerService()
    return svc


class _CursorCtx:
    def __enter__(self):
        return object()

    def __exit__(self, exc_type, exc, tb):
        return False


class _ConnCtx:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return _CursorCtx()


# ---------------------------------------------------------------------------
# Row mappers
# ---------------------------------------------------------------------------


def test_map_veeam_unique_row_preserves_column_order():
    row = (
        "2026-05-01T00:00:00Z", "j1", "Acme-Job1", "Backup",
        "Success", "Success", "2026-05-01T00:00:00Z", 5, "s1", "vm", "10.34.2.104",
    )
    mapped = CustomerService._map_veeam_unique_row(row)
    assert mapped["id"] == "j1"
    assert mapped["name"] == "Acme-Job1"
    assert mapped["status"] == "Success"
    assert mapped["source_ip"] == "10.34.2.104"


@pytest.mark.parametrize("raw_status,expected", [(1, "success"), (2, "failed"), (0, "running"), (4, "warning")])
def test_map_zerto_unique_row_normalizes_status(raw_status, expected):
    row = ("t", "v1", "Acme-VPG1", raw_status, 2, "DC13-Site01", "TurksatDC_ZVM", 100, 50, "zh1")
    mapped = CustomerService._map_zerto_unique_row(row)
    assert mapped["id"] == "v1"
    assert mapped["status"] == expected


@pytest.mark.parametrize("raw_status,expected", [(0, "success"), (1, "warning"), (2, "failed")])
def test_map_netbackup_unique_row_normalizes_status(raw_status, expected):
    row = ("t1", "t2", "1", "pol1", "VMWARE", "BACKUP", raw_status, "wl1", "c1", "nbmediadc13.blt.vc", 100, 1.0, 100)
    mapped = CustomerService._map_netbackup_unique_row(row)
    assert mapped["status"] == expected
    assert mapped["category"] == "image"  # VMWARE -> image


def test_map_netbackup_unique_row_application_category():
    row = ("t1", "t2", "2", "sap-daily", "SAP", "BACKUP", 0, "wl2", "c2", "nbmediadc14.blt.vc", 10, 1.0, 100)
    mapped = CustomerService._map_netbackup_unique_row(row)
    assert mapped["category"] == "application"


def test_map_unique_row_dispatches_by_vendor():
    svc = _make_service()
    veeam_row = ("t", "j1", "n", "Backup", "Success", "Success", "t", 1, "s", "vm", "ip")
    assert svc._map_unique_row("veeam", veeam_row)["id"] == "j1"
    assert svc._map_unique_row("bogus-vendor", veeam_row) == {}


# ---------------------------------------------------------------------------
# Pattern resolution — _unique_jobs_patterns
# ---------------------------------------------------------------------------


def test_unique_jobs_patterns_uses_resolved_backup_patterns():
    svc = _make_service()
    resolved = ResolvedSourcePatterns(ilike_by_source={"backup_veeam": ["%Acme%", "%AcmeCorp%"]})
    with patch.object(svc, "resolve_source_patterns", return_value=resolved):
        patterns = svc._unique_jobs_patterns("Acme", "veeam")
    assert patterns == ["%Acme%", "%AcmeCorp%"]


def test_unique_jobs_patterns_falls_back_to_infra_search_name():
    svc = _make_service()
    resolved = ResolvedSourcePatterns()  # no mappings
    with patch.object(svc, "resolve_source_patterns", return_value=resolved), \
         patch.object(svc, "resolve_infra_search_name", return_value="Acme"):
        patterns = svc._unique_jobs_patterns("Acme Corp", "netbackup")
    assert patterns == ["%Acme%"]


def test_unique_jobs_patterns_unknown_vendor_returns_empty():
    svc = _make_service()
    assert svc._unique_jobs_patterns("Acme", "bogus") == []


def test_unique_jobs_patterns_swallows_resolver_errors():
    svc = _make_service()
    with patch.object(svc, "resolve_source_patterns", side_effect=RuntimeError("boom")), \
         patch.object(svc, "resolve_infra_search_name", return_value="Acme"):
        patterns = svc._unique_jobs_patterns("Acme", "veeam")
    assert patterns == ["%Acme%"]


# ---------------------------------------------------------------------------
# _fetch_customer_unique_jobs — pattern query dispatch + dedup
# ---------------------------------------------------------------------------


def test_fetch_customer_unique_jobs_veeam_uses_first_pattern_only():
    svc = _make_service()
    veeam_rows = [
        ("t1", "j1", "Acme-Job1", "Backup", "Success", "Success", "t1", 1, "s1", "vm", "10.0.0.1"),
    ]
    seen_patterns: list[str] = []

    def fake_run_rows(cur, sql, params=None):
        if sql == cq.CUSTOMER_VEEAM_UNIQUE_JOBS_LATEST:
            seen_patterns.append(params[0])
            return veeam_rows
        return []

    with patch.object(svc, "_get_connection", return_value=_ConnCtx()), \
         patch.object(svc, "_run_rows", side_effect=fake_run_rows), \
         patch.object(svc, "_unique_jobs_patterns", return_value=["%Acme%", "%AcmeCorp%"]):
        out = svc._fetch_customer_unique_jobs("Acme", "veeam", "start", "end")

    assert seen_patterns == ["%Acme%"]  # only the first (highest-priority) pattern is queried
    assert [r["id"] for r in out["rows"]] == ["j1"]
    assert out["vendor"] == "veeam"


def test_fetch_customer_unique_jobs_zerto_merges_all_patterns_and_dedups():
    svc = _make_service()

    def fake_run_rows(cur, sql, params=None):
        if sql == cq.CUSTOMER_ZERTO_UNIQUE_VPGS_LATEST:
            pattern = params[0]
            if pattern == "%Acme%":
                return [("t1", "v1", "Acme-App1", 1, 2, "DC13-Site01", "DC14", 100, 50, "zh1")]
            if pattern == "%AcmeCorp%":
                # v1 re-appears under the second pattern (should be deduped) + a new v2
                return [
                    ("t1", "v1", "Acme-App1", 1, 2, "DC13-Site01", "DC14", 100, 50, "zh1"),
                    ("t2", "v2", "AcmeCorp-App2", 1, 1, "DC13-Site01", "DC14", 100, 50, "zh2"),
                ]
        return []

    with patch.object(svc, "_get_connection", return_value=_ConnCtx()), \
         patch.object(svc, "_run_rows", side_effect=fake_run_rows), \
         patch.object(svc, "_unique_jobs_patterns", return_value=["%Acme%", "%AcmeCorp%"]):
        out = svc._fetch_customer_unique_jobs("Acme", "zerto", "start", "end")

    assert {r["id"] for r in out["rows"]} == {"v1", "v2"}
    assert out["totals"]["total_jobs"] == 2


def test_fetch_customer_unique_jobs_unknown_vendor_returns_empty():
    svc = _make_service()
    out = svc._fetch_customer_unique_jobs("Acme", "bogus", "start", "end")
    assert out["rows"] == []
    assert out["vendor"] == "bogus"


# ---------------------------------------------------------------------------
# Cached base set (SWR) — get_customer_unique_jobs
# ---------------------------------------------------------------------------


def test_get_customer_unique_jobs_cache_key_shape():
    svc = _make_service()
    tr = {"start": "2026-04-01", "end": "2026-05-01", "preset": "custom"}
    expected_key = "cust_veeam_unique_jobs:Acme:2026-04-01:2026-05-01"
    cache.delete(expected_key)

    computed = {"rows": [], "totals": {}, "as_of": "x", "vendor": "veeam"}
    with patch.object(svc, "_fetch_customer_unique_jobs", return_value=computed) as p_fetch:
        out = svc.get_customer_unique_jobs("Acme", "veeam", tr)

    assert out == computed
    p_fetch.assert_called_once()
    # The important, non-brittle assertion: the value is now cached under the
    # documented key shape (cust_{vendor}_unique_jobs:{customer}:{start}:{end}).
    cached_val, is_stale = cache.get_with_stale(expected_key)
    assert cached_val == computed
    assert is_stale is False


def test_get_customer_unique_jobs_fresh_hit_skips_fetch():
    svc = _make_service()
    tr = {"start": "2026-04-01", "end": "2026-05-01", "preset": "custom"}
    key = "cust_veeam_unique_jobs:Acme:2026-04-01:2026-05-01"
    cache.delete(key)
    fresh_payload = {"rows": [], "totals": {}, "as_of": "x", "vendor": "veeam"}
    cache.set_with_stale(key, fresh_payload, fresh_ttl=30, stale_ttl=600)

    with patch.object(svc, "_fetch_customer_unique_jobs") as p_fetch:
        out = svc.get_customer_unique_jobs("Acme", "veeam", tr)

    assert out == fresh_payload
    p_fetch.assert_not_called()


def test_get_customer_unique_jobs_stale_hit_triggers_async_refresh():
    svc = _make_service()
    tr = {"start": "2026-04-01", "end": "2026-05-01", "preset": "custom"}
    key = "cust_veeam_unique_jobs:Acme:2026-04-01:2026-05-01"
    cache.delete(key)
    stale_payload = {"rows": [], "totals": {}, "as_of": "x", "vendor": "veeam"}
    cache.set_with_stale(key, stale_payload, fresh_ttl=30, stale_ttl=600)
    from app.core.cache_backend import _memory_lock, _memory_cache
    with _memory_lock:
        _memory_cache.pop(key, None)  # keep only the ':last_good' shadow key -> stale path

    with patch.object(svc, "_trigger_async_unique_jobs_refresh") as p_trigger:
        out = svc.get_customer_unique_jobs("Acme", "veeam", tr)

    assert out == stale_payload
    p_trigger.assert_called_once()


# ---------------------------------------------------------------------------
# Paged/filtered table — get_customer_unique_jobs_table
# ---------------------------------------------------------------------------


def test_get_customer_unique_jobs_table_paginates_and_recomputes_filtered_totals():
    svc = _make_service()
    rows = [
        {"id": "j1", "name": "Acme-A", "type": "Backup", "status": "success"},
        {"id": "j2", "name": "Acme-B", "type": "Backup", "status": "failed"},
        {"id": "j3", "name": "Acme-C", "type": "Backup", "status": "success"},
    ]
    base = {"rows": rows, "totals": {"total_jobs": 3}, "as_of": "x", "vendor": "veeam"}

    with patch.object(svc, "get_customer_unique_jobs", return_value=base):
        out = svc.get_customer_unique_jobs_table(
            "Acme", "veeam", None, page=1, page_size=1, statuses=["success"],
        )

    assert out["vendor"] == "veeam"
    assert out["total"] == 2
    assert len(out["items"]) == 1
    assert out["totals"]["total_jobs"] == 2


def test_get_customer_unique_jobs_table_search_filters_by_name():
    svc = _make_service()
    rows = [
        {"id": "j1", "name": "Acme-Prod", "type": "Backup", "status": "success"},
        {"id": "j2", "name": "OtherCo-Prod", "type": "Backup", "status": "success"},
    ]
    base = {"rows": rows, "totals": {}, "as_of": "x", "vendor": "veeam"}

    with patch.object(svc, "get_customer_unique_jobs", return_value=base):
        out = svc.get_customer_unique_jobs_table("Acme", "veeam", None, search="acme")

    assert [r["id"] for r in out["items"]] == ["j1"]


# ---------------------------------------------------------------------------
# Warm hook
# ---------------------------------------------------------------------------


def test_warm_customer_unique_jobs_calls_all_three_vendors():
    svc = _make_service()
    calls: list[tuple] = []

    def fake_get(customer_name, vendor, time_range=None):
        calls.append((customer_name, vendor))
        return {}

    with patch.object(svc, "get_customer_unique_jobs", side_effect=fake_get):
        svc.warm_customer_unique_jobs("Acme")

    assert calls == [("Acme", "veeam"), ("Acme", "zerto"), ("Acme", "netbackup")]


def test_warm_customer_unique_jobs_tolerates_per_vendor_failure():
    svc = _make_service()

    def fake_get(customer_name, vendor, time_range=None):
        if vendor == "zerto":
            raise RuntimeError("boom")
        return {}

    with patch.object(svc, "get_customer_unique_jobs", side_effect=fake_get):
        svc.warm_customer_unique_jobs("Acme")  # must not raise
