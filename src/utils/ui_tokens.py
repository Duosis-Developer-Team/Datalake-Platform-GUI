"""Shared UI helpers for Settings and Query Explorer (DMC + DashIconify)."""

from __future__ import annotations

from typing import Any

import dash_mantine_components as dmc
from dash import html
from dash_iconify import DashIconify

# Brand palette (aligned with product identity)
PRIMARY = "#552cf8"
PRIMARY_END = "#a092ff"
BG_PAGE = "#f5f6f9"
ON_SURFACE = "#2c2f31"
ON_DIM = "#595c5e"

# Standardized table header style used across all settings pages
_TH_STYLE_BASE: dict[str, Any] = {
    "fontSize": "11px",
    "fontWeight": 600,
    "textTransform": "uppercase",
    "letterSpacing": "0.05em",
    "color": "#6c757d",
    "padding": "8px 12px",
    "borderBottom": "1px solid #eef1f4",
}


def th_left() -> dict[str, Any]:
    return {**_TH_STYLE_BASE, "textAlign": "left"}


def th_center() -> dict[str, Any]:
    return {**_TH_STYLE_BASE, "textAlign": "center"}


def card_style(
    *,
    border_left: str | None = None,
    padding: str = "md",
) -> dict[str, Any]:
    """Paper-style container props for dmc.Paper."""
    style: dict[str, Any] = {
        "borderRadius": "12px",
        "boxShadow": "0 4px 24px rgba(44, 47, 49, 0.06)",
        "background": "#ffffff",
        "border": "1px solid rgba(171, 173, 176, 0.15)",
    }
    if border_left:
        style["borderLeft"] = f"4px solid {border_left}"
    return {"p": padding, "radius": "md", "withBorder": True, "style": style}


def gradient_button_style() -> dict[str, Any]:
    return {
        "background": f"linear-gradient(135deg, {PRIMARY} 0%, {PRIMARY_END} 100%)",
        "border": "none",
        "color": "#fff",
        "fontWeight": 600,
        "transition": "opacity 0.18s ease, box-shadow 0.18s ease",
    }


def html_submit_button_gradient(
    label: str,
    *,
    icon: str | None = None,
    style_extra: dict[str, Any] | None = None,
) -> html.Button:
    """Native HTML submit button with gradient styling.

    Uses html.Button instead of dmc.Button because DMC's Button does not
    accept ``type='submit'`` in older 0.14.x releases.
    """
    base: dict[str, Any] = {
        **gradient_button_style(),
        "cursor": "pointer",
        "padding": "10px 20px",
        "borderRadius": "10px",
        "display": "inline-flex",
        "alignItems": "center",
        "gap": "8px",
        "fontSize": "14px",
        "fontFamily": "inherit",
        "boxShadow": "0 2px 8px rgba(85, 44, 248, 0.25)",
    }
    if style_extra:
        base.update(style_extra)
    if icon:
        return html.Button(
            [DashIconify(icon=icon, width=18), label],
            type="submit",
            style=base,
        )
    return html.Button(label, type="submit", style=base)


def html_submit_button_light(
    label: str,
    *,
    scheme: str = "gray",
    small: bool = False,
    style_extra: dict[str, Any] | None = None,
) -> html.Button:
    """Light-style native submit for filters and inline actions."""
    schemes: dict[str, dict[str, str]] = {
        "gray": {"background": "#f8f9fa", "color": "#495057", "border": "1px solid #dee2e6"},
        "red": {"background": "#fff5f5", "color": "#fa5252", "border": "1px solid #ffc9c9"},
        "indigo": {"background": "#f3f0ff", "color": "#552cf8", "border": "1px solid #d0bfff"},
    }
    s = schemes.get(scheme, schemes["gray"])
    base: dict[str, Any] = {
        **s,
        "cursor": "pointer",
        "borderRadius": "10px",
        "fontFamily": "inherit",
        "fontWeight": 500,
        "padding": "6px 12px" if small else "8px 16px",
        "fontSize": "12px" if small else "13px",
        "transition": "opacity 0.18s ease",
    }
    if style_extra:
        base.update(style_extra)
    return html.Button(label, type="submit", style=base)


def status_badge(label: str, variant: str = "light", color: str = "gray") -> dmc.Badge:
    """Map semantic status to Mantine badge."""
    color_map = {
        "active": "green",
        "inactive": "gray",
        "connected": "green",
        "disconnected": "gray",
        "degraded": "orange",
        "draft": "yellow",
        "success": "indigo",
        "warning": "orange",
        "error": "red",
    }
    c = color_map.get(variant, color)
    return dmc.Badge(label.upper(), variant=variant, color=c, size="sm", radius="xl")


def section_header(title: str, subtitle: str | None = None, icon: str | None = None) -> html.Div:
    """Page section title row with optional icon and subtitle."""
    left: list = []
    if icon:
        left.append(
            dmc.ThemeIcon(
                DashIconify(icon=icon, width=20),
                size="lg",
                radius="md",
                variant="light",
                color="indigo",
            )
        )
    left.append(
        dmc.Stack(
            gap=2,
            children=[
                dmc.Text(title, fw=800, size="lg", c=ON_SURFACE),
                dmc.Text(subtitle, size="xs", c=ON_DIM) if subtitle else None,
            ],
        )
    )
    return html.Div(
        dmc.Group(gap="md", align="flex-start", children=left),
        style={"marginBottom": "16px"},
    )


def kpi_card(
    label: str,
    value: str | int,
    *,
    icon: str | None = None,
    trend: str | None = None,
    color: str = "indigo",
) -> dmc.Paper:
    """Compact KPI metric tile."""
    top = dmc.Group(
        justify="space-between",
        align="flex-start",
        children=[
            dmc.Stack(
                gap=4,
                children=[
                    dmc.Text(label.upper(), size="xs", fw=700, c="dimmed", style={"letterSpacing": "0.06em"}),
                    dmc.Text(str(value), fw=900, size="xl", c=PRIMARY),
                ],
            ),
            dmc.ThemeIcon(
                DashIconify(icon=icon or "solar:chart-bold-duotone", width=22),
                size="xl",
                radius="md",
                variant="light",
                color=color,
            )
            if icon
            else html.Div(),
        ],
    )
    children: list = [top]
    if trend:
        children.append(dmc.Text(trend, size="xs", c="dimmed", mt=4))
    return dmc.Paper(
        children=children,
        **card_style(),
    )


def section_nav_card(
    title: str,
    description: str,
    href: str,
    *,
    icon: str = "solar:widget-bold-duotone",
    badges: list[str] | None = None,
) -> dmc.Card:
    """Clickable landing card linking to a settings area."""
    badge_row = (
        dmc.Group(
            gap="xs",
            children=[dmc.Badge(b, size="xs", variant="light", color="indigo") for b in badges],
        )
        if badges
        else None
    )
    inner = dmc.Stack(
        gap="sm",
        children=[
            dmc.Group(
                children=[
                    dmc.ThemeIcon(
                        DashIconify(icon=icon, width=26, color="#fff"),
                        size="xl",
                        radius="md",
                        variant="filled",
                        color="indigo",
                        style={
                            "background": f"linear-gradient(135deg, {PRIMARY} 0%, {PRIMARY_END} 100%)",
                            "border": "none",
                        },
                    ),
                    dmc.Stack(
                        gap=4,
                        children=[
                            dmc.Text(title, fw=800, size="lg", c=ON_SURFACE),
                            dmc.Text(description, size="sm", c=ON_DIM),
                        ],
                    ),
                ],
                align="flex-start",
            ),
            badge_row,
            dmc.Anchor(
                dmc.Button(
                    "Open",
                    variant="light",
                    color="indigo",
                    size="xs",
                    radius="md",
                    styles={"root": {"transition": "opacity 0.18s ease"}},
                ),
                href=href,
                underline=False,
            ),
        ],
    )
    return dmc.Card(
        withBorder=True,
        radius="md",
        p="lg",
        style={
            "border": "1px solid rgba(171, 173, 176, 0.2)",
            "boxShadow": "0 8px 28px rgba(85, 44, 248, 0.08)",
            "background": "#fff",
            "transition": "box-shadow 0.2s ease",
        },
        children=[inner],
    )


def settings_page_shell(children: list, *, max_width: str = "1280px") -> html.Div:
    """Outer wrapper for settings content with consistent max-width."""
    return html.Div(
        style={"maxWidth": max_width, "margin": "0 auto", "paddingBottom": "48px"},
        children=children,
    )


def relative_time(ts) -> str:
    """Human-readable relative time from a datetime-like value."""
    if ts is None:
        return "—"
    try:
        from datetime import datetime, timezone

        if isinstance(ts, str):
            s = ts.replace("Z", "+00:00")
            try:
                ts = datetime.fromisoformat(s)
            except ValueError:
                return ts[:19]
        if hasattr(ts, "tzinfo") and getattr(ts, "tzinfo", None) is None:
            ts = ts.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - ts
        sec = int(delta.total_seconds())
        if sec < 60:
            return f"{sec}s ago"
        if sec < 3600:
            return f"{sec // 60}m ago"
        if sec < 86400:
            return f"{sec // 3600}h ago"
        return f"{sec // 86400}d ago"
    except Exception:
        return str(ts)[:19]
