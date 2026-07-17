"""Shared Redis / in-process cache key helpers for customer asset bundles."""

from __future__ import annotations

# Bump when customer assets JSON shape changes (e.g. Real CPU enrichment fields).
# v4: backup.netbackup gained image/application/policy_types (policy-based IA).
CUSTOMER_ASSETS_CACHE_VERSION = "netbackup-policy-v4"


def customer_assets_cache_key(customer_name: str, start: str, end: str) -> str:
    return f"customer_assets:{CUSTOMER_ASSETS_CACHE_VERSION}:{customer_name}:{start}:{end}"
