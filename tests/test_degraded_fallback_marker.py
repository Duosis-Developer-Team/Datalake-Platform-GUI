"""P0-4, part 2: tell "the backend said nothing" apart from "the backend said zero".

When a fetch fails or a follower's wait expires with nothing cached, the client
returns _clone(empty_fallback) — a fully-shaped payload of zeros. The page cannot
tell it from a measurement, so it renders "0 VMs, 0 hosts, 0 kW" as though those
were readings, and swaps in the real numbers on the next callback. Zeros are not
a neutral placeholder in a capacity product: an operator who sees them reasonably
concludes a datacenter fell over.

The distinction has to survive the return trip, so the fabricated payload is
tagged. Dicts carry a `_degraded` key; lists have nowhere to put one, so the type
carries it (_DegradedList). Pages ask through is_degraded() and never touch
either mechanism.

The boundary matters as much as the marker: a *measured* empty must stay
unmarked. A DC with genuinely no unmapped resources returns {"rows": [], ...},
which is equal to the fallback and equally uncacheable — but it is an answer, and
turning it into an error banner would be a new lie replacing the old one.
"""
from __future__ import annotations

import copy
import threading
import time
from unittest.mock import patch

import httpx
import pytest

from src.services import api_client as api
from src.services import cache_service


@pytest.fixture(autouse=True)
def clean_cache():
    cache_service.clear()
    api._inflight.clear()
    yield
    cache_service.clear()
    api._inflight.clear()


def _boom():
    raise httpx.ConnectError("backend down")


# --- the marker itself -------------------------------------------------------

def test_is_degraded_reads_the_dict_marker():
    assert api.is_degraded({"_degraded": True, "overview": {}}) is True
    assert api.is_degraded({"overview": {}}) is False


def test_is_degraded_reads_the_list_type():
    assert api.is_degraded(api._DegradedList()) is True
    assert api.is_degraded([]) is False


def test_a_degraded_list_still_behaves_like_a_list():
    """Nothing downstream should have to know the subclass exists."""
    d = api._DegradedList([1, 2])
    assert d == [1, 2]
    assert list(d) == [1, 2]
    assert len(d) == 2
    assert api._DegradedList() == []


def test_the_list_marker_survives_a_deepcopy():
    """_clone is deepcopy, and the fallback is cloned before it is returned."""
    assert api.is_degraded(copy.deepcopy(api._DegradedList())) is True


def test_is_degraded_tolerates_whatever_it_is_handed():
    for value in (None, 0, "", [], {}, [1], "text"):
        assert api.is_degraded(value) is False


# --- where the marker is applied --------------------------------------------

def test_a_failed_fetch_with_nothing_cached_is_degraded():
    out = api._api_cache_get_with_stale("api:dk1", _boom, {"overview": {"total_vms": 0}})

    assert api.is_degraded(out), "no answer was obtained; the zeros are fabricated"
    assert out["overview"] == {"total_vms": 0}, "shape preserved for callers that index it"


def test_a_failed_fetch_with_a_list_fallback_is_degraded():
    out = api._api_cache_get_with_stale("api:dk2", _boom, [])

    assert api.is_degraded(out)
    assert out == []


def test_a_failed_fetch_falls_back_to_last_good_and_is_not_degraded():
    """Real data from an earlier fetch is still real data. Only the fabricated
    payload is marked, or every backend hiccup would blank a working page."""
    api._cache_store("api:dk3", {"overview": {"total_vms": 900}})

    out = api._api_cache_get_with_stale("api:dk3", _boom, {"overview": {"total_vms": 0}})

    assert out == {"overview": {"total_vms": 900}}
    assert api.is_degraded(out) is False


def test_an_expired_follower_with_nothing_cached_is_degraded(monkeypatch):
    """The other fabricating path: the leader is still working, the follower's
    budget ran out, and it has nothing to show."""
    monkeypatch.setattr(api, "_INFLIGHT_WAIT_SECONDS", 0.2)
    monkeypatch.setattr(api, "_SHARED_RESULT_WAIT_SECONDS", 0.2)

    def slow():
        time.sleep(1.0)
        return {"overview": {"total_vms": 7}}

    results: dict[str, object] = {}

    def leader():
        api._api_cache_get_with_stale("api:dk4", slow, {"overview": {"total_vms": 0}})

    def follower():
        time.sleep(0.05)
        results["follower"] = api._api_cache_get_with_stale(
            "api:dk4", slow, {"overview": {"total_vms": 0}}
        )

    threads = [threading.Thread(target=leader), threading.Thread(target=follower)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert api.is_degraded(results["follower"])


# --- where it must NOT be applied -------------------------------------------

def test_a_measured_empty_is_not_degraded():
    """The false positive that would make this feature worse than the bug.

    {"rows": [], "total": 0} equals the fallback and is not worth caching, but
    the backend said it. Marking it degraded would put an error banner on every
    DC that legitimately has nothing to show.
    """
    empty = {"rows": [], "total": 0}

    out = api._api_cache_get_with_stale("api:dk5", lambda: dict(empty), empty)

    assert out == empty
    assert api.is_degraded(out) is False


def test_a_measured_empty_list_is_not_degraded():
    out = api._api_cache_get_with_stale("api:dk6", lambda: [], [])

    assert out == []
    assert api.is_degraded(out) is False


def test_a_successful_fetch_is_not_degraded():
    out = api._api_cache_get_with_stale("api:dk7", lambda: {"overview": {"total_vms": 5}}, {})

    assert api.is_degraded(out) is False


# --- the marker must never reach the cache -----------------------------------

def test_a_degraded_payload_is_never_cached():
    """It is a statement about one failed call, not about the data. Caching it
    would hand the marker to every later reader for the full TTL — and worse,
    would let a fabricated payload satisfy the freshness check."""
    api._api_cache_get_with_stale("api:dk8", _boom, {"overview": {}})

    assert cache_service.get("api:dk8") is None


def test_should_persist_refuses_a_degraded_dict():
    """Pinned at the guard as well as the call site: a degraded payload can be
    handed back into a cached function by a caller that did not check."""
    assert api._should_persist_api_cache({"_degraded": True, "rows": [{"a": 1}]}, {}) is False
    assert api._should_persist_api_cache({"rows": [{"a": 1}]}, {}) is True


def test_should_persist_refuses_a_degraded_list():
    assert api._should_persist_api_cache(api._DegradedList([{"a": 1}]), []) is False


def test_a_degraded_fetch_result_does_not_overwrite_last_good():
    """_prefer_stale_over_empty_fetch keys off the same guard, so a degraded
    payload arriving from a nested call cannot evict a working cached value.

    The stale entry's age is now part of the decision (see
    test_last_good_age_bound); zero stands for "just written", which is what
    _cache_store above did.
    """
    api._cache_store("api:dk9", {"rows": [{"id": 1}]})

    resolved = api._prefer_stale_over_empty_fetch(
        "api:dk9", {"rows": [{"id": 1}]}, 0.0, {"_degraded": True, "rows": []}, {"rows": []}
    )

    assert resolved == {"rows": [{"id": 1}]}


# --- the real fallbacks, end to end -----------------------------------------

def test_global_dashboard_marks_a_dead_backend():
    with patch.object(api, "_get_json", side_effect=httpx.ConnectError("down")):
        data = api.get_global_dashboard(None)

    assert api.is_degraded(data)
    assert data["overview"]["total_vms"] == 0, "shape intact so home.py can still index it"


def test_datacenters_summary_marks_a_dead_backend():
    with patch.object(api, "_get_json", side_effect=httpx.ConnectError("down")):
        rows = api.get_all_datacenters_summary(None)

    assert api.is_degraded(rows)
    assert rows == []


def test_dc_details_marks_a_dead_backend():
    with patch.object(api, "_get_json", side_effect=httpx.ConnectError("down")):
        data = api.get_dc_details("DC13", None)

    assert api.is_degraded(data)


def test_unmapped_resources_marks_a_dead_backend():
    with patch.object(api, "_get_json", side_effect=httpx.ConnectError("down")):
        data = api.get_unmapped_resources(None)

    assert api.is_degraded(data)
