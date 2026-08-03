"""Last-good has to stop being good eventually.

The audit filed this next to P1-6, and called it the more important half of it:

    "404, _HTTP_ERRORS'a dusup _api_cache_get_with_stale'in except kolunda yas
    sinirsiz last-good donduruyor. TTL'siz RedisBackend ile birlikte bu,
    *herhangi bir* endpoint 4xx vermeye basladiginda o key'in son snapshot'ini
    sonsuza kadar, hata gostermeden oynatmasi demek."

The failure it describes is not a backend that went down — it is a backend route
that is quietly wrong. P1-6 found four CRM calls pointed at the service that
does not mount them; every one of those returns 404 forever. On this path a 404
is caught, the last successful snapshot is returned in its place, and the page
renders normally. Nothing about the screen says the number stopped being
measured. An operator can read months-old figures off a page that looks live.

P0-8 put a 6-hour expiry on Redis entries, which bounds it there — but only
there: InProcessBackend (no Redis configured, or Redis unreachable at boot) has
no age expiry at all, only LRU, so a rarely-evicted key really can replay
forever. The bound belongs at the read, where it can be *said*, rather than
being a side effect of where the value happens to be stored.

So: below the bound, last-good is served silently — a backend hiccup should not
blank a working page, which is why P0-4 deliberately left this payload unmarked.
Above it, the page says it has no data instead of showing numbers nobody
measured. The two rules are the same rule at different ages.
"""
from __future__ import annotations

import time

import httpx
import pytest

from src.services import api_client as api
from src.services import cache_service

EMPTY = {"vms": 0, "hosts": 0}


@pytest.fixture(autouse=True)
def _isolated_backend():
    orig = cache_service.get_backend()
    cache_service.set_backend(cache_service.InProcessBackend())
    yield
    cache_service.set_backend(orig)


def _seed(key, value, age_seconds):
    cache_service.set(key, {api._SWR_STAMP: time.time() - age_seconds, "value": value})


def _boom():
    raise httpx.HTTPStatusError("404", request=None, response=None)


def _young():
    return api._LAST_GOOD_MAX_AGE_SECONDS - 60


def _ancient():
    return api._LAST_GOOD_MAX_AGE_SECONDS + 60


# --- the bound itself -------------------------------------------------------


def test_a_recent_last_good_is_still_served_when_the_fetch_fails():
    """The behaviour that must survive: a blip is not an outage. P0-4 chose not
    to mark this payload degraded precisely so a five-second backend stumble
    does not replace a working page with an error card."""
    _seed("lg1", {"vms": 16_892, "hosts": 900}, age_seconds=_young())

    out = api._api_cache_get_with_stale("lg1", _boom, EMPTY)

    assert out == {"vms": 16_892, "hosts": 900}
    assert not api.is_degraded(out), "real data, just a little old"


def test_a_last_good_past_the_bound_is_not_presented_as_data():
    """The defect. Same code path, same 404 — only the age differs."""
    _seed("lg2", {"vms": 16_892, "hosts": 900}, age_seconds=_ancient())

    out = api._api_cache_get_with_stale("lg2", _boom, EMPTY)

    assert api.is_degraded(out), "an endpoint that has been 404ing this long must say so"
    assert out.get("vms") != 16_892, "the stale figure must not survive into the fallback"


def test_the_bound_is_the_audits_number_and_is_tunable():
    """Named, not inlined: how long a figure may go unrefreshed before the page
    stops showing it is a product decision, and the person making it should be
    able to find and change it."""
    assert api._LAST_GOOD_MAX_AGE_SECONDS == 4 * api._SWR_TTL_SECONDS
    assert api._LAST_GOOD_MAX_AGE_SECONDS > api._SWR_TTL_SECONDS, (
        "a bound at or below the freshness window would discard every stale entry, "
        "which is the opposite of a last-good fallback"
    )


def test_an_entry_with_no_recorded_fetch_time_is_treated_as_too_old():
    """Unknown age reads as stale everywhere else in this module (see
    _age_is_fresh). An unbounded last-good is exactly what an unstamped entry
    would become if unknown counted as young."""
    cache_service.set("lg3", {"vms": 16_892})  # pre-upgrade bare value

    out = api._api_cache_get_with_stale("lg3", _boom, EMPTY)

    assert api.is_degraded(out)


def test_no_cached_entry_at_all_still_degrades():
    """Unchanged, restated so the new branch cannot swallow the old one."""
    out = api._api_cache_get_with_stale("lg4", _boom, EMPTY)

    assert api.is_degraded(out)


# --- the same rule where an empty fetch is masked by a stale one ------------


def test_a_recent_stale_entry_still_wins_over_an_empty_fetch():
    """_prefer_stale_over_empty_fetch exists because a fetch that succeeds with
    nothing in it is usually a backend still warming up, not a real emptying."""
    _seed("lg5", {"vms": 16_892}, age_seconds=_young())

    out = api._api_cache_get_with_stale("lg5", lambda: dict(EMPTY), EMPTY)

    assert out == {"vms": 16_892}


def test_an_ancient_stale_entry_does_not_mask_an_empty_fetch():
    """Past the bound the fetch's own answer is the better one — it is at least
    current. Same call, same empty response, different age."""
    _seed("lg6", {"vms": 16_892}, age_seconds=_ancient())

    out = api._api_cache_get_with_stale("lg6", lambda: dict(EMPTY), EMPTY)

    assert out == EMPTY, "an hours-old figure must not outrank a fresh measurement"


# --- and where a follower reads what its leader left behind -----------------


def test_a_follower_does_not_hand_back_an_ancient_entry(monkeypatch):
    """The follower path reads the cache directly after waiting out its leader.
    It is the same last-good, reached a different way, and needs the same bound."""
    monkeypatch.setattr(api, "_INFLIGHT_WAIT_SECONDS", 0.05)
    _seed("lg7", {"vms": 16_892}, age_seconds=_ancient())

    # A leader is already in flight for this key, so this call takes the follower
    # branch and waits on the leader's event rather than fetching.
    import threading

    api._inflight["lg7"] = threading.Event()
    try:
        out = api._api_cache_get_with_stale("lg7", _boom, EMPTY)
    finally:
        api._inflight.pop("lg7", None)

    assert api.is_degraded(out)


# --- the two paths whose pages cannot read a degraded marker ----------------
#
# P0-4 wired the degraded notice into five pages. The consumers of the inventory
# overview and sellable summary caches — crm_inventory_overview,
# crm_sellable_potential, dc_view, dc_summary_sellable — are not among them, so a
# marked payload would travel through them as data and buy nothing. The bound
# still applies; past it they get their existing "nothing" value instead.


def test_the_sellable_summary_stops_replaying_an_ancient_snapshot():
    """The live one. Unlike the overview cache, this path reaches its failure
    branch with a stale entry already in hand: a stale read falls through to a
    fetch, and a 404 there used to return the stale copy unmarked, forever."""
    _seed("lg8", {"sellable_vcpu": 4_096}, age_seconds=_ancient())

    out = api._api_cache_get_sellable_summary("lg8", _boom, "DC13")

    assert out == {}, "a snapshot this old must not be presented as a measurement"


def test_the_sellable_summary_still_covers_a_short_outage():
    """The behaviour being preserved: below the bound, last-good is the whole
    point of keeping the entry."""
    _seed("lg9", {"sellable_vcpu": 4_096}, age_seconds=_young())

    out = api._api_cache_get_sellable_summary("lg9", _boom, "DC13")

    assert out == {"sellable_vcpu": 4_096}


def test_the_sellable_summary_treats_an_unstamped_entry_as_too_old():
    cache_service.set("lg10", {"sellable_vcpu": 4_096})

    assert api._api_cache_get_sellable_summary("lg10", _boom, "DC13") == {}


def test_the_overview_failure_branch_is_bounded_too(monkeypatch):
    """Defensive rather than live, and worth saying so.

    The overview cache returns any entry it finds — fresh or stale — before it
    ever reaches a fetch, so its failure branches only run on a miss and the only
    entry they can find is one another worker published mid-fetch, which is by
    construction recent. Seeding an old one from inside the fetch is contrived;
    it pins the rule, not a scenario. The rule is what matters: every path in
    this module that hands back a cached payload after a failure applies the
    same bound, so the next one written inherits it.
    """
    def _fetch_then_fail():
        _seed("lg11", {"vms": 16_892}, age_seconds=_ancient())
        return _boom()

    assert api._api_cache_get_inventory_overview("lg11", _fetch_then_fail) == {}


def test_the_overview_follower_branch_is_bounded_too(monkeypatch):
    """Same rule on the branch a follower takes after waiting out its leader."""
    import threading

    monkeypatch.setattr(api, "_INFLIGHT_WAIT_SECONDS", 0.05)
    _seed("lg12", {"vms": 16_892}, age_seconds=_ancient())
    monkeypatch.setattr(api, "_age_is_fresh", lambda age: False)
    # A stale entry would normally be served by the SWR branch above; suppress
    # that so the follower branch is the one under test.
    monkeypatch.setattr(api, "_schedule_inventory_swr_refresh", lambda *a, **k: None)
    api._inflight["lg12"] = threading.Event()
    try:
        # The overview cache serves any stale entry it finds, so reach the
        # follower branch the only way it is reachable: with the entry hidden
        # from the fast path.
        real_load = api._cache_load
        seen = {"n": 0}

        def _load(key):
            if key == "lg12":
                seen["n"] += 1
                if seen["n"] == 1:
                    return None, None  # the fast path sees a miss
            return real_load(key)

        monkeypatch.setattr(api, "_cache_load", _load)
        out = api._api_cache_get_inventory_overview("lg12", lambda: {"vms": 1})
    finally:
        api._inflight.pop("lg12", None)

    assert out == {}
