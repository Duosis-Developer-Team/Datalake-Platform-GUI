"""Extract datacenter codes from free-text backup/replication fields.

Shared by datacenter-api (DC-scoped filtering) and GUI unique-job row annotation
so customer/DC views use the same DCxx / AZxx / ICTxx / UZxx / DHxx grammar.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

_DC_CODE_RE = re.compile(r"(DC\d+|AZ\d+|ICT\d+|UZ\d+|DH\d+)", re.IGNORECASE)

# Prefer site/host labels that already embed a DC code; source_ip alone never matches.
_DC_TEXT_FIELDS = (
    "source_site",
    "target_site",
    "zerto_host",
    "destinationmediaservername",
    "host_name",
    "repository_name",
    "clientname",
    "name",
)


def extract_dc_code(value: str | None, dc_set: Iterable[str] | None = None) -> str | None:
    """Return the first DC-like token in ``value`` (uppercased), optionally constrained."""
    if not value:
        return None
    match = _DC_CODE_RE.search(str(value).upper())
    if not match:
        return None
    code = match.group(1).upper()
    if dc_set is None:
        return code
    allowed = {str(c).upper() for c in dc_set}
    return code if code in allowed else None


def annotate_unique_job_dc(row: dict[str, Any] | None) -> dict[str, Any]:
    """Shallow-copy ``row`` and set ``dc`` from the first matching text field."""
    out = dict(row or {})
    if out.get("dc"):
        out["dc"] = str(out["dc"]).strip().upper() or out.get("dc")
        return out
    for key in _DC_TEXT_FIELDS:
        code = extract_dc_code(out.get(key))
        if code:
            out["dc"] = code
            return out
    return out


def annotate_unique_job_dcs(rows: list[dict] | None) -> list[dict]:
    return [annotate_unique_job_dc(r) for r in (rows or [])]


def collect_datacenter_codes(rows: Iterable[dict] | None) -> list[str]:
    """Sorted unique DC codes present on annotated unique-job rows."""
    codes: set[str] = set()
    for row in rows or []:
        code = str((row or {}).get("dc") or "").strip().upper()
        if code:
            codes.add(code)
    return sorted(codes)
