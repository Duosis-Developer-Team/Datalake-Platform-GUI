"""P0-6: a stale compute entry must trigger the recompute it promises.

cache_service.get_with_stale returns (value, is_stale) and its docstring is
explicit about the contract: "is_stale=True → fresh expire, stale snapshot
kullanılıyor → arayan kişi arka planda revalidate tetiklemeli."

Ten call sites in dc_service honour that. `_get_compute_cached` — the one behind
both cluster-filtered compute panels — read the tuple and threw the flag away:

    val, _stale = cache.get_with_stale(key)

So the entry's life ran fresh for 10 minutes, then stale for 20 more with nobody
ever recomputing it, and at minute 30 the stale copy expired too and the next
visitor paid a cold multi-query SQL fetch. From the operator's side: the panel
holds one set of numbers for half an hour, hangs, and comes back with different
ones. The stale window is not a grace period if nothing uses it to refresh.

These pin the three paths separately — fresh, stale, miss — because the bug was
invisible in two of them.
"""
from __future__ import annotations

from unittest.mock import patch

from psycopg2 import OperationalError

from app.services import cache_service as cs
from app.services.dc_service import DatabaseService

TR = {"start": "2026-07-28", "end": "2026-08-03", "preset": "7d"}
CLUSTERS = ["KM-1"]

FRESH_TTL = DatabaseService._COMPUTE_CACHE_FRESH_TTL
STALE_TTL = DatabaseService._COMPUTE_CACHE_STALE_TTL


def _make_service():
    with patch(
        "app.services.dc_service.pg_pool.ThreadedConnectionPool",
        side_effect=OperationalError("no db"),
    ):
        svc = DatabaseService()
    svc._dc_list = ["DC13"]
    return svc


def _key(svc, kind="classic"):
    return svc._compute_cache_key(kind, "DC13", TR, CLUSTERS)


def _purge(key) -> None:
    cs.delete(key)
    cs.delete(f"stale:{key}")
    # _trigger_async_swr_refresh recomputes under a singleflight lock that
    # memoises its result for 60 s, so concurrent stale hits on one key collapse
    # into a single recompute. Across tests that memo is pollution: the second
    # test's "recompute" would return the first test's answer.
    cs.delete(f"_sf:{key}")


def _seed(key, payload, *, stale_only: bool) -> None:
    _purge(key)
    cs.set_with_stale(key, payload, fresh_ttl=FRESH_TTL, stale_ttl=STALE_TTL)
    if stale_only:
        cs.delete(key)  # fresh gone, stale snapshot remains


class _RanInline:
    """Runs the background thread's target on the calling thread.

    The recompute is a daemon thread in production; a test that let it float
    would be racing it. Same trick as test_backup_jobs_stale.
    """

    def __init__(self, target, daemon=True, name=""):
        self._target = target
        self.daemon = daemon
        self.name = name

    def start(self):
        self._target()


def _call(svc, kind, *, fetch_result=None):
    """Invoke the filtered-metrics method with the SQL body stubbed out."""
    method = f"get_{kind}_metrics_filtered"
    fetcher = f"_fetch_{kind}_filtered"
    with patch.object(svc, "_is_full_cluster_selection", return_value=False), \
         patch.object(svc, fetcher, return_value=fetch_result or {"hosts": 99}) as p_fetch:
        out = getattr(svc, method)("DC13", CLUSTERS, dict(TR))
    return out, p_fetch


# --- fresh: no recompute -----------------------------------------------------


def test_a_fresh_entry_is_served_without_recomputing_anything():
    svc = _make_service()
    _seed(_key(svc), {"hosts": 1}, stale_only=False)

    with patch.object(svc, "_trigger_async_swr_refresh") as p_trigger:
        out, p_fetch = _call(svc, "classic")

    assert out == {"hosts": 1}
    p_fetch.assert_not_called()
    p_trigger.assert_not_called()


# --- stale: serve it, and refresh behind the request -------------------------


def test_a_stale_entry_is_served_and_a_recompute_is_triggered():
    """The defect. Before this, the stale value was returned and that was all —
    it stayed stale until it expired outright."""
    svc = _make_service()
    _seed(_key(svc), {"hosts": 2}, stale_only=True)

    with patch.object(svc, "_trigger_async_swr_refresh") as p_trigger:
        out, p_fetch = _call(svc, "classic")

    assert out == {"hosts": 2}, "the caller still gets an instant answer"
    # ...and does not wait for the recompute
    p_fetch.assert_not_called()
    p_trigger.assert_called_once()
    assert p_trigger.call_args[0][0] == _key(svc), "refreshes the entry it read"


def test_the_hyperconv_panel_revalidates_too():
    svc = _make_service()
    _seed(_key(svc, "hyperconv"), {"hosts": 3}, stale_only=True)

    with patch.object(svc, "_trigger_async_swr_refresh") as p_trigger:
        out, _ = _call(svc, "hyperconv")

    assert out == {"hosts": 3}
    p_trigger.assert_called_once()


def test_the_recompute_writes_the_new_value_back_under_the_same_key():
    """End to end through the real _trigger_async_swr_refresh: the point of the
    refresh is that the *next* reader gets fresh numbers without waiting."""
    svc = _make_service()
    key = _key(svc)
    _seed(key, {"hosts": 4}, stale_only=True)

    with patch("app.services.dc_service.threading.Thread", _RanInline):
        out, _ = _call(svc, "classic", fetch_result={"hosts": 40})

    assert out == {"hosts": 4}, "this request still returned the stale copy"
    value, is_stale = cs.get_with_stale(key)
    assert value == {"hosts": 40}, "the next request gets the recomputed one"
    assert is_stale is False


def test_the_recompute_runs_off_the_request_thread():
    svc = _make_service()
    _seed(_key(svc), {"hosts": 5}, stale_only=True)

    started: list[tuple] = []

    class _Spy(_RanInline):
        def start(self):
            started.append((self.daemon, self.name))
            super().start()

    with patch("app.services.dc_service.threading.Thread", _Spy):
        _call(svc, "classic")

    assert started and started[0][0] is True, "must be a daemon thread, not a request-blocking one"


def test_a_failed_recompute_leaves_the_stale_copy_in_place():
    """Backgrounded work has nobody to report to. It must not take the cached
    value down with it — a page that was rendering is better than one that is
    not."""
    svc = _make_service()
    key = _key(svc)
    _seed(key, {"hosts": 6}, stale_only=True)

    with patch("app.services.dc_service.threading.Thread", _RanInline), \
         patch.object(svc, "_is_full_cluster_selection", return_value=False), \
         patch.object(svc, "_fetch_classic_filtered", side_effect=OperationalError("db gone")):
        out = svc.get_classic_metrics_filtered("DC13", CLUSTERS, dict(TR))

    assert out == {"hosts": 6}
    assert cs.get_with_stale(key)[0] == {"hosts": 6}


# --- miss: compute synchronously, then cache --------------------------------


def test_a_cold_miss_computes_once_and_caches_the_result():
    svc = _make_service()
    key = _key(svc)
    _purge(key)

    with patch.object(svc, "_trigger_async_swr_refresh") as p_trigger:
        out, p_fetch = _call(svc, "classic", fetch_result={"hosts": 7})

    assert out == {"hosts": 7}
    p_fetch.assert_called_once()
    p_trigger.assert_not_called()  # nothing to revalidate; it was just computed
    assert cs.get_with_stale(key)[0] == {"hosts": 7}


def test_a_cold_miss_writes_both_the_fresh_and_the_stale_snapshot():
    """Without the stale copy there is no stale-while-revalidate at all — the
    entry would go straight from fresh to absent."""
    svc = _make_service()
    key = _key(svc)
    _purge(key)

    _call(svc, "classic", fetch_result={"hosts": 8})

    assert cs.get(key) == {"hosts": 8}
    assert cs.get(f"stale:{key}") == {"hosts": 8}
