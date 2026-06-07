"""Shared compliance / efficiency status badges for Customer View panels."""

from __future__ import annotations

import dash_mantine_components as dmc


def compliance_status_badge(status: str | None) -> dmc.Badge:
    """Badge for resource compliance and sold-vs-used rows."""
    s = (status or "unknown").lower()
    if s == "unsold_usage":
        return dmc.Badge("Unsold usage", color="red", variant="filled", size="sm")
    if s == "over":
        return dmc.Badge("Over-utilized", color="red", variant="light", size="sm")
    if s == "under":
        return dmc.Badge("Under-utilized", color="green", variant="light", size="sm")
    if s == "optimal":
        return dmc.Badge("Optimal", color="indigo", variant="light", size="sm")
    if s == "no_sales":
        return dmc.Badge("No CRM sales", color="gray", variant="light", size="sm")
    if s == "no_usage":
        return dmc.Badge("No usage", color="gray", variant="outline", size="sm")
    return dmc.Badge("N/A", color="gray", variant="outline", size="sm")
