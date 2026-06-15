"""Reusable sellable capacity visualizations with constraint explanations."""
from __future__ import annotations

from typing import Any

import dash_mantine_components as dmc
from dash import html
from dash_iconify import DashIconify

from src.utils.format_units import fmt_tl, fmt_tl_range

_BRAND = "#4318FF"
_MUTED = "#A3AED0"
_TEXT = "#2B3674"
_LOST = "#FFB547"
_SELLABLE = "#4318FF"
_ALLOC = "#A3AED0"

_CONSTRAINT_LABELS: dict[str, tuple[str, str]] = {
    "gate_blocked": ("Eşik aşıldı", "red"),
    "ratio_bound": ("Oran sınırı", "orange"),
    "compute_bottleneck": ("Compute darboğazı", "orange"),
    "none": ("", "gray"),
}

_BOTTLENECK_LABELS = {
    "cpu": "CPU",
    "ram": "RAM",
    "storage": "Storage",
}


def fmt_tl_for_card(
    tl_value: float | None,
    *,
    constrained: float | None = None,
) -> tuple[str, str]:
    """Return (short_label, tooltip_full). Hide TL when constrained capacity is zero."""
    if constrained is not None and float(constrained or 0) <= 1e-9:
        return "—", "Satılabilir kapasite sıfır — TL potansiyeli yok"
    if tl_value is None:
        return "—", ""
    v = float(tl_value or 0)
    if v <= 1e-9:
        return "—", "0 TL"
    full = f"{v:,.0f} TL"
    return fmt_tl(v), full


def count_constraint_breakdown(panels: list[dict]) -> dict[str, int]:
    """Count panels by constraint_reason for executive strip subtitles."""
    counts: dict[str, int] = {"gate_blocked": 0, "ratio_bound": 0, "compute_bottleneck": 0}
    for p in panels or []:
        if not isinstance(p, dict):
            continue
        reason = (p.get("constraint_reason") or "none").lower()
        if reason in counts:
            counts[reason] += 1
        elif p.get("gate_blocked"):
            counts["gate_blocked"] += 1
        elif p.get("ratio_bound") and reason == "none":
            counts["ratio_bound"] += 1
    return counts


def constraint_breakdown_text(panels: list[dict]) -> str | None:
    """Human-readable constraint summary for executive KPI subtitles."""
    counts = count_constraint_breakdown(panels)
    parts: list[str] = []
    if counts["compute_bottleneck"]:
        parts.append(f"{counts['compute_bottleneck']} compute darboğazı")
    if counts["ratio_bound"]:
        parts.append(f"{counts['ratio_bound']} oran sınırı")
    if counts["gate_blocked"]:
        parts.append(f"{counts['gate_blocked']} eşik engeli")
    if not parts:
        return None
    return " · ".join(parts)


def sellable_constraint_bar(
    total: float,
    allocated: float,
    sellable: float,
    *,
    sellable_raw: float | None = None,
    threshold_pct: float = 80.0,
    color: str = _BRAND,
) -> html.Div:
    """Stacked capacity bar: allocation fill, sellable marker, ratio-lost segment, threshold."""
    cap = max(float(total or 0), 1e-9)
    alloc_pct = min(100.0, 100.0 * float(allocated or 0) / cap)
    sell_pct = min(100.0, 100.0 * float(sellable or 0) / cap)
    raw = float(sellable_raw if sellable_raw is not None else sellable or 0)
    lost_pct = min(100.0, max(0.0, 100.0 * max(raw - float(sellable or 0), 0.0) / cap))
    thr_pct = min(float(threshold_pct or 80.0), 100.0)

    segments = [
        html.Div(style={
            "width": f"{alloc_pct}%", "height": "100%",
            "background": f"linear-gradient(90deg, {color}44, {color})",
            "position": "absolute", "left": 0, "top": 0,
        }),
    ]
    if lost_pct > 0.5:
        left = min(alloc_pct + sell_pct, 99.0)
        segments.append(html.Div(style={
            "width": f"{lost_pct}%", "height": "100%",
            "background": _LOST,
            "opacity": 0.65,
            "position": "absolute", "left": f"{left}%", "top": 0,
        }))

    return html.Div(style={"marginTop": "8px"}, children=[
        html.Div(style={
            "position": "relative", "height": "10px", "borderRadius": "6px",
            "background": "#E9EDF7", "overflow": "hidden",
        }, children=[
            *segments,
            html.Div(style={
                "position": "absolute", "left": f"{thr_pct}%", "top": 0, "bottom": 0,
                "width": "2px", "background": "#E53E3E",
            }),
        ]),
        dmc.Group(gap="md", mt=6, children=[
            dmc.Text(f"Cap: {total:,.0f}", size="xs", c="dimmed"),
            dmc.Text(f"Alloc: {allocated:,.0f}", size="xs", c="dimmed"),
            dmc.Text(f"Sellable: {sellable:,.0f}", size="xs", c="blue", fw=600),
        ]),
    ])


def sellable_constraint_badges(panel: dict[str, Any] | None, *, kind_label: str = "") -> list:
    """Build dmc.Badge children explaining why sellable is below raw."""
    if not panel:
        return []
    badges: list = []
    prefix = f"{kind_label} " if kind_label else ""
    reason = (panel.get("constraint_reason") or "none").lower()

    if panel.get("gate_blocked") or reason == "gate_blocked":
        badges.append(dmc.Badge(
            f"{prefix}eşik aşıldı — satılabilir kapasite sıfır",
            color="red", variant="light", size="sm",
        ))
    elif reason == "compute_bottleneck":
        bk = _BOTTLENECK_LABELS.get(panel.get("bottleneck_kind") or "", "Compute")
        badges.append(dmc.Badge(
            f"{prefix}compute darboğazı ({bk}) — storage/compute oranı",
            color="orange", variant="light", size="sm",
        ))
    elif panel.get("ratio_bound") or reason == "ratio_bound":
        raw = float(panel.get("sellable_raw") or 0)
        constrained = float(panel.get("sellable_constrained") or 0)
        if raw > constrained + 1e-6:
            unit = panel.get("display_unit") or ""
            lost = raw - constrained
            badges.append(dmc.Badge(
                f"{prefix}oran sınırı: {lost:,.0f} {unit} kayıp",
                color="orange", variant="light", size="sm",
            ))
    return badges


def storage_capacity_text(panel: dict[str, Any] | None) -> str:
    """Format storage sellable as range or single constrained value."""
    if not panel:
        return "—"
    lo, hi = panel.get("sellable_min"), panel.get("sellable_max")
    unit = panel.get("display_unit") or "GB"
    if lo is not None and hi is not None and abs(float(hi) - float(lo)) > 1e-6:
        return f"{float(lo):,.0f} – {float(hi):,.0f} {unit}"
    return f"{float(panel.get('sellable_constrained') or 0):,.0f} {unit}"


def _storage_bottleneck_tooltip(panel: dict[str, Any] | None) -> str:
    if not panel:
        return ""
    units = panel.get("bottleneck_units")
    constrained = float(panel.get("sellable_constrained") or 0)
    if units is None or constrained <= 1e-9:
        return ""
    bk = _BOTTLENECK_LABELS.get(panel.get("bottleneck_kind") or "", "Compute")
    return f"{float(units):,.0f} effective {bk} unit(s) — storage capped at {constrained:,.0f} GB"


def build_storage_family_tile(
    panel: dict[str, Any] | None,
    *,
    label: str,
    color: str = "blue",
    kind_label: str = "",
) -> html.Div:
    """Summary storage tile: capacity, TL range, constraint badges, optional tooltip."""
    constrained = float((panel or {}).get("sellable_constrained") or 0)
    tl_min = (panel or {}).get("potential_tl_min")
    tl_max = (panel or {}).get("potential_tl_max")
    tl_value = (panel or {}).get("potential_tl")

    if tl_min is not None and tl_max is not None and abs(float(tl_max) - float(tl_min)) > 1e-6:
        if constrained <= 1e-9:
            tl_short, tl_full = "—", "Satılabilir kapasite sıfır — TL potansiyeli yok"
        else:
            tl_short = fmt_tl_range(float(tl_min), float(tl_max))
            tl_full = f"{float(tl_min):,.0f} – {float(tl_max):,.0f} TL"
    else:
        tl_short, tl_full = fmt_tl_for_card(
            float(tl_value) if tl_value is not None else None,
            constrained=constrained,
        )

    tooltip = _storage_bottleneck_tooltip(panel) or tl_full
    badge_label = kind_label or label

    return html.Div(
        title=tooltip if tooltip and tooltip != tl_short else None,
        children=[
            dmc.Text(label, fw=600, size="sm"),
            dmc.Text(storage_capacity_text(panel), size="lg", fw=800, c=color),
            dmc.Text(tl_short, size="xs", c="dimmed"),
            dmc.Group(
                gap="xs",
                mt="xs",
                children=sellable_constraint_badges(panel, kind_label=badge_label),
            ),
        ],
    )


def sellable_resource_card(
    label: str,
    capacity_text: str,
    *,
    tl_value: float | None = None,
    constrained: float | None = None,
    tl_min: float | None = None,
    tl_max: float | None = None,
    icon: str = "solar:cpu-bolt-bold-duotone",
    color: str = "violet",
    tooltip: str = "",
) -> html.Div:
    """Single sellable KPI card with conditional TL row."""
    if tl_min is not None and tl_max is not None and abs(float(tl_max) - float(tl_min)) > 1e-6:
        if constrained is not None and float(constrained or 0) <= 1e-9:
            tl_short, tl_full = "—", "Satılabilir kapasite sıfır"
        else:
            tl_short = fmt_tl_range(tl_min, tl_max)
            tl_full = f"{float(tl_min):,.0f} – {float(tl_max):,.0f} TL"
    else:
        tl_short, tl_full = fmt_tl_for_card(tl_value, constrained=constrained)

    tip = tooltip or tl_full
    return html.Div(
        className="nexus-card dc-kpi-card",
        style={"padding": "18px", "minHeight": "130px"},
        title=tip if tip and tip != tl_short else None,
        children=[
            dmc.Group(justify="space-between", align="flex-start", children=[
                html.Div([
                    html.Span(label, style={
                        "color": _MUTED, "fontSize": "0.75rem",
                        "textTransform": "uppercase",
                    }),
                    html.H3(capacity_text, style={
                        "color": _TEXT, "fontWeight": 900, "margin": "8px 0 4px",
                        "fontSize": "1.05rem",
                    }),
                    html.Span(tl_short, style={
                        "color": _BRAND, "fontSize": "0.78rem", "fontWeight": 600,
                    }),
                ]),
                dmc.ThemeIcon(size=42, radius="xl", variant="light", color=color,
                              children=DashIconify(icon=icon, width=22)),
            ]),
        ],
    )
