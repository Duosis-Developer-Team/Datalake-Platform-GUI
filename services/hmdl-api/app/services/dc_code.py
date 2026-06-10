"""Extract infrastructure site codes from Loki location names."""

from __future__ import annotations

import re

_DC_CODE_RE = re.compile(r"(DC|AZ|ICT|UZ)\d+", re.IGNORECASE)


def extract_dc_code(site_or_name: str | None) -> str:
    """Extract DC13-style code from a NetBox location or site name."""
    if not site_or_name:
        return ""
    match = _DC_CODE_RE.search(str(site_or_name))
    return match.group(0).upper() if match else ""
