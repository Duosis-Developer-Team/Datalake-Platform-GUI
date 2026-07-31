"""Backup license compliance strip + NetBackup KPI helpers (Summary / Backup only).

Surfaces: Customer View Summary + Backup (K-03). Not Billing.
"""
from __future__ import annotations

from typing import Any

import dash_mantine_components as dmc
from dash import html

from src.components.sold_vs_used_panel import filter_efficiency_rows

# Display labels for shared.backup.license_compliance categories.
CATEGORY_LABELS: dict[str, str] = {
    "veeam_backup": "Veeam Backup",
    "veeam_replication": "Veeam Replication",
    "zerto": "Zerto",
}

# Statuses shown on the OK / No license strip (usage must exist).
_STRIP_STATUSES = frozenset({"ok", "unsold_usage"})


def visible_compliance_rows(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Keep rows with usage that need an OK / No-license badge (K-03)."""
    out: list[dict[str, Any]] = []
    for r in rows or []:
        status = str(r.get("status") or "").lower()
        if status not in _STRIP_STATUSES:
            continue
        try:
            usage = float(r.get("usage_qty") or 0)
        except (TypeError, ValueError):
            usage = 0.0
        if usage <= 0:
            continue
        out.append(r)
    return out


def license_badge_label(status: str | None) -> str:
    s = (status or "").lower()
    if s == "ok":
        return "OK"
    if s == "unsold_usage":
        return "No license"
    if s == "crm_only":
        return "CRM only"
    return "N/A"


def license_badge_color(status: str | None) -> str:
    s = (status or "").lower()
    if s == "ok":
        return "green"
    if s == "unsold_usage":
        return "red"
    return "gray"


def license_status_badge(status: str | None) -> dmc.Badge:
    """Green OK / red No license badge for a compliance row status."""
    s = (status or "").lower()
    return dmc.Badge(
        license_badge_label(s),
        color=license_badge_color(s),
        variant="filled" if s in ("ok", "unsold_usage") else "outline",
        size="sm",
        radius="xl",
    )


def license_compliance_to_overusage_rows(
    rows: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Map Veeam/Zerto license_compliance rows into Summary overusage table shape.

    Keeps rows with usage that are either unsold or over sold quantity so they
    pass ``filter_overusage_rows`` (sold / used / loss / status columns).
    """
    out: list[dict[str, Any]] = []
    for r in rows or []:
        category = str(r.get("category") or "").strip()
        if category not in CATEGORY_LABELS:
            continue
        try:
            usage = float(r.get("usage_qty") or 0)
        except (TypeError, ValueError):
            usage = 0.0
        try:
            sold = float(r.get("sold_qty") or 0)
        except (TypeError, ValueError):
            sold = 0.0
        status = str(r.get("status") or "").lower()
        overage = max(0.0, usage - sold)
        if status == "unsold_usage" and usage > 0:
            table_status = "unsold_usage"
            if overage <= 0:
                overage = usage
        elif overage > 0:
            table_status = "over"
        else:
            continue

        loss = r.get("overage_loss_tl")
        if loss is None:
            loss = r.get("loss")
        out.append(
            {
                "category_code": category,
                "category_label": CATEGORY_LABELS.get(category, category),
                "entitled_qty": sold,
                "sold_qty": sold,
                "used_qty": usage,
                "overage_qty": overage,
                "overage_loss_tl": loss,
                "status": table_status,
                "resource_unit": str(r.get("resource_unit") or ""),
            }
        )
    return out


def _row_matches_netbackup_category(row: dict[str, Any], category: str) -> bool:
    cat = (category or "").strip().lower()
    needle = f"backup_netbackup_{cat}"
    code = str(row.get("category_code") or "").lower()
    panel = str(row.get("panel_key") or row.get("page_key") or "").lower()
    label = str(row.get("category_label") or "").lower()
    if needle in code or needle in panel:
        return True
    if cat == "image" and ("imaj" in label or "image" in label):
        return True
    if cat == "application" and ("uygulama" in label or "application" in label):
        return True
    return False


def filter_netbackup_efficiency_rows(
    rows: list[dict[str, Any]] | None,
    category: str,
    *,
    allow_legacy_fallback: bool = True,
) -> list[dict[str, Any]]:
    """Prefer ``backup.netbackup.{image|application}``; else filter legacy binding."""
    cat = (category or "").strip().lower()
    if cat not in ("image", "application"):
        return filter_efficiency_rows(rows, "backup.netbackup")

    specific = filter_efficiency_rows(rows, f"backup.netbackup.{cat}")
    if specific:
        return specific

    legacy = filter_efficiency_rows(rows, "backup.netbackup")
    if not legacy:
        return []

    matched = [r for r in legacy if _row_matches_netbackup_category(r, cat)]
    if matched:
        return matched
    if not allow_legacy_fallback:
        return []
    # Undifferentiated legacy bucket (no image/app split yet).
    has_split = any(
        _row_matches_netbackup_category(r, "image")
        or _row_matches_netbackup_category(r, "application")
        for r in legacy
    )
    if has_split:
        return []
    return legacy


def _sum_sold_used(rows: list[dict[str, Any]]) -> tuple[float, float]:
    sold = 0.0
    used = 0.0
    for r in rows:
        try:
            sold += float(
                r.get("entitled_qty")
                if r.get("entitled_qty") is not None
                else r.get("sold_qty")
                or 0
            )
        except (TypeError, ValueError):
            pass
        try:
            used += float(r.get("used_qty") or 0)
        except (TypeError, ValueError):
            pass
    return sold, used


def _category_pre_post_gib(
    backup_assets: dict[str, Any] | None,
    category: str,
) -> tuple[float, float]:
    nb = (backup_assets or {}).get("netbackup") or {}
    block = nb.get(category) if isinstance(nb, dict) else None
    if not isinstance(block, dict):
        block = {}
    try:
        pre = float(block.get("pre_dedup_size_gib") or 0)
    except (TypeError, ValueError):
        pre = 0.0
    try:
        post = float(block.get("post_dedup_size_gib") or 0)
    except (TypeError, ValueError):
        post = 0.0
    return pre, post


def build_netbackup_kpi_defs(
    efficiency_rows: list[dict[str, Any]] | None,
    backup_assets: dict[str, Any] | None,
    *,
    show_post_dedup: bool,
) -> list[dict[str, Any]]:
    """Pure KPI definitions for Image / Application summary strip.

    Each dict: category, label, sold, used_pre, post (optional), margin (optional),
    savings_pct (optional), has_signal.
    """
    defs: list[dict[str, Any]] = []
    for cat, label in (("image", "Image Backup"), ("application", "Application Backup")):
        # Prefer split scopes; attach undifferentiated legacy only to application once.
        rows = filter_netbackup_efficiency_rows(
            efficiency_rows, cat, allow_legacy_fallback=(cat == "application")
        )
        sold, used_from_eff = _sum_sold_used(rows)
        pre_asset, post_asset = _category_pre_post_gib(backup_assets, cat)
        used_pre = used_from_eff if used_from_eff > 0 else pre_asset
        margin = max(used_pre - post_asset, 0.0) if show_post_dedup else None
        savings_pct = None
        if show_post_dedup and used_pre > 0 and post_asset >= 0:
            savings_pct = round((1.0 - (post_asset / used_pre)) * 100.0, 1)
        has_signal = sold > 0 or used_pre > 0 or (show_post_dedup and post_asset > 0)
        defs.append(
            {
                "category": cat,
                "label": label,
                "sold": sold,
                "used_pre": used_pre,
                "post": post_asset if show_post_dedup else None,
                "margin": margin,
                "savings_pct": savings_pct if show_post_dedup else None,
                "has_signal": has_signal,
            }
        )
    return defs


def build_license_compliance_strip(
    rows: list[dict[str, Any]] | None,
) -> html.Div:
    """Compact badge strip: green OK / red No license when usage exists."""
    visible = visible_compliance_rows(rows)
    if not visible:
        return html.Div()

    badges = []
    for r in visible:
        cat = str(r.get("category") or "")
        label = CATEGORY_LABELS.get(cat, cat.replace("_", " ").title() or "License")
        badges.append(
            dmc.Group(
                gap=6,
                align="center",
                children=[
                    dmc.Text(label, size="xs", fw=600, c="#2B3674"),
                    license_status_badge(str(r.get("status"))),
                ],
            )
        )

    return html.Div(
        className="nexus-card",
        style={"padding": "12px 16px", "marginBottom": "12px"},
        children=[
            dmc.Group(
                justify="space-between",
                align="center",
                wrap="wrap",
                gap="sm",
                children=[
                    dmc.Text("Backup license compliance", size="sm", fw=700, c="#2B3674"),
                    dmc.Group(gap="md", wrap="wrap", children=badges),
                ],
            )
        ],
    )


def build_license_compliance_cards(
    rows: list[dict[str, Any]] | None,
) -> html.Div | None:
    """Detailed compliance cards when usage exists (replaces CRM-only license table)."""
    visible = visible_compliance_rows(rows)
    if not visible:
        return None

    cards = []
    for r in visible:
        cat = str(r.get("category") or "")
        label = CATEGORY_LABELS.get(cat, cat.replace("_", " ").title() or "License")
        try:
            usage = float(r.get("usage_qty") or 0)
        except (TypeError, ValueError):
            usage = 0.0
        try:
            sold = float(r.get("sold_qty") or 0)
        except (TypeError, ValueError):
            sold = 0.0
        skus = r.get("skus") or []
        sku_txt = ", ".join(str(s) for s in skus) if skus else "—"
        cards.append(
            html.Div(
                className="nexus-card",
                style={"padding": "14px 16px", "marginBottom": "8px"},
                children=[
                    dmc.Group(
                        justify="space-between",
                        align="flex-start",
                        children=[
                            dmc.Stack(
                                gap=2,
                                children=[
                                    dmc.Text(label, fw=700, size="sm", c="#2B3674"),
                                    dmc.Text(f"SKUs: {sku_txt}", size="xs", c="#A3AED0"),
                                ],
                            ),
                            license_status_badge(str(r.get("status"))),
                        ],
                    ),
                    dmc.Group(
                        gap="lg",
                        mt="sm",
                        children=[
                            dmc.Text(f"Usage: {usage:,.0f}", size="xs", c="#2B3674", fw=600),
                            dmc.Text(f"Sold: {sold:,.0f}", size="xs", c="#2B3674", fw=600),
                        ],
                    ),
                ],
            )
        )

    return html.Div(
        children=[
            dmc.Text("License compliance", size="sm", fw=700, c="#2B3674", mb="xs"),
            *cards,
        ]
    )


def build_backup_kpi_strip(
    kpi_defs: list[dict[str, Any]] | None,
    *,
    show_post_dedup: bool,
    include_deeplink: bool = True,
) -> html.Div:
    """Summary Backup KPI strip with optional deeplink controls to Backup categories."""
    tiles: list = []
    for d in kpi_defs or []:
        if not d.get("has_signal"):
            continue
        cat = str(d.get("category") or "")
        label = str(d.get("label") or cat)
        sold = float(d.get("sold") or 0)
        used = float(d.get("used_pre") or 0)
        lines = [
            dmc.Text(label, size="xs", fw=700, c="#2B3674"),
            dmc.Text(
                f"Sold {sold:,.2f} · Used (pre) {used:,.2f}",
                size="xs",
                c="#707EAE",
            ),
        ]
        if show_post_dedup and d.get("post") is not None:
            post = float(d.get("post") or 0)
            margin = float(d.get("margin") or 0)
            pct = d.get("savings_pct")
            pct_txt = f"{pct:.1f}%" if pct is not None else "—"
            lines.append(
                dmc.Text(
                    f"Post {post:,.2f} · Margin {margin:,.2f} ({pct_txt})",
                    size="xs",
                    c="#4318FF",
                    fw=600,
                )
            )
        if include_deeplink and cat:
            lines.append(
                dmc.Button(
                    "Open in Backup",
                    id={"type": "customer-backup-deeplink", "category": cat},
                    size="compact-xs",
                    variant="light",
                    color="indigo",
                    mt=4,
                    n_clicks=0,
                )
            )
        tiles.append(
            html.Div(
                style={
                    "padding": "14px 12px",
                    "borderRadius": "12px",
                    "background": "#F4F7FE",
                },
                children=dmc.Stack(gap=2, children=lines),
            )
        )

    if not tiles:
        return html.Div()

    return html.Div(
        children=[
            dmc.Text("Backup — sold vs used", size="sm", fw=700, c="#2B3674", mb="xs"),
            dmc.SimpleGrid(
                cols={"base": 1, "sm": 2},
                spacing="md",
                children=tiles,
            ),
        ]
    )


def netbackup_category_table_rows(
    *,
    pre_gib: float,
    post_gib: float,
    dedup_fact: str | None,
    show_post_dedup: bool,
) -> list[tuple[str, str]]:
    """Metric labels for NetBackup category panel (perspective-gated)."""
    rows: list[tuple[str, str]] = [
        ("Pre-Dedup Size", f"{float(pre_gib):.2f} GiB"),
    ]
    if not show_post_dedup:
        return rows
    margin = max(float(pre_gib) - float(post_gib), 0.0)
    rows.extend(
        [
            ("Post-Dedup Size", f"{float(post_gib):.2f} GiB"),
            ("Dedup Ratio", str(dedup_fact or "1x")),
            ("Dedup Margin", f"{margin:.2f} GiB"),
        ]
    )
    return rows
