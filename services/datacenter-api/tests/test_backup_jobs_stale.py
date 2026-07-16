"""
Phase 3 B3 — Stale-while-revalidate tests.

Cache fresh hit / stale hit / total miss path'lerini ayrı ayrı doğrula. Stale
hit'te background thread tetiklenmeli; fresh hit'te tetiklenmemeli.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from psycopg2 import OperationalError

from app.services import cache_service as cs
from app.services.dc_service import DatabaseService


# ---- cache_service helper'ları ---------------------------------------------


def test_get_with_stale_returns_fresh_when_present():
    cs.delete("k1")
    cs.delete("stale:k1")
    cs.set_with_stale("k1", {"v": 1}, fresh_ttl=30, stale_ttl=600)
    value, is_stale = cs.get_with_stale("k1")
    assert value == {"v": 1}
    assert is_stale is False


def test_get_with_stale_returns_stale_when_fresh_missing():
    cs.delete("k2")
    cs.set_with_stale("k2", {"v": 2}, fresh_ttl=30, stale_ttl=600)
    # Fresh'i sil, stale'i bırak
    cs.delete("k2")
    value, is_stale = cs.get_with_stale("k2")
    assert value == {"v": 2}
    assert is_stale is True


def test_get_with_stale_returns_none_when_both_missing():
    cs.delete("k3")
    cs.delete("stale:k3")
    value, is_stale = cs.get_with_stale("k3")
    assert value is None
    assert is_stale is False


def test_set_with_stale_writes_both_keys():
    cs.delete("k4")
    cs.delete("stale:k4")
    cs.set_with_stale("k4", {"v": 4}, fresh_ttl=30, stale_ttl=600)
    assert cs.get("k4") == {"v": 4}
    assert cs.get("stale:k4") == {"v": 4}


# ---- DatabaseService stale path --------------------------------------------


def _make_service(dc_list=("DC13",)):
    with patch("app.services.dc_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = DatabaseService()
    svc._dc_list = list(dc_list)
    return svc


def test_fresh_hit_returns_value_without_trigger():
    svc = _make_service()
    cache_key = "dc_veeam_jobs:DC13:2026-04-01:2026-05-01:day"
    cs.delete(cache_key)
    cs.delete(f"stale:{cache_key}")
    fresh_payload = {"vendor": "veeam", "totals": {"total": 100}}
    cs.set_with_stale(cache_key, fresh_payload, fresh_ttl=30, stale_ttl=600)

    with patch.object(svc, "_trigger_async_jobs_compute") as p_trigger:
        out = svc.get_dc_veeam_jobs(
            "DC13",
            {"start": "2026-04-01", "end": "2026-05-01", "preset": "custom"},
            "day",
        )

    assert out == fresh_payload
    p_trigger.assert_not_called()


def test_stale_hit_returns_value_and_triggers_async_compute():
    svc = _make_service()
    cache_key = "dc_veeam_jobs:DC13:2026-04-01:2026-05-01:day"
    cs.delete(cache_key)
    cs.delete(f"stale:{cache_key}")
    stale_payload = {"vendor": "veeam", "totals": {"total": 50}}
    cs.set_with_stale(cache_key, stale_payload, fresh_ttl=30, stale_ttl=600)
    cs.delete(cache_key)  # only stale remains

    with patch.object(svc, "_trigger_async_jobs_compute") as p_trigger:
        out = svc.get_dc_veeam_jobs(
            "DC13",
            {"start": "2026-04-01", "end": "2026-05-01", "preset": "custom"},
            "day",
        )

    assert out == stale_payload
    p_trigger.assert_called_once()
    args, _ = p_trigger.call_args
    assert args[0] == "veeam"  # vendor


def test_stale_hit_rewrites_via_set_with_stale_not_plain_set():
    """Stale re-write must use set_with_stale so fresh+stale TTLs stay aligned."""
    svc = _make_service()
    cache_key = "dc_veeam_jobs:DC13:2026-04-01:2026-05-01:day"
    cs.delete(cache_key)
    cs.delete(f"stale:{cache_key}")
    stale_payload = {"vendor": "veeam", "totals": {"total": 50}, "series": []}
    cs.set_with_stale(cache_key, stale_payload, fresh_ttl=30, stale_ttl=600)
    cs.delete(cache_key)

    with patch.object(svc, "_trigger_async_jobs_compute"), \
         patch("app.services.dc_service.cache.set_with_stale") as p_swr, \
         patch("app.services.dc_service.cache.set") as p_set:
        out = svc.get_dc_veeam_jobs(
            "DC13",
            {"start": "2026-04-01", "end": "2026-05-01", "preset": "custom"},
            "day",
        )

    assert out == stale_payload
    p_swr.assert_called()
    p_set.assert_not_called()


def test_total_miss_falls_back_to_synchronous_compute():
    svc = _make_service()
    cache_key = "dc_veeam_jobs:DC13:2026-04-01:2026-05-01:day"
    cs.delete(cache_key)
    cs.delete(f"stale:{cache_key}")

    fake_payload = {"vendor": "veeam", "totals": {"total": 7}}
    with patch.object(svc, "_compute_all_dc_veeam_jobs", return_value={"DC13": fake_payload}) as p_compute, \
         patch.object(svc, "_trigger_async_jobs_compute") as p_trigger:
        out = svc.get_dc_veeam_jobs(
            "DC13",
            {"start": "2026-04-01", "end": "2026-05-01", "preset": "custom"},
            "day",
        )

    assert out == fake_payload
    p_compute.assert_called_once()
    p_trigger.assert_not_called()


def test_trigger_async_starts_thread_and_uses_singleflight():
    svc = _make_service()

    captured: list[tuple] = []

    class _FakeThread:
        def __init__(self, target, daemon, name):
            self._target = target
            self._daemon = daemon
            self._name = name

        def start(self):
            captured.append((self._daemon, self._name))
            self._target()

    with patch("app.services.dc_service.threading.Thread", _FakeThread), \
         patch.object(svc, "_compute_all_dc_zerto_jobs", return_value={"DC13": {}}) as p_compute:
        svc._trigger_async_jobs_compute(
            "zerto", "week", "s", "e", "2026-04-01", "2026-05-01"
        )

    assert captured == [(True, "bkp-stale-refresh-zerto")]
    p_compute.assert_called_once()
