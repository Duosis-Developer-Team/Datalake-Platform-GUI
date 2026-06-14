"""C2: stale cache entries are served immediately and refreshed in the background."""
import time
from src.services import api_client as api
from src.services import cache_service


def _set_with_age(key, value, age_seconds):
    cache_service.set(key, value)
    api._fetched_at[key] = time.monotonic() - age_seconds


def test_fresh_entry_does_not_schedule_refresh(monkeypatch):
    cache_service.clear()
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 300.0)
    scheduled = []
    monkeypatch.setattr(api, "_schedule_swr_refresh", lambda k, f: scheduled.append(k))
    _set_with_age("fresh", {"v": 1}, age_seconds=10)  # well under TTL
    out = api._api_cache_get_with_stale("fresh", lambda: {"v": 2}, {})
    assert out == {"v": 1}
    assert scheduled == []


def test_stale_entry_served_now_and_schedules_one_refresh(monkeypatch):
    cache_service.clear()
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 300.0)
    scheduled = []
    monkeypatch.setattr(api, "_schedule_swr_refresh", lambda k, f: scheduled.append(k))
    _set_with_age("stale", {"v": 1}, age_seconds=310)  # older than TTL
    out = api._api_cache_get_with_stale("stale", lambda: {"v": 2}, {})
    assert out == {"v": 1}, "must serve the cached (stale) value immediately, not block"
    assert scheduled == ["stale"], "exactly one background refresh scheduled"


def test_ttl_zero_disables_swr(monkeypatch):
    cache_service.clear()
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 0.0)
    scheduled = []
    monkeypatch.setattr(api, "_schedule_swr_refresh", lambda k, f: scheduled.append(k))
    _set_with_age("any", {"v": 1}, age_seconds=99999)
    api._api_cache_get_with_stale("any", lambda: {"v": 2}, {})
    assert scheduled == []


def test_no_timestamp_entry_not_refreshed(monkeypatch):
    """Warm-job entries (set directly, no _fetched_at) must NOT be auto-refreshed."""
    cache_service.clear()
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 300.0)
    scheduled = []
    monkeypatch.setattr(api, "_schedule_swr_refresh", lambda k, f: scheduled.append(k))
    cache_service.set("warm", {"v": 1})  # no _fetched_at entry
    api._api_cache_get_with_stale("warm", lambda: {"v": 2}, {})
    assert scheduled == []


def test_leader_fetch_records_timestamp(monkeypatch):
    cache_service.clear()
    api._fetched_at.pop("missk", None)
    api._api_cache_get_with_stale("missk", lambda: {"v": 9}, {})
    assert "missk" in api._fetched_at  # leader path stamped it


def test_schedule_swr_refresh_runs_fetch_and_updates(monkeypatch):
    """The real _schedule_swr_refresh executes the fetch and updates cache+timestamp."""
    cache_service.clear()
    _set_with_age("rk", {"v": 1}, age_seconds=999)
    api._schedule_swr_refresh("rk", lambda: {"v": 2})
    # background executor — wait briefly for completion
    for _ in range(50):
        if cache_service.get("rk") == {"v": 2}:
            break
        time.sleep(0.02)
    assert cache_service.get("rk") == {"v": 2}
