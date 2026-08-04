"""Colocation Configuration ekranı için saf yardımcılar (Dash callback'i yok)."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import dash_mantine_components as dmc
from dash import html
from dash_iconify import DashIconify

from src.utils.ui_tokens import PRIMARY, th_center, th_left, th_right

# Fixed column widths (px) so the table hugs its content instead of
# sprawling across a wide settings card with uneven gaps.
_COL_WIDTHS = {
    "role": "320px",
    "racks": "90px",
    "capacity": "120px",
    "free": "110px",
    "sellable": "110px",
}


def merge_rules_with_catalog(
    rules: Sequence[Mapping[str, Any]] | None,
    catalog: Sequence[Mapping[str, Any]] | None,
    breakdown: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Katalog + kayıtlı kural + canlı rack sayılarını tek satır listesine indir.

    Katalog otoritedir: kuralı olmayan bir rol de listelenir ve ``sellable``
    True + ``is_new`` True ile gelir -- motorun kayıtsız rolü sellable sayma
    kuralının ekrandaki karşılığı. Ters yönde (kuralı olup katalogda olmayan
    rol) satır yine gösterilir, aksi hâlde silinemeyen görünmez bir kural
    kalırdı.
    """
    by_rule = {str(r.get("role_id")).strip(): bool(r.get("sellable")) for r in rules or []}
    by_break = {str(b.get("role_id")).strip(): b for b in breakdown or []}
    names = {str(c.get("role_id")).strip(): (c.get("role_name") or "") for c in catalog or []}

    out: list[dict[str, Any]] = []
    for role_id in sorted(set(names) | set(by_rule)):
        stats = by_break.get(role_id) or {}
        out.append({
            "role_id": role_id,
            "role_name": names.get(role_id) or "UNKNOWN",
            "sellable": by_rule.get(role_id, True),
            "is_new": role_id not in by_rule,
            "rack_count": int(stats.get("rack_count") or 0),
            "capacity_u": int(stats.get("capacity_u") or 0),
            "free_u": int(stats.get("free_u") or 0),
        })
    return out


def preview_sellable_free_u(
    merged: Sequence[Mapping[str, Any]],
    overrides: Mapping[str, bool] | None = None,
) -> int:
    """Verilen switch durumuyla sellable free U ne olurdu?

    ``overrides`` kaydedilmemiş ekran durumudur; boşsa kayıtlı kural geçerli.
    """
    ov = overrides or {}
    total = 0
    for row in merged:
        role_id = str(row.get("role_id"))
        sellable = ov.get(role_id, bool(row.get("sellable")))
        if sellable:
            total += int(row.get("free_u") or 0)
    return total


def fmt_u(n: int) -> str:
    """Binlik ayraçlı U sayısı: 3503 -> '3.503'."""
    return f"{int(n):,}".replace(",", ".")


def render_sellable_total(saved: int, pending: int):
    """`#coloc-cfg-preview` içeriği.

    Değişmemişse tek büyük sayı; switch'ler henüz kaydedilmemiş bir
    değişikliği işaret ediyorsa mevcut -> yeni değer + fark birlikte
    gösterilir. Bu, ekranın var olma sebebi olan sayı olduğu için kartın
    en güçlü görsel unsuru bu olmalı -- Kaydet butonundan daha belirgin.
    """
    if pending == saved:
        return dmc.Text(fmt_u(saved), fw=800, size="32px", c="indigo", style={"lineHeight": 1.1})
    diff = pending - saved
    sign = "+" if diff >= 0 else "−"
    diff_color = "teal" if diff >= 0 else "red"
    return dmc.Group(gap=10, align="baseline", wrap="wrap", children=[
        dmc.Text(fmt_u(saved), fw=500, size="lg", c="dimmed", style={"textDecoration": "line-through"}),
        DashIconify(icon="solar:arrow-right-bold", width=18, color=PRIMARY),
        dmc.Text(fmt_u(pending), fw=800, size="32px", c="indigo", style={"lineHeight": 1.1}),
        dmc.Badge(f"{sign}{fmt_u(abs(diff))}", color=diff_color, variant="light", size="sm"),
    ])


def build_role_table(merged: Sequence[Mapping[str, Any]]) -> html.Div:
    """Rol tablosu; her satırda pattern-matching id taşıyan bir Switch.

    Header/hücre dili src.utils.ui_tokens (th_left/center/right) -- ayar
    ekranlarında (bkz. netbox_viz_ui.build_exclusion_table, iam/roles.py)
    kullanılan ortak tablo idiomu. Sayısal sütunlar sağa, rol adı sola
    hizalı; Sellable switch sütunu sabit genişlikte ortalanır ki satır
    genişledikçe kenara sürüklenmesin.
    """
    head = html.Thead(html.Tr([
        html.Th("Role", style={**th_left(), "width": _COL_WIDTHS["role"]}),
        html.Th("Racks", style={**th_right(), "width": _COL_WIDTHS["racks"]}),
        html.Th("Capacity U", style={**th_right(), "width": _COL_WIDTHS["capacity"]}),
        html.Th("Free U", style={**th_right(), "width": _COL_WIDTHS["free"]}),
        html.Th("Sellable?", style={**th_center(), "width": _COL_WIDTHS["sellable"]}),
    ]))
    rows = []
    for row in merged:
        label = f"{row['role_name']} ({row['role_id']})"
        cells = [
            html.Td(
                dmc.Stack(gap=4, children=[
                    dmc.Text(label, size="sm", fw=500),
                    dmc.Badge("yeni — karar verilmedi", color="orange", variant="light", size="xs")
                    if row.get("is_new") else None,
                ]),
                style={"padding": "10px 12px"},
            ),
            html.Td(fmt_u(row["rack_count"]), style={"padding": "10px 12px", "textAlign": "right"}),
            html.Td(fmt_u(row["capacity_u"]), style={"padding": "10px 12px", "textAlign": "right"}),
            html.Td(fmt_u(row["free_u"]), style={"padding": "10px 12px", "textAlign": "right"}),
            html.Td(
                dmc.Switch(
                    id={"type": "coloc-cfg-switch", "role": row["role_id"]},
                    checked=bool(row["sellable"]),
                    size="sm",
                    color="indigo",
                ),
                style={"padding": "10px 12px", "textAlign": "center"},
            ),
        ]
        rows.append(html.Tr(cells, style={"borderBottom": "1px solid #eef1f4"}))
    table = dmc.Table(
        children=[head, html.Tbody(rows)],
        striped=True,
        highlightOnHover=True,
        withTableBorder=False,
        withColumnBorders=False,
        style={"tableLayout": "fixed", "width": "750px"},
    )
    return html.Div(table, style={"overflowX": "auto"})
