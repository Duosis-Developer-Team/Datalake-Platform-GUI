"""Single source of truth for customer alias match semantics.

Every consumer — the SQL pattern resolver, the unmapped classifier, and the
physical-inventory filter — derives its behaviour from here. The decision is
made once, from (data_source, method, value), and is never re-derived from a
pattern string further down the pipeline. Re-deriving intent from a pattern is
what made the implementations drift apart in the first place.

`exact` is expressed as a wildcard-free ILIKE: an ILIKE with no wildcards is a
case-insensitive equality test, identical to what predicate() does. That keeps a
single consumption path (ilike) instead of a second 'exact' bucket.
"""
from __future__ import annotations

from typing import Callable

TEXT_METHODS: tuple[str, ...] = ("contains", "prefix", "suffix", "exact")
ID_METHODS: tuple[str, ...] = ("id_exact",)
ALL_METHODS: tuple[str, ...] = TEXT_METHODS + ID_METHODS

DEFAULT_METHOD: str = "contains"

# Sources correlated by numeric tenant id rather than by name. A name-matching
# method here (or an id method on a name source) is a configuration error.
ID_SOURCES: tuple[str, ...] = ("physical_device", "auranotify")


def allowed_methods(data_source: str) -> tuple[str, ...]:
    """The methods that are meaningful for this data source."""
    return ID_METHODS if (data_source or "").strip() in ID_SOURCES else TEXT_METHODS


def is_allowed(data_source: str, method: str) -> bool:
    return (method or "").strip().lower() in allowed_methods(data_source)


def normalize_method(data_source: str, method: str) -> str:
    """Coerce a possibly-invalid method into a valid one for this source."""
    candidate = (method or "").strip().lower()
    if is_allowed(data_source, candidate):
        return candidate
    return ID_METHODS[0] if (data_source or "").strip() in ID_SOURCES else DEFAULT_METHOD


def escape_like(value: str) -> str:
    """Escape LIKE/ILIKE wildcards so the value matches literally.

    Postgres' default LIKE escape character is backslash, so no ESCAPE clause is
    needed — provided the result is passed as a bind parameter, never inlined.
    Backslash is escaped first so the later replacements are not re-escaped.
    """
    return (value or "").replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def sql_pattern(method: str, value: str) -> tuple[str, str]:
    """Return (kind, pattern): ('ilike', pattern) or ('id_exact', raw_value)."""
    cleaned = (value or "").strip()
    key = (method or DEFAULT_METHOD).strip().lower()
    if key == "id_exact":
        return "id_exact", cleaned
    escaped = escape_like(cleaned)
    if key == "exact":
        return "ilike", escaped
    if key == "prefix":
        return "ilike", f"{escaped}%"
    if key == "suffix":
        return "ilike", f"%{escaped}"
    return "ilike", f"%{escaped}%"


def predicate(method: str, value: str) -> Callable[[str], bool]:
    """In-memory counterpart of sql_pattern, with identical semantics.

    Case-insensitive, wildcard-free. id_exact never matches a name: it resolves
    through tenant ids, and contributes no name pattern on the SQL side either.

    The *value* is stripped, mirroring sql_pattern. The *name* is deliberately
    NOT stripped: ILIKE compares the column as stored, so stripping here would
    make `exact` match a trailing-space name that SQL rejects. Parity beats
    tidiness — the caller normalises the name if it wants that.
    """
    needle = (value or "").strip().lower()
    key = (method or DEFAULT_METHOD).strip().lower()

    if key == "id_exact" or not needle:
        return lambda name: False

    if key == "prefix":
        return lambda name: (name or "").lower().startswith(needle)
    if key == "suffix":
        return lambda name: (name or "").lower().endswith(needle)
    if key == "exact":
        return lambda name: (name or "").lower() == needle
    return lambda name: needle in (name or "").lower()
