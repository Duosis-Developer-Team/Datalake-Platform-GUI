"""Reusable colocation usage summary: KPI tiles + a 100% stacked bar showing
where a DC's used rack-U goes (External / Internal / Untagged). Used by the DC
Colocation tab and the Floor Map. English labels only."""
from __future__ import annotations

import dash_mantine_components as dmc
from dash import html

from src.utils.format_units import fmt_tl

_EXT_COLOR = "#F79009"  # orange — external customers
_INT_COLOR = "#528BFF"  # blue — Bulutistan internal
_UNT_COLOR = "#D0D5DD"  # grey — untagged / unattributable


def _tile(label: str, value: str):
    return dmc.Paper(radius="lg", p="md", withBorder=True, children=[
        dmc.Text(label, size="xs", c="#667085", fw=600),
        dmc.Text(value, size="xl", fw=800, c="#101828"),
    ])


def _tile_with_tip(label: str, value: str, tip: str):
    return dmc.Tooltip(
        label=tip, position="bottom", withArrow=True, multiline=True, w=280,
        children=_tile(label, value),
    )


def _swatch_label(color: str, text: str):
    return dmc.Group(gap=6, align="center", children=[
        html.Span(style={"width": "10px", "height": "10px", "borderRadius": "3px",
                         "background": color, "display": "inline-block"}),
        dmc.Text(text, size="xs", c="#475467"),
    ])


def build_colocation_summary(aggregate: dict, customer_count: int | None = None):
    """KPI tiles + stacked used-U bar. Reads total_u/used_u/free_u/rack_count and
    the optional external_u/internal_u/untagged_u/external_customer_count split.
    The bar is hidden when the split is absent/zero."""
    agg = aggregate or {}
    total_u = int(agg.get("total_u") or 0)
    used_u = int(agg.get("used_u") or 0)
    free_u = int(agg.get("free_u") or 0)
    racks = int(agg.get("rack_count") or 0)
    ext = int(agg.get("external_u") or 0)
    intn = int(agg.get("internal_u") or 0)
    unt = int(agg.get("untagged_u") or 0)
    ncust = int(customer_count if customer_count is not None
                else (agg.get("external_customer_count") or 0))
    base = ext + intn + unt

    potential = agg.get("free_u_potential_tl")
    unit_price = agg.get("unit_price_tl")
    price_source = agg.get("price_source") or "unavailable"
    if unit_price is None:
        price_tip = ("Colocation unit price unavailable — no operator override and no "
                     "CRM price level for the per-U product. Shown as — rather than 0.")
    else:
        origin = {"override": "operator override",
                  "crm": "CRM price list"}.get(price_source, price_source)
        price_tip = (f"Free U x {unit_price:,.2f} TL per U ({origin}). "
                     "Potential at list price — not billed revenue.")

    tiles = dmc.SimpleGrid(cols=5, spacing="md", children=[
        _tile("Total U", f"{total_u:,}"),
        _tile("Used U", f"{used_u:,}"),
        _tile("Free U", f"{free_u:,}"),
        _tile("Racks", f"{racks:,}"),
        _tile_with_tip("Free U Potential", fmt_tl(potential), price_tip),
    ])

    children = [tiles]
    if base > 0:
        segments = []
        for u, color in ((ext, _EXT_COLOR), (intn, _INT_COLOR), (unt, _UNT_COLOR)):
            if u > 0:
                segments.append(html.Div(style={
                    "width": f"{u / base * 100:.2f}%", "background": color, "height": "100%",
                }))
        bar = html.Div(style={
            "display": "flex", "width": "100%", "height": "14px",
            "borderRadius": "7px", "overflow": "hidden", "background": "#F2F4F7",
        }, children=segments)
        labels = dmc.Group(gap="lg", mt="xs", children=[
            _swatch_label(_EXT_COLOR, f"External {ext:,}U ({ncust} customers)"),
            _swatch_label(_INT_COLOR, f"Internal {intn:,}U"),
            _swatch_label(_UNT_COLOR, f"Untagged {unt:,}U"),
        ])
        children += [
            dmc.Text("Used U — where it goes", size="xs", c="#667085", fw=600, mt="md"),
            bar,
            labels,
        ]

    return dmc.Stack(gap="xs", children=children)
