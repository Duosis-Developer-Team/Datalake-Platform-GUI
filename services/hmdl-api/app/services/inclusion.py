"""Map collector targets to inclusion categories for Sync Health UI."""

from __future__ import annotations

from typing import Any

INCLUSION_CATEGORIES = (
    "monitored",
    "not_monitored",
    "customer_environment",
    "connectivity_issue",
    "missing_from_loki",
    "pending_distribution",
)


def normalize_platform_status(extra: Any) -> str | None:
    if extra is None:
        return None
    if isinstance(extra, dict):
        ps = extra.get("platform_status")
        if ps is None:
            return None
        return str(ps).strip().lower() or None
    return None


def inclusion_from_platform_status(platform_status: str | None) -> str:
    ps = (platform_status or "").lower()
    if ps in ("not_monitored",):
        return "not_monitored"
    if ps in ("customer_environment",):
        return "customer_environment"
    return "monitored"


def classify_target(
    *,
    extra: Any,
    has_connectivity_fail: bool,
    removed_in_last_run: bool,
    pending_distribution: bool,
) -> str:
    if removed_in_last_run:
        return "missing_from_loki"
    if has_connectivity_fail:
        return "connectivity_issue"
    if pending_distribution:
        return "pending_distribution"
    return inclusion_from_platform_status(normalize_platform_status(extra))
