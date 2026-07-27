"""Shared Redis / in-process cache key helpers for customer asset bundles."""

from __future__ import annotations

# Bump when customer assets JSON shape changes (e.g. Real CPU enrichment fields).
# v4: backup.netbackup gained image/application/policy_types (policy-based IA).
CUSTOMER_ASSETS_CACHE_VERSION = "netbackup-policy-v4"


def customer_assets_cache_key(customer_name: str, start: str, end: str) -> str:
    return f"customer_assets:{CUSTOMER_ASSETS_CACHE_VERSION}:{customer_name}:{start}:{end}"


# Bump when the Eşleşmeyen Veriler payload shape changes.
# v2: rows gained guessed_owner_id / suggested_alias / suggested_method / kind,
#     and the payload gained ambiguous_count, when the Backup tab shipped.
#
# This token is not optional bookkeeping. Every cache_set also writes a 24h
# ":last_good" shadow key, and cache_get returns that shadow as a HIT when the
# primary key expires (app/core/cache_backend.py:107-112) — so run_singleflight
# never sees a miss and never recomputes. Without a token in the key, a deploy
# that changes the payload shape keeps serving the OLD shape for up to a day
# with nothing to signal it. That is exactly what happened when the Backup tab
# shipped: the endpoint served a 15-hour-old VM-only payload, so every İŞLEM
# cell rendered empty and the Backup tab read 0.
UNMAPPED_PAYLOAD_CACHE_VERSION = "backup-tab-v2"


def unmapped_payload_cache_key(start: str, end: str) -> str:
    """Cache key for the unmapped (Eşleşmeyen Veriler) payload, both sides.

    Shared so the service and the GUI cannot disagree about the token — a
    hardcoded copy of the customer-assets key already caused that once.
    """
    return f"unmapped_resources:{UNMAPPED_PAYLOAD_CACHE_VERSION}:{start}:{end}"
