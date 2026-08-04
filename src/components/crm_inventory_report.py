"""CRM inventory report tables — grouped accordion / flat view for /crm/inventory-overview."""
from __future__ import annotations

from typing import Any

import dash_mantine_components as dmc
from dash import dash_table, dcc, html
from dash_iconify import DashIconify

from src.pages import crm_shared as shared
from shared.sellable.computation import compute_catalog_tl

_ISSUE_STATUSES = frozenset({"over", "unsold_usage"})

_BASE_COLUMNS = [
    {"name": "Service", "id": "service_label"},
    {"name": "Unit", "id": "display_unit"},
    {"name": "CRM Sold", "id": "crm_sold_fmt"},
    {"name": "Total", "id": "total_fmt"},
    {"name": "Used", "id": "used_fmt"},
    {"name": "Free", "id": "free_fmt"},
    {"name": "Unsold", "id": "unsold_fmt"},
]

_REPLICATION_COLUMNS = [
    {"name": "Service", "id": "service_label"},
    {"name": "Unit", "id": "display_unit"},
    {"name": "CRM Sold", "id": "crm_sold_fmt"},
    {"name": "Total", "id": "total_fmt"},
    {"name": "Allocated", "id": "used_fmt"},
    {"name": "Free", "id": "free_fmt"},
    {"name": "Unsold", "id": "unsold_fmt"},
    {"name": "Sellable (Alloc)", "id": "sellable_alloc_fmt"},
    {"name": "Sellable (Max util)", "id": "sellable_max_fmt"},
    {"name": "Sellable (Ort.)", "id": "sellable_avg_fmt"},
]

_VIRT_BASE_COLUMNS = [
    {"name": "Service", "id": "service_label"},
    {"name": "Unit", "id": "display_unit"},
    {"name": "CRM Sold", "id": "crm_sold_fmt"},
    {"name": "Total", "id": "total_fmt"},
    {"name": "Free", "id": "free_fmt"},
    {"name": "Unsold", "id": "unsold_fmt"},
]

_INVENTORY_VIRT_FAMILIES = frozenset({
    "virt_classic",
    "virt_hyperconverged",
    "virt_power",
    "virt_power_hana",
})

_PHYSICAL_FREE_FAMILIES = frozenset({"storage_s3", "backup_netbackup"})

_NETBACKUP_COLUMNS = [
    {"name": "Service", "id": "service_label"},
    {"name": "Unit", "id": "display_unit"},
    {"name": "CRM Sold", "id": "crm_sold_fmt"},
    {"name": "Total", "id": "total_fmt"},
    {"name": "Used", "id": "used_fmt"},
    {"name": "Transfer (Pre)", "id": "pre_dedup_fmt"},
    {"name": "PostDedup (Cost)", "id": "post_dedup_fmt"},
    {"name": "Dedup Savings %", "id": "dedup_savings_fmt"},
    {"name": "Free", "id": "free_fmt"},
    {"name": "Unsold", "id": "unsold_fmt"},
    {"name": "Birim Fiyat", "id": "unit_price_fmt"},
]

_FREE_COLUMN_TOOLTIP = (
    "Free = altyapıdaki boş kapasite (Total − Allocated / pool available). "
    "CRM Sold düşülmez. Unsold = Total − CRM Sold."
)

_NETBACKUP_FREE_TOOLTIP = (
    "Free = boş havuz kapasitesi (available space). CRM Sold düşülmez. "
    "Unsold = Total − CRM Sold."
)

_DUAL_TRACK_COLUMNS = [
    {"name": "Sellable (Alloc)", "id": "sellable_alloc_fmt"},
    {"name": "Sellable (Max util)", "id": "sellable_max_fmt"},
    {"name": "Sellable (Ort.)", "id": "sellable_avg_fmt"},
]

_ALLOC_ONLY_COLUMNS = [
    {"name": "Sellable (Alloc)", "id": "sellable_alloc_fmt"},
]

_UNIT_PRICE_COLUMN = {"name": "Birim Fiyat", "id": "unit_price_fmt"}

_FLAT_EXTRA_COLUMN = {"name": "Family", "id": "family_label"}

_FLAT_VIEW_FAMILY = "dual_track"

INVENTORY_REPORT_SCHEMA_VERSION = "inventory-final-polish-v5"

_LEFT_COLS = frozenset({
    "service_label", "display_unit", "family_label", "product_name", "resource_unit",
})

_NUMERIC_COLS = frozenset({
    "crm_sold_fmt", "total_fmt", "used_fmt", "free_fmt", "unsold_fmt",
    "pre_dedup_fmt", "post_dedup_fmt", "dedup_savings_fmt",
    "sellable_alloc_fmt", "sellable_max_fmt", "sellable_avg_fmt", "unit_price_fmt",
    "licence_detected_fmt", "licence_gap_fmt", "licence_gap_tl_fmt",
    "entitled_qty", "entitled_amount_tl",
})

_TABLE_STYLE_TABLE = {
    "overflowX": "auto",
    "borderRadius": "8px",
    "minWidth": "900px",
    "tableLayout": "fixed",
    "width": "100%",
}

_UNMAPPED_COLUMNS = [
    {"name": "Product", "id": "product_name"},
    {"name": "Unit", "id": "resource_unit"},
    {"name": "CRM Sold", "id": "entitled_qty"},
    {"name": "Amount TL", "id": "entitled_amount_tl"},
]

_PRODUCT_MATCHING_COLUMNS = [
    {"name": "SKU", "id": "productnumber"},
    {"name": "Product", "id": "product_name"},
    {"name": "Unit", "id": "resource_unit"},
    {"name": "CRM Sold", "id": "crm_sold_fmt"},
    {"name": "Birim Fiyat", "id": "unit_price_fmt"},
    {"name": "Status", "id": "match_status"},
    {"name": "In registry", "id": "in_registry_fmt"},
    {"name": "Matching Rule", "id": "matching_rule"},
    {"name": "Usage source", "id": "usage_source"},
    {"name": "Panel", "id": "panel_key"},
    {"name": "Infra total", "id": "infra_total_fmt"},
    {"name": "Infra used", "id": "infra_used_fmt"},
    {"name": "Tables", "id": "infra_tables_fmt"},
    {"name": "Columns", "id": "infra_columns_fmt"},
    {"name": "Notes", "id": "notes"},
]

_TABLE_STYLE_CELL = {
    "fontSize": "12px",
    "fontFamily": "Inter, system-ui, sans-serif",
    "padding": "8px 10px",
    "textAlign": "left",
    "border": "none",
    "borderBottom": "1px solid #E9EDF7",
    "whiteSpace": "pre-line",
}
_TABLE_STYLE_HEADER = {
    "backgroundColor": "#F4F7FE",
    "color": "#2B3674",
    "fontWeight": "700",
    "border": "none",
    "borderBottom": "2px solid #E0E5F2",
    "position": "sticky",
    "top": 0,
    "zIndex": 1,
}


_COMPARISON_ONLY_COLUMNS = [
    {"name": "Service", "id": "service_label"},
    {"name": "Unit", "id": "display_unit"},
    {"name": "CRM Sold", "id": "crm_sold_fmt"},
    {"name": "Total", "id": "total_fmt"},
    {"name": "Used", "id": "used_fmt"},
    {"name": "Δ Used vs CRM", "id": "delta_fmt"},
]

_OS_LICENCE_COLUMNS = [
    {"name": "Service", "id": "service_label"},
    {"name": "Unit", "id": "display_unit"},
    {"name": "Tespit Edilen", "id": "licence_detected_fmt"},
    {"name": "CRM Sold", "id": "crm_sold_fmt"},
    {"name": "Lisanslanmalı", "id": "licence_gap_fmt"},
    {"name": "Birim Fiyat", "id": "unit_price_fmt"},
    {"name": "Lisanslanmalı TL", "id": "licence_gap_tl_fmt"},
]

_OS_LICENCE_TOOLTIP = (
    "Lisans satılabilir kapasite değildir; sayı vm_metrics.guest_os "
    "(NetBox fallback) ile tespit edilen guest OS adedidir."
)


def columns_for_family(
    family: str | None,
    *,
    hide_used: bool = False,
) -> list[dict[str, str]]:
    """Return DataTable columns for a family sellable profile."""
    profile = (family or "standard").strip()
    if profile == "os_licence":
        return list(_OS_LICENCE_COLUMNS)
    if profile == "comparison_only":
        return [*list(_COMPARISON_ONLY_COLUMNS), dict(_UNIT_PRICE_COLUMN)]
    if profile == "backup_netbackup":
        return list(_NETBACKUP_COLUMNS)
    if (
        profile == "replication"
        or profile.startswith("backup_veeam_replication")
        or profile.startswith("backup_zerto_replication")
    ):
        return [*list(_REPLICATION_COLUMNS), dict(_UNIT_PRICE_COLUMN)]
    if profile in _PHYSICAL_FREE_FAMILIES:
        profile = "standard"
        hide_used = False
    use_virt_base = hide_used or profile in ("dual_track", "allocation_only")
    if profile in _INVENTORY_VIRT_FAMILIES:
        use_virt_base = True
    base_cols = _VIRT_BASE_COLUMNS if use_virt_base else _BASE_COLUMNS
    if profile == _FLAT_VIEW_FAMILY or profile == "dual_track":
        cols = [*list(base_cols), *list(_DUAL_TRACK_COLUMNS)]
    elif profile == "allocation_only":
        cols = [*list(base_cols), *list(_ALLOC_ONLY_COLUMNS)]
    else:
        cols = list(base_cols)
    return [*cols, dict(_UNIT_PRICE_COLUMN)]


def _fmt_qty(value: Any, unit: str) -> str:
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    unit_l = (unit or "").strip().lower()
    if unit_l == "tb" and 0 < abs(v) < 1.0:
        return f"{v * 1024.0:,.1f} GB".strip()
    if unit_l == "tb" and abs(v) < 10:
        return f"{v:,.2f} {unit}".strip()
    return f"{v:,.0f} {unit}".strip()


_ZERO_SELLABLE_HINTS = {
    "ratio_bound": "başka kaynak dolu (oran kısıtı)",
    "compute_bottleneck": "CPU/hesap darboğazı",
    "utilization_gate": "kullanım eşiği aşıldı",
    "gate_blocked": "kullanım eşiği aşıldı",
    "over_threshold": "kapasite eşiği aşıldı",
}


def _sellable_zero_hint(reason: str) -> str:
    """Human explanation for a virt row whose sellable is 0 (so it isn't read as a bug)."""
    return _ZERO_SELLABLE_HINTS.get((reason or "").strip(), "kapasite/oran kısıtı")


def _fmt_dedup_note(row: dict[str, Any], unit: str) -> str:
    """Annotation under Total: shared pool used vs category Jobs PostDedup."""
    note = str(row.get("used_compare_note") or "").strip()
    if note:
        return f"({note})"
    # Fallback when overlay note missing
    try:
        pool_used = float(row.get("pool_used_qty") or 0.0)
        post = float(row.get("post_dedup_qty") or 0.0)
    except (TypeError, ValueError):
        return ""
    if pool_used <= 0 and post <= 0:
        return ""
    pk = str(row.get("panel_key") or "")
    cat = (
        "image" if pk == "backup_netbackup_image"
        else "app" if pk == "backup_netbackup_application"
        else "jobs"
    )
    return f"(Pool used: {pool_used:,.1f} {unit} · {cat} PostDedup: {post:,.1f} {unit})"


def _catalog_unit_price(row: dict[str, Any]) -> float | None:
    """Unit price from catalog / override only (never CRM-sold implied)."""
    if row.get("has_price") is False:
        return None
    try:
        price = float(row.get("unit_price_tl") or 0.0)
    except (TypeError, ValueError):
        return None
    if price <= 0.0:
        return None
    return price


def _price_unit_label(row: dict[str, Any]) -> str:
    """Service/catalog UOM for Birim Fiyat (falls back to display_unit)."""
    return str(row.get("unit_price_unit") or row.get("display_unit") or "").strip()


def _value_at_catalog_price(qty: Any, row: dict[str, Any]) -> float | None:
    """qty (display_unit) × catalog price (price_unit), units aligned."""
    price = _catalog_unit_price(row)
    if price is None or qty is None:
        return None
    display_unit = str(row.get("display_unit") or "")
    price_unit = _price_unit_label(row) or display_unit
    return compute_catalog_tl(
        float(qty),
        price,
        qty_unit=display_unit,
        price_unit=price_unit,
        has_price=True,
    )


def _fmt_unit_price(value: Any, unit: str) -> str:
    """Format a per-unit price. Adaptive precision so per-TB / per-GB prices
    (e.g. 1.42 TL/TB, 0.03 TL/GB) don't round away to zero."""
    try:
        price = float(value)
    except (TypeError, ValueError):
        return "—"
    if price <= 0:
        return "—"
    if price >= 100:
        if abs(price - round(price)) < 1e-9:
            num = f"{price:,.0f}"
        else:
            num = f"{price:,.2f}".rstrip("0").rstrip(".")
    elif price >= 1:
        num = f"{price:,.2f}".rstrip("0").rstrip(".")
    else:
        num = f"{price:,.4f}".rstrip("0").rstrip(".")
    unit = (unit or "").strip()
    return f"{num} TL/{unit}" if unit else f"{num} TL"


def _fmt_crm_sold_block(row: dict[str, Any], unit: str, crm_sold_tl: Any) -> str:
    """Format CRM Sold with optional KM/HANA sub-product line."""
    sub_qty_km = row.get("crm_sold_qty_km")
    sub_qty_hana = row.get("crm_sold_qty_hana")
    has_km = sub_qty_km is not None and float(sub_qty_km or 0) > 0
    has_hana = sub_qty_hana is not None and float(sub_qty_hana or 0) > 0
    if not has_km and not has_hana:
        return shared.fmt_qty_tl_block(
            row.get("crm_sold_qty"), unit, crm_sold_tl,
        )
    sub_label = "KM" if has_km else "HANA"
    sub_qty = sub_qty_km if has_km else sub_qty_hana
    qty_line = shared.fmt_unit(row.get("crm_sold_qty"), unit)
    sub_line = f"({sub_label}: {shared.fmt_unit(sub_qty, unit)})"
    tl_line = shared.fmt_tl(crm_sold_tl) if crm_sold_tl is not None else "—"
    return f"{qty_line}\n{sub_line}\n{tl_line}"


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _row_sellable_tl_tracks(row: dict[str, Any]) -> list[float]:
    """Non-null potential TL values among Alloc / Max util / Ort tracks."""
    tracks: list[float] = []
    for key in ("potential_tl_alloc", "potential_tl_max", "potential_tl_avg"):
        v = _as_float(row.get(key))
        if v is not None:
            tracks.append(v)
    return tracks


def _row_sellable_tl_bounds(row: dict[str, Any]) -> tuple[float | None, float | None]:
    tracks = _row_sellable_tl_tracks(row)
    if not tracks:
        pot = _as_float(row.get("potential_tl"))
        if pot is None:
            return None, None
        return pot, pot
    return min(tracks), max(tracks)


def _fmt_sellable_tl_interval(lo: float | None, hi: float | None) -> str:
    if lo is None and hi is None:
        return "—"
    if lo is None:
        return shared.fmt_tl(hi)
    if hi is None or abs(lo - hi) < 1e-9:
        return shared.fmt_tl(lo)
    return f"{shared.fmt_tl(lo)} – {shared.fmt_tl(hi)}"


def _fill_replication_storage_tracks(row: dict[str, Any]) -> dict[str, Any]:
    """When replication storage triad is missing, fill from post-cap constrained only.

    Never re-inflate from a raw pool headroom larger than ``sellable_qty`` /
    constrained under merged coupling — that broke ratio parity in the UI.
    """
    family = str(row.get("family") or "")
    is_repl = family.startswith("backup_veeam_replication") or family.startswith(
        "backup_zerto_replication"
    )
    kind = str(row.get("resource_kind") or row.get("display_unit") or "").lower()
    is_storage = kind in ("storage", "gb", "tb") or str(row.get("panel_key") or "").endswith(
        "_storage"
    )
    if not (is_repl and is_storage):
        return row
    # Prefer explicit dual tracks from BE (Alloc/Max/Ort already ratio-projected).
    if (
        row.get("sellable_alloc_qty") is not None
        or row.get("sellable_max_qty") is not None
        or row.get("sellable_avg_qty") is not None
    ):
        return row
    qty = row.get("sellable_qty")
    if qty is None:
        qty = row.get("sellable_constrained")
    qty_f = _as_float(qty)
    if qty_f is None:
        return row
    out = dict(row)
    out["sellable_alloc_qty"] = qty_f
    if out.get("sellable_max_qty") is None:
        out["sellable_max_qty"] = qty_f
    if out.get("sellable_avg_qty") is None:
        out["sellable_avg_qty"] = qty_f
    price = _as_float(out.get("unit_price_tl"))
    if price is not None and price > 0 and out.get("has_price") is not False:
        display_unit = str(out.get("display_unit") or "")
        price_unit = str(out.get("unit_price_unit") or display_unit)
        tl = compute_catalog_tl(
            qty_f,
            price,
            qty_unit=display_unit,
            price_unit=price_unit,
            has_price=True,
        )
        if tl is not None:
            if out.get("potential_tl_alloc") is None:
                out["potential_tl_alloc"] = tl
            if out.get("potential_tl_max") is None:
                out["potential_tl_max"] = tl
            if out.get("potential_tl_avg") is None:
                out["potential_tl_avg"] = tl
            if out.get("potential_tl") is None:
                out["potential_tl"] = tl
    return out


def prepare_service_row(row: dict[str, Any]) -> dict[str, Any]:
    row = _fill_replication_storage_tracks(row)
    unit = str(row.get("display_unit") or "")
    status = str(row.get("status") or "no_usage")
    data_quality = str(row.get("data_quality") or "")
    profile = str(row.get("sellable_profile") or "standard")
    has_infra = bool(row.get("has_infra_source"))

    service_label = row.get("service_label") or row.get("label") or ""
    if data_quality == "suspect":
        reason_hint = {
            "crm_exceeds_total": "CRM sold exceeds infra total (check units)",
            "used_exceeds_total": "Used exceeds total capacity",
            "allocation_exceeds_total": "Allocation exceeds capacity (oversubscription)",
            "unit_conversion_missing": "Unit conversion missing",
            "zero_used_with_capacity": "Zero used with positive capacity",
            "total_scale_anomaly": "Unusually large capacity value",
        }.get(str(row.get("suspect_reason") or ""), "Data quality review suggested")
        service_label = f"⚠ {service_label}"
        if row.get("suspect_reason"):
            service_label = f"{service_label}\n({reason_hint})"
    elif has_infra is False and float(row.get("crm_sold_tl") or 0) > 0:
        service_label = f"{service_label}\n(CRM entitled — infra telemetry pending)"

    crm_sold_tl = row.get("crm_sold_tl")
    used_tl = row.get("used_tl")
    potential_tl = row.get("potential_tl")
    sellable_alloc_qty = row.get("sellable_alloc_qty")
    sellable_max_qty = row.get("sellable_max_qty")
    potential_tl_alloc = row.get("potential_tl_alloc")
    potential_tl_max = row.get("potential_tl_max")
    sellable_avg_qty = row.get("sellable_avg_qty")
    potential_tl_avg = row.get("potential_tl_avg")

    if profile in ("dual_track", "allocation_only") and has_infra:
        try:
            _alloc_val = None if sellable_alloc_qty is None else float(sellable_alloc_qty)
        except (TypeError, ValueError):
            _alloc_val = None
        if _alloc_val is not None and _alloc_val <= 0:
            reason = str(row.get("sellable_constraint_reason") or "")
            service_label = f"{service_label}\n(Satılabilir 0 — {_sellable_zero_hint(reason)})"

    free_display_qty = row.get("free_qty")
    unsold_display_qty = row.get("unsold_qty")
    family = str(row.get("family") or "")
    free_mode = str(row.get("inventory_free_mode") or "infra")
    is_replication = family.startswith("backup_veeam_replication") or family.startswith(
        "backup_zerto_replication"
    )
    use_physical_free = (
        free_mode == "physical"
        or family in _PHYSICAL_FREE_FAMILIES
    )
    # Unsold fallback when API/cache omits unsold_qty: Total − CRM Sold.
    if has_infra and unsold_display_qty is None:
        total_f = _as_float(row.get("total"))
        crm_f = _as_float(row.get("crm_sold_qty")) or 0.0
        if total_f is not None:
            unsold_display_qty = max(total_f - crm_f, 0.0)
    # Free = infra empty. Valued at catalog unit price (service UOM aligned).
    free_tl = row.get("free_tl")
    if has_infra and free_display_qty is not None:
        if use_physical_free or free_tl is None:
            recomputed = _value_at_catalog_price(free_display_qty, row)
            if recomputed is not None:
                free_tl = recomputed
    unsold_tl = row.get("unsold_tl")
    if has_infra and unsold_display_qty is not None:
        if unsold_tl is None or use_physical_free:
            recomputed = _value_at_catalog_price(unsold_display_qty, row)
            if recomputed is not None:
                unsold_tl = recomputed
    hide_used = bool(row.get("inventory_hide_used"))

    unit_price_display = _catalog_unit_price(row)
    price_unit_label = _price_unit_label(row) or unit

    # Total = capacity qty only (pool used / PostDedup move to Used for NetBackup).
    total_fmt = _fmt_qty(row.get("total"), unit) if has_infra else "—"

    is_netbackup = family == "backup_netbackup" or str(row.get("panel_key") or "").startswith(
        "backup_netbackup"
    )
    pre_qty = row.get("pre_dedup_qty")
    post_qty = row.get("post_dedup_qty")
    post_tl = row.get("post_dedup_tl")
    dedup_pct = row.get("dedup_savings_pct")
    dedup_margin_tl = row.get("dedup_margin_tl")

    if is_netbackup and has_infra:
        # Transfer = job Pre; Used = pool used (+ PostDedup note).
        # Prefer backend used_tl (catalog×PreDedup, units aligned); recompute if missing.
        pre_tl = row.get("used_tl") if pre_qty is not None else None
        if pre_tl is None and pre_qty is not None:
            pre_tl = _value_at_catalog_price(pre_qty, row)
        if post_tl is None and post_qty is not None:
            post_tl = _value_at_catalog_price(post_qty, row)
        if dedup_margin_tl is None:
            try:
                margin_q = max(float(pre_qty or 0) - float(post_qty or 0), 0.0)
            except (TypeError, ValueError):
                margin_q = None
            if margin_q is not None:
                dedup_margin_tl = _value_at_catalog_price(margin_q, row)
        pre_fmt = shared.fmt_qty_tl_block(
            pre_qty,
            unit,
            pre_tl,
            qty_missing="—",
        )
        post_fmt = shared.fmt_qty_tl_block(
            post_qty, unit, post_tl, qty_missing="—",
        )
        if dedup_pct is None:
            savings_fmt = "—"
        else:
            try:
                pct_line = f"{float(dedup_pct):,.1f}%"
            except (TypeError, ValueError):
                pct_line = "—"
            margin_line = (
                shared.fmt_tl(dedup_margin_tl) if dedup_margin_tl is not None else "—"
            )
            savings_fmt = f"{pct_line}\n{margin_line}"
        pool_used = row.get("pool_used_qty")
        used_block = shared.fmt_qty_tl_block(
            pool_used, unit, None, qty_missing="—",
        )
        used_note = _fmt_dedup_note(row, unit)
        used_fmt = f"{used_block}\n{used_note}" if used_note else used_block
    else:
        pre_fmt = "—\n—"
        post_fmt = "—\n—"
        savings_fmt = "—"
        used_fmt = (
            "—\n—"
            if hide_used
            else shared.fmt_qty_tl_block(
                row.get("used_qty"),
                unit,
                used_tl,
                qty_missing="—",
            ) if has_infra else "—\n—"
        )

    return {
        "panel_key": row.get("panel_key") or "",
        "service_label": service_label,
        "family_label": row.get("family_label") or row.get("family") or "",
        "display_unit": unit,
        "total_fmt": total_fmt,
        "crm_sold_fmt": _fmt_crm_sold_block(row, unit, crm_sold_tl),
        "used_fmt": used_fmt,
        "pre_dedup_fmt": pre_fmt if has_infra else "—\n—",
        "post_dedup_fmt": post_fmt if has_infra else "—\n—",
        "dedup_savings_fmt": savings_fmt if has_infra else "—",
        "free_fmt": shared.fmt_qty_tl_block(
            free_display_qty, unit, free_tl,
            qty_missing="—",
        ) if has_infra else "—\n—",
        "unsold_fmt": shared.fmt_qty_tl_block(
            unsold_display_qty, unit, unsold_tl,
            qty_missing="—",
        ) if has_infra else "—\n—",
        "sellable_alloc_fmt": shared.fmt_qty_tl_block(
            sellable_alloc_qty, unit, potential_tl_alloc,
        ) if profile in ("dual_track", "allocation_only") or is_replication else "—\n—",
        "sellable_max_fmt": shared.fmt_qty_tl_block(
            sellable_max_qty, unit, potential_tl_max,
        ) if profile == "dual_track" or is_replication else "—\n—",
        "sellable_avg_fmt": shared.fmt_qty_tl_block(
            sellable_avg_qty, unit, potential_tl_avg,
        ) if profile == "dual_track" or is_replication else "—\n—",
        "licence_detected_fmt": (
            _fmt_qty(row.get("licence_detected_qty"), unit)
            if profile == "os_licence"
            else "—"
        ),
        "licence_gap_fmt": (
            _fmt_qty(row.get("licence_gap_qty"), unit)
            if profile == "os_licence"
            else "—"
        ),
        "licence_gap_tl_fmt": (
            shared.fmt_tl(row.get("licence_gap_tl"))
            if profile == "os_licence"
            else "—"
        ),
        "unit_price_fmt": _fmt_unit_price(unit_price_display, price_unit_label),
        "status": status,
        "data_quality": data_quality,
        "sellable_profile": profile,
        "crm_products_summary": row.get("crm_products_summary") or "",
        "infra_binding": row.get("infra_binding") or "",
        "has_infra_source": has_infra,
        "inventory_free_mode": free_mode,
        "used_is_allocation": bool(row.get("used_is_allocation") or is_replication),
    }


def filter_service_rows(rows: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    mode = (mode or "all").lower()
    if mode == "infra":
        return [r for r in rows if r.get("has_infra_source")]
    if mode == "crm_only":
        return [r for r in rows if (r.get("infra_binding") or "") == "crm_only"]
    if mode == "issues":
        return [r for r in rows if str(r.get("status") or "") in _ISSUE_STATUSES]
    return list(rows)


def filter_by_search(rows: list[dict[str, Any]], query: str | None) -> list[dict[str, Any]]:
    q = (query or "").strip().lower()
    if not q:
        return list(rows)
    out: list[dict[str, Any]] = []
    for row in rows:
        haystack = " ".join([
            str(row.get("service_label") or ""),
            str(row.get("family_label") or row.get("family") or ""),
            str(row.get("crm_products_summary") or ""),
            str(row.get("panel_key") or ""),
        ]).lower()
        if q in haystack:
            out.append(row)
    return out


def _table_style_data_conditional() -> list[dict[str, Any]]:
    styles: list[dict[str, Any]] = [
        {
            "if": {"filter_query": "{data_quality} = suspect", "column_id": "service_label"},
            "backgroundColor": "#FEF3F2",
            "color": "#B42318",
        },
    ]
    for col in _NUMERIC_COLS:
        styles.append({
            "if": {"column_id": col},
            "textAlign": "right",
            "fontVariantNumeric": "tabular-nums",
        })
    return styles


def _table_style_header_conditional() -> list[dict[str, Any]]:
    return [
        {
            "if": {"column_id": col},
            "textAlign": "right",
            "fontVariantNumeric": "tabular-nums",
        }
        for col in _NUMERIC_COLS
    ]


def _table_column_width_styles(columns: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Matched width rules for header and body cells (prevents column drift)."""
    styles: list[dict[str, Any]] = []
    for col in columns:
        col_id = col["id"]
        if col_id in ("service_label", "product_name", "family_label"):
            styles.append({
                "if": {"column_id": col_id},
                "minWidth": "220px",
                "maxWidth": "360px",
                "textAlign": "left",
            })
        elif col_id in ("display_unit", "resource_unit"):
            styles.append({
                "if": {"column_id": col_id},
                "width": "72px",
                "minWidth": "72px",
                "textAlign": "left",
            })
        elif col_id in _NUMERIC_COLS:
            styles.append({
                "if": {"column_id": col_id},
                "minWidth": "118px",
                "width": "118px",
                "textAlign": "right",
                "fontVariantNumeric": "tabular-nums",
            })
    return styles


def build_report_table(
    rows: list[dict[str, Any]],
    *,
    table_id: str,
    page_size: int = 15,
    include_family: bool = False,
    family: str | None = None,
    sellable_profile: str | None = None,
    hide_used: bool = False,
) -> dash_table.DataTable:
    data = [prepare_service_row(r) for r in rows]
    profile = sellable_profile
    if profile is None and rows:
        profile = str(rows[0].get("sellable_profile") or "standard")
    if profile is None and family:
        profile = family if family in ("dual_track", "allocation_only") else None
    row_hide_used = hide_used or any(r.get("inventory_hide_used") for r in rows)
    if family and family in _INVENTORY_VIRT_FAMILIES:
        row_hide_used = True
    # Only collapse to the standard profile for a single-family physical table
    # (grouped NetBackup / S3). A mixed/flat table must keep its Sellable columns
    # even when it contains a NetBackup row — each row still formats its own cells
    # per its own sellable_profile.
    if family in _PHYSICAL_FREE_FAMILIES:
        row_hide_used = False
        profile = "standard"
    # Grouped NetBackup accordion uses dual Pre/Post columns. Do NOT force this
    # profile on mixed flat tables (keeps Sellable Alloc/Max columns — main regression).
    if family in ("image_backup", "application_backup"):
        profile = "backup_netbackup"
        row_hide_used = False
    if family == "replication":
        profile = "replication"
        row_hide_used = False
    if family == "backup_netbackup":
        profile = "backup_netbackup"
        row_hide_used = False
    if family == "os_licence":
        profile = "os_licence"
        row_hide_used = False
    columns = columns_for_family(profile or family, hide_used=row_hide_used)
    if include_family:
        columns = [_FLAT_EXTRA_COLUMN, *columns]
    width_styles = _table_column_width_styles(columns)
    return dash_table.DataTable(
        id=table_id,
        data=data,
        columns=columns,
        page_size=page_size,
        sort_action="native",
        sort_mode="multi",
        style_table=_TABLE_STYLE_TABLE,
        style_cell=_TABLE_STYLE_CELL,
        style_header=_TABLE_STYLE_HEADER,
        style_data_conditional=[*_table_style_data_conditional(), *width_styles],
        style_header_conditional=[*_table_style_header_conditional(), *width_styles],
    )


def build_unmapped_table(rows: list[dict[str, Any]], *, table_id: str) -> dash_table.DataTable:
    data = []
    for r in rows or []:
        data.append({
            "product_name": r.get("product_name") or r.get("productid") or "",
            "resource_unit": r.get("resource_unit") or "",
            "entitled_qty": r.get("entitled_qty"),
            "entitled_amount_tl": r.get("entitled_amount_tl"),
        })
    width_styles = _table_column_width_styles(_UNMAPPED_COLUMNS)
    return dash_table.DataTable(
        id=table_id,
        data=data,
        columns=_UNMAPPED_COLUMNS,
        page_size=15,
        sort_action="native",
        sort_mode="multi",
        style_table=_TABLE_STYLE_TABLE,
        style_cell=_TABLE_STYLE_CELL,
        style_header=_TABLE_STYLE_HEADER,
        style_data_conditional=[*_table_style_data_conditional(), *width_styles],
        style_header_conditional=[*_table_style_header_conditional(), *width_styles],
    )


def _family_issue_count(panels: list[dict[str, Any]]) -> int:
    return sum(1 for p in panels if str(p.get("status") or "") in _ISSUE_STATUSES)


def _family_potential_tl(panels: list[dict[str, Any]]) -> float:
    return sum(float(p.get("potential_tl") or 0) for p in panels)


def _family_crm_tl(panels: list[dict[str, Any]]) -> float:
    return sum(float(p.get("crm_sold_tl") or 0) for p in panels)


def _sum_tl_field(panels: list[dict[str, Any]], key: str) -> float:
    total = 0.0
    any_val = False
    for p in panels:
        raw = p.get(key)
        if raw is None:
            continue
        try:
            total += float(raw)
            any_val = True
        except (TypeError, ValueError):
            continue
    return total if any_val else 0.0


def _header_money_badges(panels: list[dict[str, Any]], *, profile: str) -> list[Any]:
    """CRM Sold + Sellable chips for the accordion control."""
    badges: list[Any] = []
    crm_tl = _family_crm_tl(panels)
    badges.append(
        dmc.Badge(
            f"CRM Sold {shared.fmt_tl(crm_tl)}",
            color="teal",
            variant="light",
            size="sm",
        )
    )
    if profile == "os_licence":
        gap_qty = 0.0
        gap_tl = 0.0
        any_gap_tl = False
        for p in panels:
            try:
                gap_qty += float(p.get("licence_gap_qty") or 0.0)
            except (TypeError, ValueError):
                pass
            raw_tl = p.get("licence_gap_tl")
            if raw_tl is None:
                continue
            try:
                gap_tl += float(raw_tl)
                any_gap_tl = True
            except (TypeError, ValueError):
                continue
        if gap_qty > 0:
            badges.append(
                dmc.Badge(
                    f"Eksik lisans {gap_qty:,.0f} adet",
                    color="red",
                    variant="light",
                    size="sm",
                )
            )
        if any_gap_tl and gap_tl > 0:
            badges.append(
                dmc.Badge(
                    f"Lisanslanmalı {shared.fmt_tl(gap_tl)}",
                    color="indigo",
                    variant="light",
                    size="sm",
                )
            )
        return badges

    is_netbackup = profile == "backup_netbackup" or any(
        str(p.get("panel_key") or "").startswith("backup_netbackup")
        or str(p.get("family") or "") == "backup_netbackup"
        for p in panels
    )
    if is_netbackup:
        sellable_tl = _family_potential_tl(panels)
        if sellable_tl <= 0:
            sellable_tl = _sum_tl_field(panels, "free_tl")
        if sellable_tl > 0:
            badges.append(
                dmc.Badge(
                    f"Sellable {shared.fmt_tl(sellable_tl)}",
                    color="indigo",
                    variant="light",
                    size="sm",
                )
            )
        return badges

    use_interval = (
        profile in ("dual_track", "allocation_only", "replication")
        or any(
            str(p.get("sellable_profile") or "") in ("dual_track", "allocation_only")
            or str(p.get("family") or "").startswith("backup_veeam_replication")
            or str(p.get("family") or "").startswith("backup_zerto_replication")
            or str(p.get("family") or "") in _INVENTORY_VIRT_FAMILIES
            for p in panels
        )
    )
    if use_interval:
        sum_lo = 0.0
        sum_hi = 0.0
        any_bound = False
        for p in panels:
            filled = _fill_replication_storage_tracks(p)
            lo, hi = _row_sellable_tl_bounds(filled)
            if lo is None and hi is None:
                continue
            any_bound = True
            sum_lo += float(lo if lo is not None else hi or 0.0)
            sum_hi += float(hi if hi is not None else lo or 0.0)
        if any_bound and (sum_lo > 0 or sum_hi > 0):
            badges.append(
                dmc.Badge(
                    f"Sellable {_fmt_sellable_tl_interval(sum_lo, sum_hi)}",
                    color="indigo",
                    variant="light",
                    size="sm",
                )
            )
        return badges

    pot = _family_potential_tl(panels)
    if pot > 0:
        badges.append(
            dmc.Badge(
                f"Sellable {shared.fmt_tl(pot)}",
                color="indigo",
                variant="light",
                size="sm",
            )
        )
    return badges


def _family_free_tooltip(*, profile: str, family_key: str) -> str:
    if profile == "os_licence" or family_key == "os_licence":
        return _OS_LICENCE_TOOLTIP
    if profile == "backup_netbackup" or family_key in ("image_backup", "application_backup"):
        return _NETBACKUP_FREE_TOOLTIP
    return _FREE_COLUMN_TOOLTIP


def _header_info_icon(label: str) -> Any:
    return dmc.Tooltip(
        label=label,
        multiline=True,
        w=280,
        withArrow=True,
        children=dmc.ThemeIcon(
            DashIconify(icon="solar:info-circle-bold-duotone", width=14),
            variant="light",
            color="gray",
            size="sm",
            radius="xl",
        ),
    )


def _family_sellable_profile(family: dict[str, Any], panels: list[dict[str, Any]]) -> str:
    if family.get("sellable_profile") == "os_licence" or str(family.get("family") or "") == "os_licence":
        return "os_licence"
    if any(
        str(p.get("panel_key") or "").startswith("backup_netbackup")
        or str(p.get("family") or "") == "backup_netbackup"
        for p in (panels or [])
    ):
        return "backup_netbackup"
    if family.get("sellable_profile") == "comparison_only":
        return "comparison_only"
    if panels:
        if all(str(p.get("sellable_profile") or "") == "comparison_only" for p in panels):
            return "comparison_only"
        if all(str(p.get("sellable_profile") or "") == "os_licence" for p in panels):
            return "os_licence"
        return str(panels[0].get("sellable_profile") or "standard")
    return "standard"


def build_family_accordion(
    families: list[dict[str, Any]],
    *,
    filter_mode: str = "all",
    search_query: str | None = None,
    id_prefix: str = "crm-inventory",
) -> dmc.Accordion | None:
    items: list[dmc.AccordionItem] = []
    idx = 0
    for fam in families or []:
        panels = fam.get("panels") or []
        filtered = filter_by_search(filter_service_rows(panels, filter_mode), search_query)
        if not filtered or filter_mode == "crm_only":
            continue
        title = str(fam.get("family_label") or fam.get("label") or fam.get("family") or "Services")
        issues = _family_issue_count(filtered)
        profile = _family_sellable_profile(fam, filtered)
        family_key = str(fam.get("family") or "")
        badges: list[Any] = [
            dmc.Badge(f"{len(filtered)} services", color="gray", variant="light", size="sm"),
        ]
        badges.extend(_header_money_badges(filtered, profile=profile))
        if issues:
            badges.append(dmc.Badge(f"{issues} issues", color="red", variant="light", size="sm"))
        control_children: list[Any] = [
            dmc.Text(title, fw=600, size="sm"),
            *badges,
            _header_info_icon(_family_free_tooltip(profile=profile, family_key=family_key)),
        ]
        items.append(
            dmc.AccordionItem(
                value=f"fam-{idx}",
                children=[
                    dmc.AccordionControl(
                        children=dmc.Group(gap="xs", wrap="wrap", children=control_children),
                    ),
                    dmc.AccordionPanel(
                        children=build_report_table(
                            filtered,
                            table_id=f"{id_prefix}-family-{idx}-{INVENTORY_REPORT_SCHEMA_VERSION}",
                            sellable_profile=profile,
                            family=family_key,
                            hide_used=family_key in _INVENTORY_VIRT_FAMILIES,
                        ),
                    ),
                ],
            )
        )
        idx += 1
    if not items:
        return None
    default_open = [items[0].value] if items else []
    return dmc.Accordion(
        multiple=True,
        variant="separated",
        radius="md",
        value=default_open,
        children=items,
    )


def build_flat_view(
    payload: dict[str, Any],
    *,
    filter_mode: str = "all",
    search_query: str | None = None,
) -> dash_table.DataTable | dmc.Alert:
    rows = payload.get("panels") or []
    filtered = filter_by_search(filter_service_rows(rows, filter_mode), search_query)
    if filter_mode == "crm_only":
        filtered = [r for r in filtered if (r.get("infra_binding") or "") == "crm_only"]
    if not filtered:
        return _empty_alert()
    return build_report_table(
        filtered,
        table_id="crm-inventory-flat-table",
        page_size=25,
        include_family=True,
        sellable_profile=_FLAT_VIEW_FAMILY,
    )


def _empty_alert() -> dmc.Alert:
    return dmc.Alert(
        title="No rows match this filter",
        color="gray",
        variant="light",
        children=[
            dmc.Text("Try another filter or search term.", size="sm", mb="xs"),
            dmc.Group(gap="md", children=[
                dcc.Link("Infra sources settings", href="/settings/integrations/crm-infra-sources"),
                dcc.Link("CRM service mapping", href="/settings/integrations/crm-service-mapping"),
            ]),
        ],
    )


def build_crm_only_section(
    rows: list[dict[str, Any]],
    *,
    filter_mode: str = "all",
    search_query: str | None = None,
    table_id: str = "crm-inventory-crm-only",
) -> dmc.AccordionItem | None:
    if filter_mode not in ("all", "crm_only"):
        return None
    filtered = filter_service_rows(rows or [], "crm_only" if filter_mode == "crm_only" else "all")
    filtered = [r for r in filtered if (r.get("infra_binding") or "") == "crm_only"]
    filtered = filter_by_search(filtered, search_query)
    if not filtered:
        return None
    return dmc.AccordionItem(
        value="crm-only",
        children=[
            dmc.AccordionControl(
                children=dmc.Group(gap="xs", children=[
                    dmc.Text("CRM-only services", fw=600, size="sm"),
                    dmc.Badge(f"{len(filtered)}", color="grape", variant="light", size="sm"),
                ]),
            ),
            dmc.AccordionPanel(
                children=[
                    dmc.Text(
                        "Mapped CRM sales without infrastructure telemetry binding.",
                        size="xs", c="dimmed", mb="sm",
                    ),
                    build_report_table(filtered, table_id=table_id, sellable_profile="standard"),
                ],
            ),
        ],
    )


def prepare_product_matching_row(row: dict[str, Any]) -> dict[str, Any]:
    """Format product matching checklist row — no column drops (ADR-0032 §41)."""
    sold_qty = row.get("crm_sold_qty")
    sold_tl = row.get("crm_sold_tl")
    try:
        sold_fmt = f"{float(sold_qty or 0):,.1f}"
        if sold_tl is not None:
            sold_fmt = f"{sold_fmt}\n({float(sold_tl):,.0f} TL)"
    except (TypeError, ValueError):
        sold_fmt = str(sold_qty or "")

    tables = [str(t) for t in (row.get("infra_tables") or []) if t]
    columns = [str(c) for c in (row.get("infra_columns") or []) if c]
    usage = str(row.get("usage_source") or "").strip()
    rule = str(row.get("matching_rule") or "").strip()
    notes = str(row.get("notes") or "").strip()
    status = str(row.get("match_status") or "documented")
    approved = bool(row.get("match_approved")) or (
        status == "capacity" and bool(tables or columns)
    )
    if not notes and approved:
        via = usage or rule or "infra binding"
        target = ".".join(tables[:1] + columns[:1]) if (tables or columns) else "panel"
        if tables and columns:
            target = f"{tables[0]}.{columns[0]}"
        elif tables:
            target = tables[0]
        notes = f"Matched via {via} → {target}"

    infra_total = row.get("infra_total")
    infra_used = row.get("infra_used")
    try:
        infra_total_fmt = "—" if infra_total is None else f"{float(infra_total):,.1f}"
    except (TypeError, ValueError):
        infra_total_fmt = str(infra_total or "—")
    try:
        infra_used_fmt = "—" if infra_used is None else f"{float(infra_used):,.1f}"
    except (TypeError, ValueError):
        infra_used_fmt = str(infra_used or "—")

    if approved:
        status_fmt = "Matched (capacity)"
    elif status == "capacity":
        status_fmt = "capacity"
    else:
        status_fmt = status or "—"

    return {
        **row,
        "crm_sold_fmt": sold_fmt,
        "unit_price_fmt": _fmt_unit_price(
            row.get("unit_price_tl"),
            str(row.get("unit_price_unit") or row.get("resource_unit") or ""),
        ),
        "infra_tables_fmt": ", ".join(tables) if tables else "—",
        "infra_columns_fmt": ", ".join(columns) if columns else "—",
        "panel_key": row.get("panel_key") or "—",
        "matching_rule": rule or "—",
        "usage_source": usage or "—",
        "infra_total_fmt": infra_total_fmt,
        "infra_used_fmt": infra_used_fmt,
        "in_registry_fmt": "yes" if row.get("in_registry") else "no",
        "notes": notes,
        "match_status": status_fmt if approved else status,
        "match_approved": approved,
        "match_status_raw": status,
    }


def filter_product_matching_rows(
    rows: list[dict[str, Any]],
    status_filter: str | None,
    search_query: str | None,
) -> list[dict[str, Any]]:
    mode = (status_filter or "all").lower()
    out = list(rows or [])
    if mode in ("capacity", "documented", "sold_noted_customer_phase", "crm_only"):
        out = [r for r in out if str(r.get("match_status") or "") == mode]
    q = (search_query or "").strip().casefold()
    if q:
        out = [
            r
            for r in out
            if q in str(r.get("product_name") or "").casefold()
            or q in str(r.get("productnumber") or "").casefold()
            or q in str(r.get("matching_rule") or "").casefold()
            or q in str(r.get("usage_source") or "").casefold()
            or q in str(r.get("notes") or "").casefold()
        ]
    return out


def build_product_matching_section(
    matching: dict[str, Any] | None,
    *,
    search_query: str | None = None,
    status_filter: str = "all",
) -> Any | None:
    """Accordion item: Excel-driven product ↔ infra matching (ADR-0024)."""
    if not matching:
        return None
    products = matching.get("products") or []
    if not products:
        return None
    filtered = filter_product_matching_rows(products, status_filter, search_query)
    summary = matching.get("summary") or {}
    data = [prepare_product_matching_row(r) for r in filtered]
    return dmc.AccordionItem(
        value="product-matching",
        children=[
            dmc.AccordionControl(
                dmc.Group(
                    gap="xs",
                    children=[
                        dmc.Text("Product Matching", fw=600),
                        dmc.Badge(
                            f"{len(filtered)}/{len(products)}",
                            size="sm",
                            variant="light",
                            color="indigo",
                        ),
                        dmc.Badge(
                            f"capacity {summary.get('capacity_count', 0)}",
                            size="sm",
                            variant="outline",
                            color="teal",
                        ),
                        dmc.Badge(
                            f"documented {summary.get('documented_count', 0)}",
                            size="sm",
                            variant="outline",
                            color="gray",
                        ),
                    ],
                )
            ),
            dmc.AccordionPanel(
                children=[
                    dmc.Text(
                        "CRM sold SKUs linked to infra sources (ADR-0024). "
                        "Capacity rows enrich from inventory panels when mapped; "
                        "documented / customer-phase rows show rules only.",
                        size="xs",
                        c="dimmed",
                        mb="sm",
                    ),
                    dash_table.DataTable(
                        id="crm-inventory-product-matching",
                        columns=_PRODUCT_MATCHING_COLUMNS,
                        data=data,
                        page_size=20,
                        sort_action="native",
                        filter_action="native",
                        style_table=_TABLE_STYLE_TABLE,
                        style_cell={
                            **_TABLE_STYLE_CELL,
                            "whiteSpace": "pre-line",
                            "minWidth": "80px",
                            "maxWidth": "280px",
                        },
                        style_header=_TABLE_STYLE_HEADER,
                        style_data_conditional=[
                            {
                                "if": {"filter_query": '{match_status} = "capacity"'},
                                "backgroundColor": "#F0FDF4",
                                "color": "#166534",
                            },
                            {
                                "if": {
                                    "filter_query": '{match_status} contains "Matched"'
                                },
                                "backgroundColor": "#DCFCE7",
                                "color": "#166534",
                                "fontWeight": "600",
                            },
                            {
                                "if": {"filter_query": "{match_approved} = true"},
                                "backgroundColor": "#DCFCE7",
                                "color": "#166534",
                            },
                            {
                                "if": {
                                    "filter_query": '{match_status} = "sold_noted_customer_phase"'
                                },
                                "backgroundColor": "#FFF7ED",
                            },
                        ],
                    ),
                ],
            ),
        ],
    )


def build_unmapped_section(
    products: list[dict[str, Any]],
    *,
    table_id: str = "crm-inventory-unmapped",
) -> dmc.AccordionItem | None:
    if not products:
        return None
    return dmc.AccordionItem(
        value="unmapped",
        children=[
            dmc.AccordionControl(
                children=dmc.Group(gap="xs", children=[
                    dmc.Text("Unmapped CRM products", fw=600, size="sm"),
                    dmc.Badge(f"{len(products)}", color="orange", variant="light", size="sm"),
                ]),
            ),
            dmc.AccordionPanel(
                children=[
                    dmc.Text(
                        "Entitled sales for catalog SKUs without panel mapping.",
                        size="xs", c="dimmed", mb="sm",
                    ),
                    build_unmapped_table(products, table_id=table_id),
                ],
            ),
        ],
    )


def build_report_body(
    payload: dict[str, Any],
    *,
    filter_mode: str = "all",
    search_query: str | None = None,
    view_mode: str = "grouped",
) -> list[Any]:
    """Assemble full report body from API payload."""
    families = payload.get("families") or []
    crm_only = payload.get("crm_only_panels") or []
    unmapped = payload.get("unmapped_products") or []
    summary = payload.get("summary") or {}
    mode = (filter_mode or "all").lower()
    view = (view_mode or "grouped").lower()

    body: list[Any] = []

    if mode == "issues":
        all_rows = payload.get("panels") or []
        issue_rows = filter_by_search(filter_service_rows(all_rows, "issues"), search_query)
        if issue_rows:
            body.append(
                dmc.Paper(
                    p="md",
                    radius="md",
                    withBorder=True,
                    mb="md",
                    children=[
                        dmc.Title("Compliance issues", order=5, mb="xs"),
                        dmc.Text(
                            f"{len(issue_rows)} service(s) with overage or unsold usage",
                            size="sm", c="dimmed", mb="sm",
                        ),
                        build_report_table(
                            issue_rows,
                            table_id="crm-inventory-issues",
                            sellable_profile=_FLAT_VIEW_FAMILY,
                        ),
                    ],
                )
            )
        else:
            body.append(_empty_alert())
        return body

    if view == "flat":
        flat = build_flat_view(payload, filter_mode=mode, search_query=search_query)
        if isinstance(flat, dmc.Alert):
            body.append(flat)
        else:
            body.append(
                dmc.Paper(p="md", radius="md", withBorder=True, mb="md", children=[flat]),
            )
    else:
        accordion_items: list[Any] = []
        fam_accordion = build_family_accordion(
            families,
            filter_mode=mode,
            search_query=search_query,
        )
        if fam_accordion is not None:
            accordion_items.extend(fam_accordion.children or [])
        crm_item = build_crm_only_section(crm_only, filter_mode=mode, search_query=search_query)
        if crm_item is not None:
            accordion_items.append(crm_item)
        if mode == "all":
            unmapped_item = build_unmapped_section(unmapped)
            if unmapped_item is not None:
                accordion_items.append(unmapped_item)
            matching_item = build_product_matching_section(
                payload.get("product_matching"),
                search_query=search_query,
                status_filter="all",
            )
            if matching_item is not None:
                accordion_items.append(matching_item)
        if accordion_items:
            body.append(
                dmc.Accordion(
                    multiple=True,
                    variant="separated",
                    radius="md",
                    value=[accordion_items[0].value],
                    children=accordion_items,
                )
            )
        else:
            body.append(_empty_alert())

    note = summary.get("note") or ""
    if note:
        body.append(
            dmc.Alert(
                title="Scope note",
                color="blue",
                variant="light",
                mt="md",
                icon=None,
                children=note,
            )
        )

    if not body:
        return [_empty_alert()]

    return body
