"""UI for Collector script healthcheck (hmdl_datalake_collector_probe_log).

Coverage reports whether metrics arrived; this panel reports whether each collector
script ran successfully on each endpoint. Matrix grain is script × DC.
"""

from __future__ import annotations

from collections import defaultdict

import dash_mantine_components as dmc
from dash import html

from src.utils.ui_tokens import kpi_card

PROBE_STATUS_LABELS: dict[str, str] = {
    "ok": "Tümü OK",
    "partial": "Kısmi",
    "fail": "Tümü fail",
    "unknown": "Veri yok",
}

PROBE_STATUS_COLORS: dict[str, str] = {
    "ok": "green",
    "partial": "orange",
    "fail": "red",
    "unknown": "gray",
}

# Category → who fixes it. This is the whole point of the screen.
REASON_LABELS: dict[str, str] = {
    "ok": "Başarılı",
    "script_missing": "Script yok (NiFi deploy)",
    "auth": "Kimlik / yetki",
    "network": "Ağ erişimi",
    "timeout": "Süre aşımı",
    "no_data": "Çalıştı, veri üretmedi",
    "runner": "Probe runner",
    "other": "Diğer",
}

REASON_COLORS: dict[str, str] = {
    "ok": "green",
    "script_missing": "violet",
    "auth": "red",
    "network": "orange",
    "timeout": "yellow",
    "no_data": "blue",
    "runner": "grape",
    "other": "gray",
}

PRODUCT_LABELS: dict[str, str] = {
    "vmware": "VMware",
    "nutanix": "Nutanix",
    "ibm": "IBM Power",
    "backup": "Backup",
    "other": "Diğer",
}

_CELL_ID = "hmdl-probe-cell"
_MATRIX_STORE = "hmdl-probe-selected-cell"


def probe_status_badge(status: str | None, *, size: str = "sm") -> dmc.Badge:
    s = str(status or "unknown")
    return dmc.Badge(
        PROBE_STATUS_LABELS.get(s, s),
        color=PROBE_STATUS_COLORS.get(s, "gray"),
        variant="light",
        size=size,
    )


def probe_inline_badge(row: dict) -> dmc.Tooltip | None:
    """Compact `2/3 script` badge for a Coverage parent row."""
    total = row.get("probe_total")
    if not total:
        return None
    ok = int(row.get("probe_ok") or 0)
    status = str(row.get("probe_status") or "unknown")
    return dmc.Tooltip(
        label=str(row.get("probe_reasons") or "Tüm collector script'leri başarılı"),
        multiline=True,
        w=280,
        withArrow=True,
        children=dmc.Badge(
            f"probe {ok}/{int(total)}",
            color=PROBE_STATUS_COLORS.get(status, "gray"),
            variant="dot",
            size="xs",
        ),
    )


def _fmt_ts(value) -> str:
    text = str(value or "")
    return text[:16].replace("T", " ") if text else "—"


def build_probe_summary(summary: dict, scripts: list[dict]) -> dmc.SimpleGrid:
    summary = summary or {}
    ok = int(summary.get("ok") or 0)
    fail = int(summary.get("fail") or 0)
    total = ok + fail
    return dmc.SimpleGrid(
        cols={"base": 1, "sm": 3},
        spacing="md",
        children=[
            kpi_card(
                "Başarılı çalıştırma",
                f"{ok}/{total}",
                icon="solar:play-circle-bold-duotone",
                color="indigo",
            ),
            kpi_card(
                "Fail",
                str(fail),
                trend="endpoint × script",
                icon="solar:danger-triangle-bold-duotone",
                color="red" if fail else "green",
            ),
            kpi_card(
                "Endpoint",
                str(summary.get("endpoints") or 0),
                trend=f"{summary.get('scripts') or 0} script",
                icon="solar:server-bold-duotone",
                color="blue",
            ),
        ],
    )


def _cell(cell: dict | None, probe_id: str, dc: str) -> html.Td:
    base = {"padding": "4px", "textAlign": "center"}
    if not cell or not cell.get("total"):
        return html.Td("·", style={**base, "color": "#ced4da"})
    status = str(cell.get("status") or "unknown")
    ok = int(cell.get("ok") or 0)
    total = int(cell.get("total") or 0)
    return html.Td(
        dmc.Button(
            f"{ok}/{total}",
            id={"type": _CELL_ID, "probe": probe_id, "dc": dc},
            color=PROBE_STATUS_COLORS.get(status, "gray"),
            variant="light" if status != "ok" else "subtle",
            size="compact-xs",
            fullWidth=True,
            radius="sm",
        ),
        style=base,
    )


def build_probe_matrix(scripts: list[dict], matrix: list[dict], dcs: list[str]) -> html.Div:
    """Script (row) × DC (column); a cell is `ok/total` and opens the endpoint list."""
    scripts = scripts or []
    dcs = [d for d in (dcs or []) if d]
    if not scripts or not dcs:
        return dmc.Alert(
            "Probe kaydı yok. AWX collector-probe job template'i henüz koşmamış olabilir.",
            color="gray",
            variant="light",
        )

    by_cell = {(str(c.get("probe_id")), str(c.get("dc"))): c for c in (matrix or [])}
    header = html.Tr(
        [
            html.Th("Ürün", style={"textAlign": "left", "padding": "6px", "fontSize": "12px"}),
            html.Th("Script", style={"textAlign": "left", "padding": "6px", "fontSize": "12px"}),
            html.Th("Genel skor", style={"textAlign": "left", "padding": "6px", "fontSize": "12px"}),
            *[
                html.Th(dc, style={"textAlign": "center", "padding": "6px", "fontSize": "12px"})
                for dc in dcs
            ],
        ]
    )

    rows = []
    for s in scripts:
        probe_id = str(s.get("probe_id") or "")
        product = str(s.get("product") or "other")
        ok = int(s.get("ok") or 0)
        endpoints = int(s.get("endpoints") or 0)
        rows.append(
            html.Tr(
                style={"borderBottom": "1px solid #eef1f4"},
                children=[
                    html.Td(
                        dmc.Badge(
                            PRODUCT_LABELS.get(product, product),
                            variant="light",
                            size="xs",
                            color="indigo",
                        ),
                        style={"padding": "6px"},
                    ),
                    html.Td(
                        dmc.Group(
                            gap=4,
                            wrap="nowrap",
                            children=[
                                dmc.Text(probe_id, fw=600, size="xs"),
                                dmc.Badge("heavy", size="xs", variant="outline", color="grape")
                                if s.get("bucket") == "heavy"
                                else None,
                            ],
                        ),
                        style={"padding": "6px"},
                    ),
                    html.Td(
                        dmc.Group(
                            gap=6,
                            wrap="nowrap",
                            children=[
                                dmc.Text(f"{ok}/{endpoints}", size="xs", fw=600),
                                probe_status_badge(str(s.get("status") or ""), size="xs"),
                            ],
                        ),
                        style={"padding": "6px"},
                    ),
                    *[_cell(by_cell.get((probe_id, dc)), probe_id, dc) for dc in dcs],
                ],
            )
        )

    return html.Div(
        style={"overflowX": "auto"},
        children=[
            html.Table(
                [header, *rows],
                style={"width": "100%", "borderCollapse": "collapse", "minWidth": "760px"},
            )
        ],
    )


def build_probe_reason_cards(reasons: list[dict]) -> html.Div:
    """Failures grouped by owner: deploy vs credentials vs network vs 'ran, no data'."""
    reasons = reasons or []
    if not reasons:
        return dmc.Alert("Fail eden collector script yok.", color="green", variant="light")

    by_category: dict[str, list[dict]] = defaultdict(list)
    for r in reasons:
        by_category[str(r.get("category") or "other")].append(r)

    cards = []
    for category, items in sorted(
        by_category.items(), key=lambda kv: -sum(int(i.get("count") or 0) for i in kv[1])
    ):
        total = sum(int(i.get("count") or 0) for i in items)
        cards.append(
            dmc.Paper(
                p="sm",
                withBorder=True,
                radius="md",
                children=[
                    dmc.Group(
                        justify="space-between",
                        mb=6,
                        children=[
                            dmc.Badge(
                                REASON_LABELS.get(category, category),
                                color=REASON_COLORS.get(category, "gray"),
                                variant="light",
                                size="sm",
                            ),
                            dmc.Text(f"{total} fail", size="xs", c="dimmed"),
                        ],
                    ),
                    dmc.Stack(
                        gap=2,
                        children=[
                            dmc.Text(
                                f"{i.get('count')}× {i.get('reason')} "
                                f"· {', '.join(i.get('probe_ids') or [])} "
                                f"· {', '.join(i.get('dcs') or [])}",
                                size="xs",
                                c="dimmed",
                            )
                            for i in sorted(items, key=lambda x: -int(x.get("count") or 0))
                        ],
                    ),
                ],
            )
        )
    return dmc.SimpleGrid(cols={"base": 1, "md": 2, "xl": 3}, spacing="md", children=cards)


def build_probe_endpoint_table(items: list[dict], *, title: str | None = None) -> html.Div:
    items = items or []
    if not items:
        return dmc.Alert("Bu seçimde probe kaydı yok.", color="gray", variant="light")

    header = html.Tr(
        [
            html.Th(h, style={"textAlign": "left", "padding": "6px", "fontSize": "12px"})
            for h in ("Script", "Endpoint", "IP", "DC", "Sonuç", "Sebep", "Süre", "Son çalışma")
        ]
    )
    body = []
    for r in sorted(items, key=lambda x: (bool(x.get("success")), str(x.get("dc") or ""))):
        success = bool(r.get("success"))
        category = str(r.get("reason_category") or "other")
        duration = r.get("duration_sec")
        body.append(
            html.Tr(
                style={"borderBottom": "1px solid #f1f3f5"},
                children=[
                    html.Td(str(r.get("probe_id") or "—"), style={"padding": "6px", "fontSize": "12px"}),
                    html.Td(
                        str(r.get("entity_name") or "—"),
                        style={"padding": "6px", "fontSize": "12px", "fontWeight": 600},
                    ),
                    html.Td(str(r.get("target_host") or "—"), style={"padding": "6px", "fontSize": "12px"}),
                    html.Td(str(r.get("dc") or "—"), style={"padding": "6px", "fontSize": "12px"}),
                    html.Td(
                        dmc.Badge(
                            "OK" if success else "FAIL",
                            color="green" if success else "red",
                            variant="light",
                            size="xs",
                        ),
                        style={"padding": "6px"},
                    ),
                    html.Td(
                        dmc.Group(
                            gap=6,
                            wrap="nowrap",
                            children=[
                                dmc.Badge(
                                    REASON_LABELS.get(category, category),
                                    color=REASON_COLORS.get(category, "gray"),
                                    variant="dot",
                                    size="xs",
                                )
                                if not success
                                else None,
                                dmc.Text(str(r.get("reason") or "—"), size="xs", c="dimmed"),
                            ],
                        ),
                        style={"padding": "6px"},
                    ),
                    html.Td(
                        f"{duration:.1f} sn" if isinstance(duration, (int, float)) else "—",
                        style={"padding": "6px", "fontSize": "12px"},
                    ),
                    html.Td(
                        _fmt_ts(r.get("finished_at")),
                        style={"padding": "6px", "fontSize": "11px", "color": "#666"},
                    ),
                ],
            )
        )

    children: list = []
    if title:
        children.append(dmc.Text(title, fw=700, size="sm", mb=6))
    children.append(
        html.Div(
            style={"overflowX": "auto"},
            children=[
                html.Table([header, *body], style={"width": "100%", "borderCollapse": "collapse"})
            ],
        )
    )
    return html.Div(children)


def build_probe_runner_alert(errors: list[dict]) -> dmc.Alert | None:
    """Runner faults are not collector verdicts — never mix them into the matrix."""
    errors = errors or []
    if not errors:
        return None
    return dmc.Alert(
        [
            dmc.Text(
                f"{len(errors)} koşuda probe altyapısı çıktıyı ayrıştıramadı "
                "(collector script sonucundan bağımsız). Bu koşulardaki endpoint'ler "
                "matris skoruna dahil edilmedi.",
                size="sm",
            ),
            dmc.Stack(
                gap=2,
                mt=6,
                children=[
                    dmc.Text(
                        f"{e.get('dc')} · {e.get('run_id')} · {e.get('reason')}",
                        size="xs",
                        c="dimmed",
                    )
                    for e in errors[:5]
                ],
            ),
        ],
        title="Probe altyapı hatası",
        color="grape",
        variant="light",
    )


def build_probe_section(data: dict, *, selected: tuple[str, str] | None = None) -> html.Div:
    """Healthcheck panel: KPI → matrix → endpoint detail → fail summary → runner errors."""
    data = data or {}
    scripts = data.get("scripts") or []
    items = data.get("items") or []

    if selected:
        probe_id, dc = selected
        detail = [
            i
            for i in items
            if str(i.get("probe_id")) == probe_id and str(i.get("dc")) == dc
        ]
        detail_title = f"{probe_id} · {dc} — {len(detail)} endpoint"
    else:
        detail = [i for i in items if not i.get("success")]
        detail_title = f"Fail eden tüm çalıştırmalar ({len(detail)})"

    blocks: list = [
        build_probe_summary(data.get("summary") or {}, scripts),
        dmc.Space(h="md"),
        dmc.Text(
            "Her hücre = o DC'deki başarılı/toplam endpoint. Detay için hücreye tıkla.",
            size="xs",
            c="dimmed",
            mb=6,
        ),
        build_probe_matrix(scripts, data.get("matrix") or [], data.get("dcs") or []),
        dmc.Space(h="lg"),
        build_probe_endpoint_table(detail, title=detail_title),
        dmc.Space(h="lg"),
        dmc.Text("Hata nedenleri özeti", fw=700, size="sm", mb=6),
        build_probe_reason_cards(data.get("reasons") or []),
    ]
    runner = build_probe_runner_alert(data.get("runner_errors") or [])
    if runner is not None:
        blocks.extend([dmc.Space(h="lg"), runner])
    return html.Div(blocks)
