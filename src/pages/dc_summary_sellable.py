"""DC View Summary tab — categorized sellable executive overview."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import dash_mantine_components as dmc
from dash import html
from dash_iconify import DashIconify

from src.services import api_client as api
from src.components.sellable_constraint_viz import (
    build_storage_family_tile,
    constraint_breakdown_text,
    sellable_constraint_badges,
    sellable_constraint_bar,
)
from src.utils.format_units import fmt_tl, fmt_tl_range, smart_cpu, smart_memory, smart_storage
from src.utils.virt_sellable_aggregate import (
    collect_virt_sellable_panels,
    merge_power_panels_for_summary,
    virt_constrained_loss_tl,
    virt_tab_cluster_scope,
    virt_total_potential_range,
)

_BRAND = "#4318FF"
_MUTED = "#A3AED0"
_TEXT = "#2B3674"

# Virtualization families grouped for compute vs storage relationship blocks.
_VIRT_COMPUTE_FAMILIES = frozenset({
    "virt_classic", "virt_hyperconverged", "virt_power", "virt_power_hana",
})
_VIRT_STORAGE_FAMILIES = frozenset({"virt_classic", "virt_hyperconverged", "virt_power"})
_VIRT_FAMILY_LABELS = {
    "virt_classic": "Klasik Mimari",
    "virt_hyperconverged": "Hyperconverged",
    "virt_power": "Power",
    "virt_power_hana": "Power HANA",
}


_fmt_tl = fmt_tl
_fmt_tl_range = fmt_tl_range


def _section_title(title: str, subtitle: str | None = None) -> html.Div:
    return html.Div([
        html.H3(title, style={"margin": 0, "color": _TEXT, "fontWeight": 800, "fontSize": "1.05rem"}),
        html.P(subtitle or "", style={"margin": "4px 0 0", "color": _MUTED, "fontSize": "0.85rem"}),
    ])


def _exec_kpi(label: str, value: str, sub: str, icon: str, color: str = "violet") -> html.Div:
    return html.Div(
        className="nexus-card dc-kpi-card",
        style={"padding": "18px", "minHeight": "130px"},
        children=[
            dmc.Group(
                justify="space-between",
                align="flex-start",
                children=[
                    html.Div([
                        html.Span(label, style={"color": _MUTED, "fontSize": "0.75rem", "textTransform": "uppercase"}),
                        html.H3(value, style={"color": _TEXT, "fontWeight": 900, "margin": "8px 0 4px", "fontSize": "1.1rem"}),
                        html.Span(sub, style={"color": _BRAND, "fontSize": "0.78rem", "fontWeight": 600}),
                    ]),
                    dmc.ThemeIcon(size=42, radius="xl", variant="light", color=color,
                                  children=DashIconify(icon=icon, width=22)),
                ],
            ),
        ],
    )


def _gradient_bar(total: float, allocated: float, sellable: float, threshold_pct: float, color: str) -> html.Div:
    cap = max(total, 1e-9)
    alloc_pct = min(100.0, 100.0 * allocated / cap)
    sell_pct = min(100.0, 100.0 * sellable / cap)
    thr_pct = min(threshold_pct, 100.0)
    return html.Div(style={"marginTop": "8px"}, children=[
        html.Div(style={
            "position": "relative", "height": "10px", "borderRadius": "6px",
            "background": "#E9EDF7", "overflow": "hidden",
        }, children=[
            html.Div(style={
                "width": f"{alloc_pct}%", "height": "100%",
                "background": f"linear-gradient(90deg, {color}55, {color})",
            }),
            html.Div(style={
                "position": "absolute", "left": f"{thr_pct}%", "top": 0, "bottom": 0,
                "width": "2px", "background": "#FFB547",
            }),
        ]),
        dmc.Group(gap="md", mt=6, children=[
            dmc.Text(f"Cap: {total:,.0f}", size="xs", c="dimmed"),
            dmc.Text(f"Alloc: {allocated:,.0f}", size="xs", c="dimmed"),
            dmc.Text(f"Sellable: {sellable:,.0f}", size="xs", c="blue", fw=600),
        ]),
    ])


def _panel_by_kind(panels: list[dict], kind: str) -> dict | None:
    for p in panels or []:
        if (p.get("resource_kind") or "").lower() == kind:
            return p
    return None


def _family_panels(summary: dict, family: str) -> list[dict]:
    for fam in summary.get("families") or []:
        if fam.get("family") == family:
            panels = fam.get("panels") or []
            if panels:
                return panels
            summaries = fam.get("panel_summaries") or {}
            if isinstance(summaries, dict):
                return list(summaries.values())
    return []


def _group_panels_by_family(panels: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for p in panels or []:
        if not isinstance(p, dict):
            continue
        fam = p.get("family") or ""
        if fam:
            grouped[fam].append(p)
    return grouped


def _resolve_virt_panels(
    dc_id: str,
    summary: dict | None,
    *,
    classic_clusters: list[str] | None = None,
    hyperconv_clusters: list[str] | None = None,
) -> list[dict]:
    """Prefer by-panel API (Virt tab parity); fall back to summary rollup."""
    classic, hyperconv = virt_tab_cluster_scope(classic_clusters, hyperconv_clusters)
    try:
        panels = collect_virt_sellable_panels(str(dc_id), classic, hyperconv)
        if panels:
            return panels
    except Exception:
        pass
    if not summary:
        return []
    out: list[dict] = []
    for fam in _VIRT_COMPUTE_FAMILIES | _VIRT_STORAGE_FAMILIES:
        for p in _family_panels(summary, fam):
            row = dict(p)
            row.setdefault("family", fam)
            out.append(row)
    return out


def build_sellable_executive_strip(
    summary: dict | None = None,
    *,
    virt_panels: list[dict] | None = None,
) -> html.Div:
    """Executive KPI strip for Summary tab (virt-scoped, Virt tab parity)."""
    panels = virt_panels or []
    _, tl_min, tl_max = virt_total_potential_range(panels)
    constrained_loss = virt_constrained_loss_tl(panels)
    if tl_max <= 1e-6 and tl_min <= 1e-6:
        constrained_loss = 0.0
    mapped_count = sum(
        1 for p in panels if p.get("has_infra_source") or p.get("has_price")
    )
    modes = {
        p.get("family"): p.get("computation_mode")
        for p in panels
        if p.get("computation_mode")
    }
    if not modes and summary:
        modes = summary.get("computation_modes") or {}
    mode_badge = ", ".join(f"{k}: {v}" for k, v in modes.items()) or "aggregate"
    unmapped = (summary or {}).get("unmapped_product_count") or 0
    breakdown = constraint_breakdown_text(panels)
    exec_strip = dmc.SimpleGrid(cols={"base": 1, "sm": 2, "lg": 4}, spacing="md", children=[
        _exec_kpi(
            "Total Potential",
            _fmt_tl_range(tl_min, tl_max),
            breakdown or "Classic + Hyperconverged + Power (Virt tab parity)",
            "solar:wallet-money-bold-duotone",
            "grape",
        ),
        _exec_kpi(
            "Constrained Loss",
            _fmt_tl(constrained_loss),
            "Ratio-bound kayıp (sanallaştırma)",
            "solar:chart-2-bold-duotone",
            "orange",
        ),
        _exec_kpi(
            "Mapped Panels",
            str(mapped_count),
            f"Unmapped products: {unmapped}",
            "solar:checklist-bold-duotone",
            "teal",
        ),
        _exec_kpi(
            "Computation",
            "Host-based" if any(v == "host_based" for v in modes.values()) else "Cluster",
            mode_badge[:80],
            "solar:server-bold-duotone",
            "blue",
        ),
    ])
    return html.Div(className="nexus-card", style={"padding": "20px"}, children=[
        _section_title(
            "Sellable Executive Summary",
            "Satılabilir kapasite ve TL potansiyeli — yönetici özeti",
        ),
        exec_strip,
    ])


def build_virt_compute_block(summary: dict | None = None, *, panels: list[dict] | None = None) -> html.Div:
    """Sanallaştırma — Compute block (host-based CPU/RAM sellable)."""
    grouped = _group_panels_by_family(panels or []) if panels else {}
    cards = []
    for fam in ("virt_classic", "virt_hyperconverged", "virt_power"):
        fam_panels = grouped.get(fam) if panels else _family_panels(summary or {}, fam)
        if not fam_panels:
            continue
        cpu = _panel_by_kind(fam_panels, "cpu")
        ram = _panel_by_kind(fam_panels, "ram")
        if not cpu and not ram:
            continue
        mode = next((p.get("computation_mode") for p in fam_panels if p.get("computation_mode")), None)
        allocation_only = fam == "virt_power" or mode == "power_allocation_only"
        cpu_alloc = cpu.get("sellable_allocation") if cpu else None
        if cpu_alloc is None and cpu:
            cpu_alloc = cpu.get("sellable_effective") or cpu.get("sellable_constrained")
        cpu_max = cpu.get("sellable_max_util") if cpu else None
        ram_alloc = ram.get("sellable_allocation") if ram else None
        if ram_alloc is None and ram:
            ram_alloc = ram.get("sellable_physical") or ram.get("sellable_constrained")
        ram_max = ram.get("sellable_max_util") if ram else None
        if ram_max is None and ram and not allocation_only:
            ram_max = ram.get("sellable_effective")
        cpu_unit = (cpu or {}).get("display_unit") or "vCPU"
        badge_children: list = []
        for kind_label, panel in (("CPU", cpu), ("RAM", ram)):
            badge_children.extend(sellable_constraint_badges(panel, kind_label=kind_label))
        cards.append(html.Div(
            className="nexus-card",
            style={"padding": "16px", "background": "#FBFCFE"},
            children=[
                dmc.Group(gap="xs", mb="xs", children=[
                    dmc.Text(_VIRT_FAMILY_LABELS.get(fam, fam), fw=700, size="sm"),
                    dmc.Badge(mode or "aggregate", variant="light", size="xs", color="blue" if mode == "host_based" else "gray"),
                ]),
                dmc.Stack(gap=4, children=[
                    dmc.Text("CPU", fw=600, size="xs"),
                    dmc.Text(
                        f"Sellable: {cpu_alloc:,.0f} {cpu_unit}"
                        if allocation_only and cpu_alloc is not None
                        else (
                            f"Allocation: {cpu_alloc:,.0f} {cpu_unit} · "
                            f"Max: {cpu_max:,.0f} {cpu_unit}"
                            if cpu_alloc is not None and cpu_max is not None
                            else f"Sellable: {(cpu or {}).get('sellable_constrained', '—')}"
                        ),
                        size="xs",
                    ),
                    sellable_constraint_bar(
                        float((cpu or {}).get("total") or 0),
                        float((cpu or {}).get("allocated") or 0),
                        float(cpu_alloc or 0),
                        sellable_raw=float((cpu or {}).get("sellable_raw") or 0),
                        threshold_pct=float((cpu or {}).get("threshold_pct") or 80),
                        color=_BRAND,
                    ) if cpu else None,
                    dmc.Text("RAM", fw=600, size="xs", mt="xs"),
                    dmc.Text(
                        f"Sellable: {smart_memory(ram_alloc)}"
                        if allocation_only and ram_alloc is not None
                        else (
                            f"Allocation: {smart_memory(ram_alloc)} · Max: {smart_memory(ram_max)}"
                            if ram_alloc is not None and ram_max is not None
                            else f"Sellable: {smart_memory((ram or {}).get('sellable_constrained'))}"
                        ),
                        size="xs",
                    ),
                    sellable_constraint_bar(
                        float((ram or {}).get("total") or 0),
                        float((ram or {}).get("allocated") or 0),
                        float(ram_alloc or (ram or {}).get("sellable_constrained") or 0),
                        sellable_raw=float((ram or {}).get("sellable_raw") or 0),
                        threshold_pct=float((ram or {}).get("threshold_pct") or 80),
                        color="#7551FF",
                    ) if ram else None,
                ]),
                dmc.Group(gap="xs", mt="sm", children=badge_children) if badge_children else None,
            ],
        ))
    if not cards:
        return dmc.Alert("Sanallaştırma compute sellable verisi yok.", color="gray", radius="md")
    return html.Div([
        _section_title(
            "Sanallaştırma — Compute",
            "Host-based CPU/RAM sellable (Classic/Hyperconv: Alloc|Max; Power: allocation only)",
        ),
        dmc.SimpleGrid(cols={"base": 1, "md": 2, "xl": 4}, spacing="md", mt="md", children=cards),
    ])


def build_virt_storage_block(summary: dict | None = None, *, panels: list[dict] | None = None) -> html.Div:
    """Sanallaştırma — Storage block (KM, Hyperconverged, Power)."""
    grouped = _group_panels_by_family(panels or []) if panels else {}
    km_panels = grouped.get("virt_classic") if panels else _family_panels(summary or {}, "virt_classic")
    hc_panels = grouped.get("virt_hyperconverged") if panels else _family_panels(summary or {}, "virt_hyperconverged")
    pw_panels = grouped.get("virt_power") if panels else _family_panels(summary or {}, "virt_power")
    km_stor = _panel_by_kind(km_panels, "storage")
    hc_stor = _panel_by_kind(hc_panels, "storage")
    pw_stor = _panel_by_kind(pw_panels, "storage")
    if not km_stor and not hc_stor and not pw_stor:
        return html.Div()

    km_cpu = _panel_by_kind(km_panels, "cpu") if km_panels else None
    km_ram = _panel_by_kind(km_panels, "ram") if km_panels else None
    compute_zero = (
        km_stor is not None
        and float((km_cpu or {}).get("sellable_constrained") or 0) <= 1e-9
        and float((km_ram or {}).get("sellable_constrained") or 0) <= 1e-9
        and (
            float(km_stor.get("sellable_min") or km_stor.get("sellable_constrained") or 0) > 1e-9
            or float(km_stor.get("sellable_max") or 0) > 1e-9
        )
    )

    tiles = [
        build_storage_family_tile(km_stor, label="KM (Classic) Storage Sellable", color="blue", kind_label="KM"),
        build_storage_family_tile(
            hc_stor,
            label="Hyperconverged Storage Sellable",
            color="teal",
            kind_label="Hyperconverged",
        ),
        build_storage_family_tile(pw_stor, label="Power Storage Sellable", color="grape", kind_label="Power"),
    ]

    return html.Div(
        className="nexus-card",
        style={"padding": "20px"},
        children=[
            _section_title(
                "Sanallaştırma — Storage",
                "Tüm mimarilerde storage, CPU/RAM compute bottleneck ile oran sınırlı",
            ),
            dmc.SimpleGrid(cols={"base": 1, "md": 3}, spacing="lg", mt="md", children=tiles),
            dmc.Alert(
                "KM storage aralığı ham pool kapasitesini gösterir; headline sellable compute "
                "(CPU/RAM) darboğazı ile sınırlıdır — CPU/RAM sıfırken storage TL bandı "
                "planlama aralığıdır, satılabilir bundle değildir.",
                color="orange",
                variant="light",
                radius="md",
                mt="md",
                icon=DashIconify(icon="solar:danger-triangle-bold", width=18),
            ) if compute_zero else None,
            dmc.Alert(
                "IBM storage alanı hem KM datastore hem Power mimarisi tarafından kullanılabilir. "
                "Detay için Virtualization sekmesindeki Storage alt sekmesine gidin.",
                color="blue",
                variant="light",
                radius="md",
                mt="md",
                icon=DashIconify(icon="solar:link-round-bold", width=18),
            ),
            dmc.Alert(
                "Hyperconverged storage Nutanix pool kapasitesinden gelir; satılabilir değer compute "
                "darboğazına göre oran ile sınırlanır (IBM aralığı yok).",
                color="teal",
                variant="light",
                radius="md",
                mt="sm",
                icon=DashIconify(icon="solar:server-square-bold", width=18),
            ),
        ],
    )


def build_summary_sellable_section(
    dc_id: str,
    summary: dict | None = None,
    *,
    classic_clusters: list[str] | None = None,
    hyperconv_clusters: list[str] | None = None,
) -> html.Div | None:
    """Sellable blocks for DC Summary tab (executive + virt compute/storage)."""
    if not dc_id:
        return None
    data: dict = summary if isinstance(summary, dict) else {}
    virt_panels = merge_power_panels_for_summary(
        _resolve_virt_panels(
            str(dc_id),
            data or None,
            classic_clusters=classic_clusters,
            hyperconv_clusters=hyperconv_clusters,
        )
    )
    if not virt_panels and not data:
        try:
            data = api.get_sellable_summary_light(dc_code=str(dc_id)) or {}
        except Exception:
            return html.Div(children=[
                dmc.Alert("Sellable özeti yüklenemedi.", color="red", radius="md"),
            ])
        virt_panels = merge_power_panels_for_summary(
            _resolve_virt_panels(
                str(dc_id),
                data,
                classic_clusters=classic_clusters,
                hyperconv_clusters=hyperconv_clusters,
            )
        )

    if not virt_panels and not data:
        return None

    return html.Div(
        id="dc-summary-sellable-root",
        children=[
            build_sellable_executive_strip(data, virt_panels=virt_panels),
            html.Div(style={"marginTop": "16px"}, children=build_virt_compute_block(panels=virt_panels)),
            build_virt_storage_block(panels=virt_panels),
        ],
    )


def build_summary_sellable_children(
    dc_id: str,
    summary: dict | None = None,
    *,
    classic_clusters: list[str] | None = None,
    hyperconv_clusters: list[str] | None = None,
) -> list:
    """Return sellable section children for Dash callback updates."""
    block = build_summary_sellable_section(
        dc_id,
        summary,
        classic_clusters=classic_clusters,
        hyperconv_clusters=hyperconv_clusters,
    )
    if block is None:
        return [dmc.Alert("Sellable verisi yok.", color="gray", radius="md")]
    return block.children if hasattr(block, "children") else [block]
