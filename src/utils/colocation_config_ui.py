"""Colocation Configuration ekranı için saf yardımcılar (Dash callback'i yok)."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import dash_mantine_components as dmc
from dash import html


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


def build_role_table(merged: Sequence[Mapping[str, Any]]) -> dmc.Table:
    """Rol tablosu; her satırda pattern-matching id taşıyan bir Switch."""
    head = html.Thead(html.Tr([
        html.Th("Role"), html.Th("Racks"), html.Th("Capacity U"),
        html.Th("Free U"), html.Th("Sellable?"),
    ]))
    rows = []
    for row in merged:
        label = f"{row['role_name']} ({row['role_id']})"
        cells = [
            html.Td(dmc.Group(gap=6, children=[
                dmc.Text(label, size="sm"),
                dmc.Badge("yeni — karar verilmedi", color="orange", variant="light", size="xs")
                if row.get("is_new") else None,
            ])),
            html.Td(f"{row['rack_count']:,}".replace(",", ".")),
            html.Td(f"{row['capacity_u']:,}".replace(",", ".")),
            html.Td(f"{row['free_u']:,}".replace(",", ".")),
            html.Td(dmc.Switch(
                id={"type": "coloc-cfg-switch", "role": row["role_id"]},
                checked=bool(row["sellable"]),
                size="sm",
                color="indigo",
            )),
        ]
        rows.append(html.Tr(cells))
    return dmc.Table(children=[head, html.Tbody(rows)], striped=True, highlightOnHover=True)
