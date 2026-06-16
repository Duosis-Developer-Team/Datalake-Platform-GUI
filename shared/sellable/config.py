"""Runtime configuration for sellable computation paths."""
from __future__ import annotations

import os


def host_based_sellable_enabled() -> bool:
    """Return True when per-host virt sellable (ADR-0017) is active."""
    return os.getenv("SELLABLE_HOST_BASED_ENABLED", "false").lower() in (
        "1",
        "true",
        "yes",
    )
