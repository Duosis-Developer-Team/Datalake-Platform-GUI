"""Administration area route prefix and legacy /settings redirects."""

from __future__ import annotations

ADMIN_PREFIX = "/administration"
LEGACY_PREFIX = "/settings"


def to_administration_path(pathname: str) -> str:
    """Map legacy /settings URLs to /administration."""
    p = (pathname or ADMIN_PREFIX).rstrip("/") or ADMIN_PREFIX
    if p == LEGACY_PREFIX or p.startswith(f"{LEGACY_PREFIX}/"):
        suffix = p[len(LEGACY_PREFIX) :] or ""
        return ADMIN_PREFIX if not suffix else f"{ADMIN_PREFIX}{suffix}"
    return p
