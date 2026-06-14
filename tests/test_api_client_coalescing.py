"""C1: concurrent misses for the same key trigger exactly ONE fetch (single-flight)."""
import threading
import time
from src.services import api_client as api
from src.services import cache_service


def test_concurrent_misses_fetch_once():
    cache_service.clear()
    calls = {"n": 0}
    lock = threading.Lock()

    def slow_fetch():
        with lock:
            calls["n"] += 1
        time.sleep(0.3)
        return {"v": 42}

    results = []
    def worker():
        results.append(api._api_cache_get_with_stale("coalesce-key", slow_fetch, {}))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()

    assert calls["n"] == 1, f"expected single-flight (1 fetch), got {calls['n']}"
    assert all(r == {"v": 42} for r in results)
    assert cache_service.get("coalesce-key") == {"v": 42}


def test_different_keys_run_in_parallel():
    """Different keys must NOT serialize (lock not held during fetch)."""
    cache_service.clear()
    barrier = threading.Barrier(3, timeout=2.0)

    def fetch_for(v):
        def f():
            barrier.wait()  # all 3 must be inside fetch simultaneously, else Barrier times out
            return {"v": v}
        return f

    errs = []
    def worker(k, v):
        try:
            api._api_cache_get_with_stale(k, fetch_for(v), {})
        except Exception as e:
            errs.append(e)

    threads = [threading.Thread(target=worker, args=(f"k{i}", i)) for i in range(3)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert not errs, f"different keys serialized (barrier timed out): {errs}"


def test_sequential_miss_then_hit_still_one_fetch():
    cache_service.clear()
    calls = {"n": 0}
    def fetch():
        calls["n"] += 1
        return {"v": 1}
    api._api_cache_get_with_stale("k-seq", fetch, {})
    api._api_cache_get_with_stale("k-seq", fetch, {})
    assert calls["n"] == 1
