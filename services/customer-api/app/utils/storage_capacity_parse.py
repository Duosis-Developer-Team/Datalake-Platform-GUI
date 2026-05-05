"""Parse IBM SAN textual capacity fields (same semantics as datacenter-api format_units)."""

from __future__ import annotations

import re


def parse_storage_string_to_gb(value: str | None) -> float:
    """Parse strings like '110.00 TB' into GB (1024-based tiers)."""
    if value is None:
        return 0.0
    s = str(value)
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*(PB|TB|GB|MB)\b", s, flags=re.IGNORECASE)
    if not m:
        return 0.0
    num = float(m.group(1))
    unit = m.group(2).upper()
    factors_to_gb = {
        "PB": 1024 * 1024,
        "TB": 1024,
        "GB": 1,
        "MB": 1 / 1024,
    }
    return num * factors_to_gb.get(unit, 0.0)
