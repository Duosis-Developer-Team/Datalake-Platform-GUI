"""Customer Backup Sales Position cards — sold vs used vs needs-to-sell."""
from __future__ import annotations

from typing import Any

import dash_mantine_components as dmc
from dash import html

_BRAND = "#4318FF"
_TEXT = "#2B3674"
_MUTED = "#A3AED0"
_DANGER = "#E03131"
_OK = "#12B886"
_TRACK = "#E9EDF7"


def _f(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def sales_position_metrics(
    *,
    sold: float,
    used: float,
    unit: str = "GB",
) -> dict[str, Any]:
    """Pure metrics for Sales Position (pre-dedup / replica footprint used)."""
    sold_f = max(0.0, _f(sold))
    used_f = max(0.0, _f(used))
    needs = max(0.0, used_f - sold_f)
    headroom = max(0.0, sold_f - used_f)
    eff = round((used_f / sold_f) * 100.0, 1) if sold_f > 0 else None
    return {
        "sold": sold_f,
        "used": used_f,
        "needs_to_sell": needs,
        "headroom": headroom,
        "efficiency_pct": eff,
        "unit": unit,
        "has_signal": sold_f > 0 or used_f > 0,
    }


def _position_bar(*, sold: float, used: float) -> html.Div:
    """Sold / used / overage segment bar (visual, not exact scale)."""
    ceiling = max(sold, used, 1.0)
    sold_pct = min(100.0, (sold / ceiling) * 100.0)
    used_pct = min(100.0, (used / ceiling) * 100.0)
    over_pct = max(0.0, used_pct - sold_pct)
    return html.Div(
        style={
            "position": "relative",
            "height": "10px",
            "borderRadius": "6px",
            "background": _TRACK,
            "overflow": "hidden",
            "marginTop": "8px",
            "marginBottom": "4px",
        },
        children=[
            html.Div(
                style={
                    "position": "absolute",
                    "left": 0,
                    "top": 0,
                    "bottom": 0,
                    "width": f"{sold_pct:.2f}%",
                    "background": _BRAND,
                    "opacity": 0.35,
                }
            ),
            html.Div(
                style={
                    "position": "absolute",
                    "left": 0,
                    "top": 0,
                    "bottom": 0,
                    "width": f"{min(used_pct, sold_pct):.2f}%",
                    "background": _BRAND,
                }
            ),
            html.Div(
                style={
                    "position": "absolute",
                    "left": f"{sold_pct:.2f}%",
                    "top": 0,
                    "bottom": 0,
                    "width": f"{over_pct:.2f}%",
                    "background": _DANGER,
                }
            )
            if over_pct > 0.05
            else html.Div(),
        ],
    )


def _basis_tile(
    *,
    title: str,
    used: float,
    sold: float,
    unit: str,
    authoritative: bool = False,
) -> html.Div:
    delta = used - sold
    delta_label = f"Needs {abs(delta):,.2f}" if delta > 0 else f"Headroom {abs(delta):,.2f}"
    delta_color = _DANGER if delta > 0 else _OK
    children: list = [
        dmc.Group(
            justify="space-between",
            align="center",
            children=[
                dmc.Text(title, size="xs", fw=700, c=_TEXT),
                dmc.Badge(
                    "Billing basis" if authoritative else "Comparison",
                    size="xs",
                    variant="light",
                    color="indigo" if authoritative else "gray",
                ),
            ],
        ),
        dmc.Text(f"Used {used:,.2f} {unit}", size="xs", c=_MUTED, mt=4),
        dmc.Text(delta_label, size="xs", fw=600, c=delta_color, mt=2),
    ]
    return html.Div(
        style={
            "padding": "12px",
            "borderRadius": "12px",
            "background": "#F4F7FE",
            "border": f"1px solid {'#4318FF33' if authoritative else '#E9EDF7'}",
        },
        children=children,
    )


def build_sales_position_card(
    *,
    title: str,
    sold: float,
    used: float,
    unit: str = "GB",
    subtitle: str | None = None,
    basis_badge: str | None = "Billing basis: Pre-dedup",
    netbackup_basis: dict[str, Any] | None = None,
    container_id: str | None = None,
) -> html.Div:
    """Sales Position card: needs-to-sell / headroom + KPI strip + optional NetBackup basis tiles."""
    m = sales_position_metrics(sold=sold, used=used, unit=unit)
    if not m["has_signal"]:
        return html.Div()

    if m["needs_to_sell"] > 0:
        headline = dmc.Group(
            gap="sm",
            align="center",
            children=[
                dmc.Text(
                    f"Needs to be sold: {m['needs_to_sell']:,.2f} {unit}",
                    fw=800,
                    size="lg",
                    c=_DANGER,
                ),
                dmc.Badge(basis_badge, variant="light", color="red", size="sm")
                if basis_badge
                else html.Div(),
            ],
        )
    else:
        headline = dmc.Group(
            gap="sm",
            align="center",
            children=[
                dmc.Text(
                    f"Headroom: {m['headroom']:,.2f} {unit}",
                    fw=800,
                    size="lg",
                    c=_OK,
                ),
                dmc.Badge(basis_badge, variant="light", color="teal", size="sm")
                if basis_badge
                else html.Div(),
            ],
        )

    eff_txt = f"{m['efficiency_pct']:.1f}%" if m["efficiency_pct"] is not None else "—"
    kpi_strip = dmc.SimpleGrid(
        cols={"base": 2, "sm": 4},
        spacing="sm",
        mt="md",
        children=[
            _mini_kpi("Sold (CRM)", f"{m['sold']:,.2f} {unit}"),
            _mini_kpi("Used", f"{m['used']:,.2f} {unit}"),
            _mini_kpi(
                "Delta",
                (
                    f"+{m['needs_to_sell']:,.2f}"
                    if m["needs_to_sell"] > 0
                    else f"-{m['headroom']:,.2f}"
                ),
                color=_DANGER if m["needs_to_sell"] > 0 else _OK,
            ),
            _mini_kpi("Efficiency", eff_txt),
        ],
    )

    body: list = [
        dmc.Text(title, size="sm", fw=700, c=_TEXT),
        dmc.Text(subtitle, size="xs", c=_MUTED, mt=2) if subtitle else html.Div(),
        headline,
        kpi_strip,
        _position_bar(sold=m["sold"], used=m["used"]),
        dmc.Text(
            "Bar: indigo = sold capacity · darker = used within sold · red = overage",
            size="xs",
            c=_MUTED,
        ),
    ]

    if netbackup_basis:
        pre = _f(netbackup_basis.get("pre"))
        post = _f(netbackup_basis.get("post"))
        margin = max(pre - post, 0.0)
        sold_f = m["sold"]
        ratio = netbackup_basis.get("dedup_ratio") or "—"
        body.extend(
            [
                dmc.Text("Basis comparison", size="xs", fw=700, c=_TEXT, mt="md", mb="xs"),
                dmc.SimpleGrid(
                    cols={"base": 1, "sm": 3},
                    spacing="sm",
                    children=[
                        _basis_tile(
                            title="Pre-dedup",
                            used=pre,
                            sold=sold_f,
                            unit=unit,
                            authoritative=True,
                        ),
                        _basis_tile(
                            title="Post-dedup",
                            used=post,
                            sold=sold_f,
                            unit=unit,
                        ),
                        _basis_tile(
                            title="Dedup margin",
                            used=margin,
                            sold=sold_f,
                            unit=unit,
                        ),
                    ],
                ),
                dmc.Text(f"Dedup ratio: {ratio}", size="xs", c=_MUTED, mt="xs"),
            ]
        )

    kwargs: dict[str, Any] = {
        "className": "nexus-card",
        "style": {"padding": "16px 20px", "marginBottom": "12px"},
        "children": body,
    }
    if container_id:
        kwargs["id"] = container_id
    return html.Div(**kwargs)


def _mini_kpi(label: str, value: str, *, color: str = _TEXT) -> html.Div:
    return html.Div(
        style={
            "padding": "10px 12px",
            "borderRadius": "10px",
            "background": "#F4F7FE",
        },
        children=[
            dmc.Text(label, size="xs", c=_MUTED, tt="uppercase"),
            dmc.Text(value, fw=700, size="sm", c=color, mt=2),
        ],
    )


def build_netbackup_sales_position_from_kpi_def(
    kpi_def: dict[str, Any] | None,
    *,
    dedup_ratio: str | None = None,
) -> html.Div:
    """Build Sales Position from ``build_netbackup_kpi_defs`` output."""
    d = kpi_def or {}
    if not d.get("has_signal"):
        return html.Div()
    sold = _f(d.get("sold"))
    used = _f(d.get("used_pre"))
    post = d.get("post")
    return build_sales_position_card(
        title=str(d.get("label") or "NetBackup"),
        sold=sold,
        used=used,
        unit="GiB",
        subtitle="CRM sold vs Pre-dedup usage (billing basis)",
        basis_badge="Billing basis: Pre-dedup",
        netbackup_basis={
            "pre": used,
            "post": _f(post) if post is not None else 0.0,
            "dedup_ratio": dedup_ratio,
        }
        if post is not None
        else None,
        container_id=f"cust-sales-pos-nb-{d.get('category') or 'nb'}",
    )


def build_replication_sales_position_card(
    *,
    vendor: str,
    sold_cpu: float,
    sold_ram: float,
    sold_disk: float,
    used_cpu: float,
    used_ram: float,
    used_disk: float,
) -> html.Div:
    """Stack of CPU/RAM/Disk Sales Position cards for one replication vendor."""
    label = "Veeam" if vendor == "veeam" else "Zerto" if vendor == "zerto" else vendor.title()
    cards = []
    for kind, unit, sold, used in (
        ("CPU", "vCPU", sold_cpu, used_cpu),
        ("RAM", "GB", sold_ram, used_ram),
        ("Storage", "GB", sold_disk, used_disk),
    ):
        card = build_sales_position_card(
            title=f"{label} Replication — {kind}",
            sold=sold,
            used=used,
            unit=unit,
            subtitle="CRM entitlement vs replica/DR VM footprint",
            basis_badge="Basis: Replica VM footprint",
            container_id=f"cust-sales-pos-{vendor}-{kind.lower()}",
        )
        if getattr(card, "children", None):
            cards.append(card)
    if not cards:
        return html.Div()
    return dmc.Stack(gap="sm", children=cards)
