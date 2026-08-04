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
from src.utils.platform_sellable_aggregate import (
    BACKUP_SELLABLE_FAMILIES,
    collect_platform_sellable_panels,
    platform_total_potential_range,
    potential_sales_info_text,
)
from src.utils.virt_sellable_aggregate import (
    collect_virt_sellable_panels,
    merge_power_panels_for_summary,
    virt_constrained_loss_tl,
    virt_tab_cluster_scope,
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
_BACKUP_FAMILY_LABELS = {
    "backup_netbackup": "NetBackup",
    "backup_veeam_replication": "Veeam Replication",
    "backup_zerto_replication": "Zerto Replication",
    "backup_veeam_replication_classic": "Veeam Replication Classic",
    "backup_veeam_replication_hyperconverged": "Veeam Replication HC",
    "backup_zerto_replication_classic": "Zerto Replication Classic",
    "backup_zerto_replication_hyperconverged": "Zerto Replication HC",
    "backup_image": "Nutanix Image Backup",
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


def _virt_panels_only(panels: list[dict]) -> list[dict]:
    return [
        p for p in (panels or [])
        if isinstance(p, dict) and str(p.get("family") or "").startswith("virt_")
    ]


def _backup_panels_only(panels: list[dict]) -> list[dict]:
    backup_fams = set(BACKUP_SELLABLE_FAMILIES)
    return [
        p for p in (panels or [])
        if isinstance(p, dict) and (p.get("family") or "") in backup_fams
    ]


def _resolve_platform_panels(
    dc_id: str,
    summary: dict | None,
    *,
    classic_clusters: list[str] | None = None,
    hyperconv_clusters: list[str] | None = None,
) -> list[dict]:
    """Prefer platform by-panel API (virt + backup); fall back to virt / summary."""
    classic, hyperconv = virt_tab_cluster_scope(classic_clusters, hyperconv_clusters)
    try:
        panels = collect_platform_sellable_panels(str(dc_id), classic, hyperconv)
        if panels:
            return panels
    except Exception:
        pass
    try:
        panels = collect_virt_sellable_panels(str(dc_id), classic, hyperconv)
        if panels:
            return panels
    except Exception:
        pass
    if not summary:
        return []
    out: list[dict] = []
    for fam in _VIRT_COMPUTE_FAMILIES | _VIRT_STORAGE_FAMILIES | set(BACKUP_SELLABLE_FAMILIES):
        for p in _family_panels(summary, fam):
            row = dict(p)
            row.setdefault("family", fam)
            out.append(row)
    return out


# Backward-compatible virt-only resolver (cluster-scope tests / callers).
def _resolve_virt_panels(
    dc_id: str,
    summary: dict | None,
    *,
    classic_clusters: list[str] | None = None,
    hyperconv_clusters: list[str] | None = None,
) -> list[dict]:
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
    panels: list[dict] | None = None,
    colocation_tl: float | None = None,
) -> html.Div:
    """Executive KPI strip for Summary tab (platform Potential Sales)."""
    panel_rows = panels if panels is not None else (virt_panels or [])
    _, tl_min, tl_max = platform_total_potential_range(
        panel_rows, colocation_tl=colocation_tl,
    )
    constrained_loss = virt_constrained_loss_tl(_virt_panels_only(panel_rows))
    if tl_max <= 1e-6 and tl_min <= 1e-6:
        constrained_loss = 0.0
    mapped_count = sum(
        1 for p in panel_rows if p.get("has_infra_source") or p.get("has_price")
    )
    modes = {
        p.get("family"): p.get("computation_mode")
        for p in panel_rows
        if p.get("computation_mode")
    }
    if not modes and summary:
        modes = summary.get("computation_modes") or {}
    mode_badge = ", ".join(f"{k}: {v}" for k, v in modes.items()) or "aggregate"
    unmapped = (summary or {}).get("unmapped_product_count") or 0
    breakdown = constraint_breakdown_text(_virt_panels_only(panel_rows))
    info = potential_sales_info_text()
    exec_strip = dmc.SimpleGrid(cols={"base": 1, "sm": 2, "lg": 4}, spacing="md", children=[
        dmc.Tooltip(
            label=info,
            position="bottom",
            withArrow=True,
            multiline=True,
            w=360,
            children=_exec_kpi(
                "Potential Sales",
                _fmt_tl_range(tl_min, tl_max),
                breakdown or "Virt + Backup + Replication + Colocation",
                "solar:wallet-money-bold-duotone",
                "grape",
            ),
        ),
        _exec_kpi(
            "Constrained Loss",
            _fmt_tl(constrained_loss),
            "Ratio-bound loss (virtualization)",
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
            "Potential Sales — platform sellable headroom (min–max TL)",
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


def build_backup_sellable_block(*, panels: list[dict] | None = None) -> html.Div | None:
    """Backup / Replication sellable family tiles for Summary."""
    backup = _backup_panels_only(panels or [])
    if not backup:
        return None
    grouped = _group_panels_by_family(backup)
    cards = []
    for fam in BACKUP_SELLABLE_FAMILIES:
        fam_panels = grouped.get(fam) or []
        if not fam_panels:
            continue
        tl_min = 0.0
        tl_max = 0.0
        gate_blocked = False
        for p in fam_panels:
            lo = p.get("potential_tl_min")
            hi = p.get("potential_tl_max")
            base = float(p.get("potential_tl") or 0)
            tl_min += float(lo) if lo is not None else base
            tl_max += float(hi) if hi is not None else base
            if p.get("gate_blocked"):
                gate_blocked = True
        kinds = sorted({
            (p.get("resource_kind") or "other").lower() for p in fam_panels
        })
        sub = ", ".join(k.upper() for k in kinds) or "sellable"
        if gate_blocked:
            sub = f"{sub} · utilization gate"
        cards.append(_exec_kpi(
            _BACKUP_FAMILY_LABELS.get(fam, fam),
            fmt_tl_range(tl_min, tl_max),
            sub,
            "solar:cloud-storage-bold-duotone",
            "green",
        ))
    if not cards:
        return None
    return html.Div(
        className="nexus-card",
        style={"padding": "20px", "marginTop": "16px"},
        children=[
            _section_title(
                "Backup & Replication — Sellable",
                "NetBackup, Nutanix image, Veeam / Zerto replication headroom (min–max TL)",
            ),
            dmc.SimpleGrid(
                cols={"base": 1, "md": min(4, len(cards))},
                spacing="md",
                mt="md",
                children=cards,
            ),
        ],
    )


def _excluded_u_sentence(free_u, sellable_free_u, role_breakdown) -> str:
    """Name what left the sellable pool, with numbers, or return "".

    Customer rule 2026-08-04: customer cabinets AND network cabinets are out.
    Naming only one of them (or neither) leaves the tile above looking like a
    number that shrank for no reason."""
    excluded_u = max(int(free_u or 0) - int(sellable_free_u or 0), 0)
    if not excluded_u:
        return ""
    parts = [f"{int(r.get('free_u') or 0):,} U in {r['role_name']} cabinets "
             f"({int(r.get('rack_count') or 0)} racks)"
             for r in (role_breakdown or []) if not r.get("sellable")
             and int(r.get("free_u") or 0) > 0]
    if parts:
        return f" Excluded from sale — {excluded_u:,} U: " + ", ".join(parts) + "."
    return (f" Excluded from sale — {excluded_u:,} U in customer and network "
            "cabinets.")


def build_colocation_sellable_entry(coloc_aggregate: dict | None):
    """Physical — Colocation sellable entry: free rack-U and its TL value.

    Returns None when there is no colocation data for this DC. The TL figure is
    also folded into the executive Potential Sales range via
    ``platform_total_potential_range(..., colocation_tl=...)``.

    Only SELLABLE free U is shown and priced (customer rule 2026-08-04: not
    inside a colocation customer's own cabinet, not inside a network cabinet).
    ``free_u`` stays physical and is cited beside the sellable figure as the
    base it was cut from, so the subtraction is visible rather than implied.
    """
    agg = coloc_aggregate or {}
    free_u = agg.get("free_u")
    if not free_u:
        return None
    potential = agg.get("free_u_potential_tl")
    unit_price = agg.get("unit_price_tl")
    # free_u_potential_tl prices sellable_free_u (free U OUTSIDE colocation-
    # allocated racks) -- free U inside a customer's own rack isn't sellable
    # inventory, so it's excluded from both the number and the tooltip's
    # arithmetic. sellable_free_u falls back to free_u for callers that never
    # set it (no allocation data at all), so the tooltip stays accurate then too.
    sellable_free_u = agg.get("sellable_free_u", free_u)
    allocated_u = agg.get("colocation_allocated_u")
    rack_count = agg.get("rack_count")
    excluded_sentence = _excluded_u_sentence(
        free_u, sellable_free_u, agg.get("role_breakdown")
    )
    # Only worth showing the physical base when it differs -- "3,611 U of 3,611
    # free U" is noise.
    free_u_sub = (f"of {int(free_u):,} free U" if excluded_sentence
                  else "all free U is sellable here")

    if unit_price is None:
        price_sub = "unit price unavailable"
        note = ("Colocation unit price could not be resolved, so no TL figure is shown. "
                "An em dash means the price is unknown — not that the space is worthless.")
        note_color = "orange"
        note_icon = "solar:danger-triangle-bold"
    else:
        note = ("Included in Potential Sales above. Potential at list price — not billed "
                "revenue. Counts only free U that is actually offerable: space inside a "
                "colocation customer's own cabinet belongs to them, and a network "
                "cabinet is switching space nobody can rent." + excluded_sentence)
        price_sub = f"{sellable_free_u:,} U × {unit_price:,.2f} TL"
        note_color = "blue"
        note_icon = "solar:info-circle-bold"

    tiles = [
        _exec_kpi(
            "Sellable Free U", f"{sellable_free_u:,} U",
            free_u_sub, "solar:box-minimalistic-bold-duotone", "blue",
        ),
        _exec_kpi(
            "Potential (list price)", fmt_tl(potential),
            price_sub, "solar:money-bag-bold-duotone", "violet",
        ),
    ]
    if allocated_u:
        tiles.append(_exec_kpi(
            "Allocated to Customers", f"{int(allocated_u):,} U",
            f"of {int(rack_count):,} racks in this DC" if rack_count else "not sellable",
            "solar:users-group-rounded-bold-duotone", "orange",
        ))

    # Matches the shell of build_virt_storage_block above: a full-width section
    # card, not a bare tile. Appended into the same stack, a small standalone
    # card rendered as a narrow orphan against its full-width siblings.
    return html.Div(
        className="nexus-card",
        style={"padding": "20px"},
        children=[
            _section_title(
                "Physical — Colocation",
                "Free rack-U available to sell, valued at the CRM per-U list price",
            ),
            dmc.SimpleGrid(
                cols={"base": 1, "md": len(tiles)}, spacing="lg", mt="md", children=tiles,
            ),
            dmc.Alert(
                note, color=note_color, variant="light", radius="md", mt="md",
                icon=DashIconify(icon=note_icon, width=18),
            ),
        ],
    )


def build_summary_sellable_section(
    dc_id: str,
    summary: dict | None = None,
    *,
    classic_clusters: list[str] | None = None,
    hyperconv_clusters: list[str] | None = None,
    coloc_aggregate: dict | None = None,
) -> html.Div | None:
    """Sellable blocks for DC Summary tab (executive + virt + backup + colo detail)."""
    if not dc_id:
        return None
    data: dict = summary if isinstance(summary, dict) else {}
    platform_panels = merge_power_panels_for_summary(
        _resolve_platform_panels(
            str(dc_id),
            data or None,
            classic_clusters=classic_clusters,
            hyperconv_clusters=hyperconv_clusters,
        )
    )
    if not platform_panels and not data:
        try:
            data = api.get_sellable_summary_light(dc_code=str(dc_id)) or {}
        except Exception:
            return html.Div(children=[
                dmc.Alert("Sellable özeti yüklenemedi.", color="red", radius="md"),
            ])
        platform_panels = merge_power_panels_for_summary(
            _resolve_platform_panels(
                str(dc_id),
                data,
                classic_clusters=classic_clusters,
                hyperconv_clusters=hyperconv_clusters,
            )
        )

    if not platform_panels and not data and not (coloc_aggregate or {}).get("free_u"):
        return None

    colo_tl = None
    if coloc_aggregate:
        raw = coloc_aggregate.get("free_u_potential_tl")
        if raw is not None:
            try:
                colo_tl = float(raw)
            except (TypeError, ValueError):
                colo_tl = None

    virt_panels = _virt_panels_only(platform_panels)
    children: list[Any] = [
        build_sellable_executive_strip(
            data, panels=platform_panels, colocation_tl=colo_tl,
        ),
        html.Div(style={"marginTop": "16px"}, children=build_virt_compute_block(panels=virt_panels)),
        build_virt_storage_block(panels=virt_panels),
    ]
    backup_block = build_backup_sellable_block(panels=platform_panels)
    if backup_block is not None:
        children.append(backup_block)
    colo_entry = build_colocation_sellable_entry(coloc_aggregate)
    if colo_entry is not None:
        children.append(colo_entry)

    return html.Div(
        id="dc-summary-sellable-root",
        children=children,
    )


def build_summary_sellable_children(
    dc_id: str,
    summary: dict | None = None,
    *,
    classic_clusters: list[str] | None = None,
    hyperconv_clusters: list[str] | None = None,
    coloc_aggregate: dict | None = None,
) -> list:
    """Return sellable section children for Dash callback updates."""
    block = build_summary_sellable_section(
        dc_id,
        summary,
        classic_clusters=classic_clusters,
        hyperconv_clusters=hyperconv_clusters,
        coloc_aggregate=coloc_aggregate,
    )
    if block is None:
        return [dmc.Alert("Sellable verisi yok.", color="gray", radius="md")]
    return block.children if hasattr(block, "children") else [block]
