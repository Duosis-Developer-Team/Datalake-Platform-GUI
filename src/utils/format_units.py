from __future__ import annotations
# Unit formatting utilities for dynamic scaling.
# All display values should pass through these helpers so the UI
# automatically picks the most human-readable unit (MB / GB / TB, MHz / GHz).


def title_case(s):
    """Format string so only the first letter of each word is capitalized."""
    if s is None or not isinstance(s, str):
        return "" if s is None else str(s)
    s = s.strip()
    if not s:
        return s
    return " ".join(word.capitalize() for word in s.split())


def smart_storage(gb: float) -> str:
    """Format a storage value given in GB to the most appropriate unit string."""
    if gb is None:
        return "0.00 GB"
    gb = float(gb)
    if gb >= 1024:
        return f"{gb / 1024:.2f} TB"
    if gb >= 1:
        return f"{gb:.2f} GB"
    return f"{gb * 1024:.2f} MB"


def smart_memory(gb: float) -> str:
    """Format a memory value given in GB to the most appropriate unit string."""
    return smart_storage(gb)


def smart_cpu(ghz: float) -> str:
    """Format a CPU value given in GHz to the most appropriate unit string."""
    if ghz is None:
        return "0.00 GHz"
    ghz = float(ghz)
    if ghz >= 1:
        return f"{ghz:.2f} GHz"
    return f"{ghz * 1000:.2f} MHz"


def format_power_capacity_count(value: float | None) -> str:
    """Format IBM Power proc-unit / core counts as plain decimal numbers (not GHz)."""
    if value is None:
        return "0.00"
    return f"{float(value):,.2f}"


def smart_bytes(value_bytes: float) -> str:
    """Alias for base-1024 byte formatting."""
    return smart_bytes_1024(value_bytes)


def smart_bytes_1024(value_bytes: float) -> str:
    """Format a raw byte value (base 1024) to the most appropriate unit string."""
    if value_bytes is None:
        return "0.00 B"
    value = float(value_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(value) < 1024.0:
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{value:.2f} PB"


def smart_frequency_hz(value_hz: float) -> str:
    """Format a frequency value in Hz to the most appropriate unit string (base 1000)."""
    if value_hz is None:
        return "0.00 Hz"
    value = float(value_hz)
    for unit in ("Hz", "kHz", "MHz", "GHz", "THz"):
        if abs(value) < 1000.0:
            return f"{value:.2f} {unit}"
        value /= 1000.0
    return f"{value:.2f} THz"


def pct_str(used: float, cap: float) -> str:
    """Return '42.3%' string given used and capacity values (same unit)."""
    if not cap:
        return "0.0%"
    return f"{min(used / cap * 100, 100):.1f}%"


def pct_float(used: float, cap: float) -> float:
    """Return utilization percentage as a float 0–100."""
    if not cap:
        return 0.0
    return min(float(used) / float(cap) * 100, 100.0)


def parse_storage_string(value: str | None) -> float:
    """
    Parse a storage capacity string like '110.00 TB' into a float in GB.

    Supports units: PB, TB, GB, MB.
    Returns 0.0 when the input does not match the expected pattern.
    """
    import re

    if value is None:
        return 0.0

    s = str(value)
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*(PB|TB|GB|MB)\b", s, flags=re.IGNORECASE)
    if not m:
        return 0.0

    num = float(m.group(1))
    unit = m.group(2).upper()

    # Convert to GB using the same base as smart_storage (1024-based tiers).
    factors_to_gb = {
        "PB": 1024 * 1024,
        "TB": 1024,
        "GB": 1,
        "MB": 1 / 1024,
    }
    return num * factors_to_gb.get(unit, 0.0)
