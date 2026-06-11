from __future__ import annotations
"""NetBox-style datacenter display labels (short code + facility description)."""


def format_dc_display_name(name: str | None, description: str | None) -> str:
    """
    Return ``name - description`` when description is present and distinct from name.
    Otherwise return the short code/name only.
    """
    n = (name or "").strip()
    d = (description or "").strip()
    if not n:
        return d or ""
    if not d or d.casefold() == n.casefold():
        return n
    return f"{n} - {d}"


def resolve_dc_display_from_summary(dc_id: str, tr: dict | None) -> tuple[str, str]:
    """Resolve display label and location from cached datacenters summary list."""
    from src.services import api_client as api

    dc_id_s = str(dc_id or "").strip() or "Data Center"
    for dc in api.get_all_datacenters_summary(tr):
        rid = str(dc.get("id", "")).strip()
        if not rid:
            continue
        if rid.upper() == dc_id_s.upper():
            display = format_dc_display_name(dc.get("name"), dc.get("description"))
            loc = str(dc.get("location") or "").strip()
            return display or dc_id_s, loc
    return dc_id_s, ""
