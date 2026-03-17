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
        return "0 GB"
    gb = float(gb)
    if gb >= 1024:
        return f"{gb / 1024:.1f} TB"
    if gb >= 1:
        return f"{gb:.1f} GB"
    return f"{gb * 1024:.0f} MB"


def smart_memory(gb: float) -> str:
    """Format a memory value given in GB to the most appropriate unit string."""
    return smart_storage(gb)


def smart_cpu(ghz: float) -> str:
    """Format a CPU value given in GHz to the most appropriate unit string."""
    if ghz is None:
        return "0 GHz"
    ghz = float(ghz)
    if ghz >= 1:
        return f"{ghz:.1f} GHz"
    return f"{ghz * 1000:.0f} MHz"


def smart_bytes(value_bytes: float) -> str:
    """Format a raw byte value to the most appropriate unit string."""
    if value_bytes is None:
        return "0 B"
    value_bytes = float(value_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(value_bytes) < 1024.0:
            return f"{value_bytes:.1f} {unit}"
        value_bytes /= 1024.0
    return f"{value_bytes:.1f} PB"


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
