"""DC View Summary tab — categorized sellable executive overview."""
from __future__ import annotations

from typing import Any

import dash_mantine_components as dmc
from dash import html
from dash_iconify import DashIconify

from src.services import api_client as api
from src.utils.format_units import smart_cpu, smart_memory, smart_storage

_BRAND = "#4318FF"
_MUTED = "#A3AED0"
_TEXT = "#2B3674"

# Virtualization families grouped for compute vs storage relationship blocks.
_VIRT_COMPUTE_FAMILIES = frozenset({
    "virt_classic", "virt_hyperconverged", "virt_power", "virt_power_hana",
})
_VIRT_STORAGE_FAMILIES = frozenset({"virt_classic", "virt_power"})
_VIRT_FAMILY_LABELS = {
    "virt_classic": "Klasik Mimari",
    "virt_hyperconverged": "Hyperconverged",
    "virt_power": "Power",
    "virt_power_hana": "Power HANA",
}


def _fmt_tl(value: float | None) -> str:
    if value is None:
        return "—"
    v = float(value or 0)
    if v >= 1_000_000:
        return f"{v / 1_000_000:.2f} Milyon TL"
    if v >= 1_000:
        return f"{v / 1_000:.1f} Bin TL"
    return f"{v:,.0f} TL"


def _fmt_tl_range(lo: float | None, hi: float | None) -> str:
    if lo is None and hi is None:
        return "—"
    if lo is not None and hi is not None and abs(hi - lo) > 1e-6:
        return f"{_fmt_tl(lo)} – {_fmt_tl(hi)}"
    return _fmt_tl(lo if lo is not None else hi)


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
            return fam.get("panels") or []
    return []


def _build_virt_compute_block(summary: dict) -> html.Div:
    cards = []
    for fam in ("virt_classic", "virt_hyperconverged", "virt_power", "virt_power_hana"):
        panels = _family_panels(summary, fam)
        if not panels:
            continue
        cpu = _panel_by_kind(panels, "cpu")
        ram = _panel_by_kind(panels, "ram")
        if not cpu and not ram:
            continue
        mode = next((p.get("computation_mode") for p in panels if p.get("computation_mode")), None)
        cpu_phys = cpu.get("sellable_physical") if cpu else None
        cpu_eff = cpu.get("sellable_effective") if cpu else (cpu.get("sellable_constrained") if cpu else None)
        cpu_unit = (cpu or {}).get("display_unit") or "vCPU"
        cards.append(html.Div(
            className="nexus-card",
            style={"padding": "16px", "background": "#FBFCFE"},
            children=[
                dmc.Group(gap="xs", mb="xs", children=[
                    dmc.Text(_VIRT_FAMILY_LABELS.get(fam, fam), fw=700, size="sm"),
                    dmc.Badge(mode or "aggregate", variant="light", size="xs", color="blue" if mode == "host_based" else "gray"),
                ]),
                dmc.Stack(gap=4, children=[
                    dmc.Text(
                        f"CPU Physical: {smart_cpu(cpu_phys) if cpu_phys is not None else '—'}",
                        size="xs",
                    ),
                    dmc.Text(
                        f"CPU Effective: {cpu_eff:,.0f} {cpu_unit}" if cpu_eff is not None else "CPU Effective: —",
                        size="xs",
                    ),
                    dmc.Text(
                        f"RAM Sellable: {smart_memory((ram or {}).get('sellable_constrained'))}",
                        size="xs",
                    ),
                ]),
                _gradient_bar(
                    float((cpu or {}).get("total") or 0),
                    float((cpu or {}).get("allocated") or 0),
                    float(cpu_eff or 0),
                    float((cpu or {}).get("threshold_pct") or 80),
                    _BRAND,
                ) if cpu else None,
            ],
        ))
    if not cards:
        return dmc.Alert("Sanallaştırma compute sellable verisi yok.", color="gray", radius="md")
    return html.Div([
        _section_title(
            "Sanallaştırma — Compute",
            "Host bazlı CPU/RAM satılabilirlik (Physical vs Effective)",
        ),
        dmc.SimpleGrid(cols={"base": 1, "md": 2, "xl": 4}, spacing="md", mt="md", children=cards),
    ])


def _build_virt_storage_block(summary: dict) -> html.Div:
    km_panels = _family_panels(summary, "virt_classic")
    pw_panels = _family_panels(summary, "virt_power")
    km_stor = _panel_by_kind(km_panels, "storage")
    pw_stor = _panel_by_kind(pw_panels, "storage")
    if not km_stor and not pw_stor:
        return html.Div()

    def _range_text(p: dict | None) -> str:
        if not p:
            return "—"
        lo, hi = p.get("sellable_min"), p.get("sellable_max")
        unit = p.get("display_unit") or "GB"
        if lo is not None and hi is not None and abs(float(hi) - float(lo)) > 1e-6:
            return f"{float(lo):,.0f} – {float(hi):,.0f} {unit}"
        return f"{float(p.get('sellable_constrained') or 0):,.0f} {unit}"

    return html.Div(
        className="nexus-card",
        style={"padding": "20px", "marginTop": "16px"},
        children=[
            _section_title(
                "Sanallaştırma — Storage",
                "Compute ile ilişkili ancak bağımsız kategori — IBM kapasitesi KM ve Power arasında paylaşımlıdır",
            ),
            dmc.SimpleGrid(cols={"base": 1, "md": 2}, spacing="lg", mt="md", children=[
                html.Div(children=[
                    dmc.Text("KM (Classic) Storage Sellable", fw=600, size="sm"),
                    dmc.Text(_range_text(km_stor), size="lg", fw=800, c="blue"),
                    dmc.Text(_fmt_tl_range(
                        (km_stor or {}).get("potential_tl_min"),
                        (km_stor or {}).get("potential_tl_max"),
                    ), size="xs", c="dimmed"),
                ]),
                html.Div(children=[
                    dmc.Text("Power Storage Sellable", fw=600, size="sm"),
                    dmc.Text(_range_text(pw_stor), size="lg", fw=800, c="grape"),
                    dmc.Text(_fmt_tl_range(
                        (pw_stor or {}).get("potential_tl_min"),
                        (pw_stor or {}).get("potential_tl_max"),
                    ), size="xs", c="dimmed"),
                ]),
            ]),
            dmc.Alert(
                "IBM storage alanı hem KM datastore hem Power mimarisi tarafından kullanılabilir. "
                "Detay için Virtualization sekmesindeki Storage alt sekmesine gidin.",
                color="blue",
                variant="light",
                radius="md",
                mt="md",
                icon=DashIconify(icon="solar:link-round-bold", width=18),
            ),
        ],
    )


def _build_other_families_accordion(summary: dict) -> html.Div | None:
    items = []
    for fam in summary.get("families") or []:
        fkey = fam.get("family") or ""
        if fkey in _VIRT_COMPUTE_FAMILIES or fkey in _VIRT_STORAGE_FAMILIES:
            continue
        panels = fam.get("panels") or []
        if not panels:
            continue
        potential = float(fam.get("total_potential_tl") or 0)
        if potential <= 0 and not any(p.get("has_infra_source") for p in panels):
            continue
        rows = []
        for p in panels:
            rows.append(dmc.Group(
                justify="space-between",
                children=[
                    dmc.Text(p.get("label") or p.get("panel_key"), size="xs"),
                    dmc.Text(
                        f"{float(p.get('sellable_constrained') or 0):,.0f} {p.get('display_unit') or ''} · {_fmt_tl(p.get('potential_tl'))}",
                        size="xs",
                        fw=600,
                    ),
                ],
            ))
        items.append(dmc.AccordionItem(
            value=fkey,
            children=[
                dmc.AccordionControl(dmc.Text(fam.get("label") or fkey, fw=600)),
                dmc.AccordionPanel(dmc.Stack(gap=6, children=rows)),
            ],
        ))
    if not items:
        return None
    return html.Div(
        className="nexus-card",
        style={"padding": "20px", "marginTop": "16px"},
        children=[
            _section_title("Diğer CRM Kategorileri", "Eşleştirilmiş tüm servis aileleri"),
            dmc.Accordion(variant="separated", radius="md", mt="md", children=items),
        ],
    )


def build_summary_sellable_section(dc_id: str, summary: dict | None = None) -> html.Div | None:
    """Executive sellable block for DC Summary tab."""
    if not dc_id:
        return None
    try:
        data = summary if summary is not None else api.get_sellable_summary(dc_code=str(dc_id))
    except Exception:
        return dmc.Alert("Sellable özeti yüklenemedi.", color="red", radius="md")

    if not data or not isinstance(data, dict):
        return None

    modes = data.get("computation_modes") or {}
    mode_badge = ", ".join(f"{k}: {v}" for k, v in modes.items()) or "aggregate"

    exec_strip = dmc.SimpleGrid(cols={"base": 1, "sm": 2, "lg": 4}, spacing="md", children=[
        _exec_kpi(
            "Total Potential",
            _fmt_tl_range(data.get("total_potential_tl_min"), data.get("total_potential_tl_max")),
            "Physical – Effective aralığı",
            "solar:wallet-money-bold-duotone",
            "grape",
        ),
        _exec_kpi(
            "Constrained Loss",
            _fmt_tl(data.get("constrained_loss_tl")),
            "Ratio-bound kayıp",
            "solar:chart-2-bold-duotone",
            "orange",
        ),
        _exec_kpi(
            "Mapped Panels",
            str(data.get("mapped_panel_count") or 0),
            f"Unmapped products: {data.get('unmapped_product_count') or 0}",
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

    return html.Div(
        id="dc-summary-sellable-root",
        children=[
            html.Div(className="nexus-card", style={"padding": "20px"}, children=[
                _section_title(
                    "Sellable Executive Summary",
                    "Satılabilir kapasite ve TL potansiyeli — yönetici özeti",
                ),
                exec_strip,
            ]),
            html.Div(style={"marginTop": "16px"}, children=_build_virt_compute_block(data)),
            _build_virt_storage_block(data),
            _build_other_families_accordion(data),
        ],
    )


def build_summary_sellable_children(dc_id: str, summary: dict | None = None) -> list:
    """Return sellable section children for Dash callback updates."""
    block = build_summary_sellable_section(dc_id, summary)
    if block is None:
        return [dmc.Alert("Sellable verisi yok.", color="gray", radius="md")]
    return block.children if hasattr(block, "children") else [block]
