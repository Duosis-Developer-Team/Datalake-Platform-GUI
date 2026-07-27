"""The unmapped payload is cached on both sides, and every cache_set also writes
a 24h ``:last_good`` shadow key. When the primary key expires, cache_get returns
the shadow as a HIT (app/core/cache_backend.py:107-112), so run_singleflight
never sees a miss and never recomputes.

That is fine for staleness, but it means a payload whose SHAPE changed on deploy
keeps being served in its old shape for up to 24 hours, and nothing reports it.
It happened: after the Backup tab shipped, the endpoint served a 15-hour-old
VM-only payload — no ``kind``, no ``guessed_owner_id`` — so the İŞLEM column
rendered empty on every row and the Backup tab read 0.

The fix is the convention this codebase already uses for exactly this
(CUSTOMER_ASSETS_CACHE_VERSION, CRM_SALES_CACHE_VERSION): a version token inside
the key, so bumping it makes every old entry — primary AND shadow — unreachable.
"""
from shared.customer.cache_keys import (
    UNMAPPED_PAYLOAD_CACHE_VERSION,
    unmapped_payload_cache_key,
)

_START = "2026-07-21T00:00:00+00:00"
_END = "2026-07-27T23:59:59+00:00"


def test_key_carries_the_version_token():
    key = unmapped_payload_cache_key(_START, _END)
    assert UNMAPPED_PAYLOAD_CACHE_VERSION in key
    assert _START in key and _END in key


def test_bumping_the_version_makes_the_old_entry_unreachable():
    """The whole point: a shape change must not be able to hit the old shadow key."""
    import shared.customer.cache_keys as ck

    before = unmapped_payload_cache_key(_START, _END)
    original = ck.UNMAPPED_PAYLOAD_CACHE_VERSION
    try:
        ck.UNMAPPED_PAYLOAD_CACHE_VERSION = "some-later-shape"
        after = ck.unmapped_payload_cache_key(_START, _END)
    finally:
        ck.UNMAPPED_PAYLOAD_CACHE_VERSION = original

    assert before != after


def test_distinct_windows_still_get_distinct_keys():
    other_end = "2026-07-26T23:59:59+00:00"
    assert unmapped_payload_cache_key(_START, _END) != unmapped_payload_cache_key(_START, other_end)


def test_the_gui_response_cache_key_carries_the_same_token():
    """The GUI caches the same payload separately. A hardcoded copy of the key
    here is what already bit _customer_resources_ck once — same token, one bump."""
    from src.services import api_client

    ck = api_client._unmapped_resources_ck({"preset": "7d"})
    assert UNMAPPED_PAYLOAD_CACHE_VERSION in ck
    assert ck.startswith("api:unmapped_resources:")


def test_the_gui_invalidation_still_matches_the_versioned_key():
    """_invalidate_customer_views_cache drops by prefix; a version token inserted
    after the prefix must not slip out from under it."""
    from src.services import api_client

    ck = api_client._unmapped_resources_ck({"preset": "7d"})
    api_client._api_response_cache.set(ck, {"rows": []})
    assert api_client._api_response_cache.get(ck) is not None

    api_client._invalidate_customer_views_cache()

    assert api_client._api_response_cache.get(ck) is None
