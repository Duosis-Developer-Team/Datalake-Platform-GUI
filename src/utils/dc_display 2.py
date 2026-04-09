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
