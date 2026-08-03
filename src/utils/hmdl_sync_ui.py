"""UI helpers for HMDL Datalake Sync Health pages."""

from __future__ import annotations

from collections import defaultdict

import dash_mantine_components as dmc
from dash import html

from src.utils.ui_tokens import kpi_card

CATEGORY_LABELS: dict[str, str] = {
    "monitored": "Monitored",
    "not_monitored": "Not monitored",
    "customer_environment": "Customer environment",
    "connectivity_issue": "Connectivity issue",
    "missing_from_loki": "Missing from Loki",
    "pending_distribution": "Pending distribution",
}

CATEGORY_COLORS: dict[str, str] = {
    "monitored": "green",
    "not_monitored": "gray",
    "customer_environment": "blue",
    "connectivity_issue": "orange",
    "missing_from_loki": "red",
    "pending_distribution": "yellow",
}


AUTOMATION_STATUS_LABELS: dict[str, str] = {
    "fresh": "Taze",
    "stale": "Bayat",
    "dead": "Ölü",
    "unknown": "Bilinmiyor",
}

AUTOMATION_STATUS_COLORS: dict[str, str] = {
    "fresh": "green",
    "stale": "orange",
    "dead": "red",
    "unknown": "gray",
}


def relative_age(hours: float | None) -> str:
    """Human-readable Turkish 'X ago' from an age in hours."""
    if hours is None:
        return "—"
    if hours < 1:
        return "az önce"
    if hours < 48:
        return f"{round(hours)} sa önce"
    days = round(hours / 24, 1)
    return f"{days:.1f} gün önce".replace(".", ",")


def automation_status_badge(status: str | None) -> dmc.Badge:
    s = str(status or "unknown")
    return dmc.Badge(
        AUTOMATION_STATUS_LABELS.get(s, s),
        color=AUTOMATION_STATUS_COLORS.get(s, "gray"),
        variant="light",
        size="sm",
    )


def combined_alert_count(counts: dict | None, data_counts: dict | None) -> int:
    """Total staleness alerts = automation schedule alerts + data-freshness alerts,
    so a data-only outage (e.g. datastore dead) surfaces on the badge/banner too."""
    return int((counts or {}).get("alert") or 0) + int((data_counts or {}).get("alert") or 0)


def staleness_alert_banner(counts: dict, href: str) -> dmc.Alert | None:
    """Red banner when any HMDL automation is stale/dead, linking to Automation Health.

    Returns None when there is nothing to alert on (``alert`` count is 0).
    """
    alert = int((counts or {}).get("alert") or 0)
    if alert <= 0:
        return None
    stale = int(counts.get("stale") or 0)
    dead = int(counts.get("dead") or 0)
    return dmc.Alert(
        color="red",
        variant="light",
        title=f"{alert} HMDL otomasyonu schedule'da değil",
        icon=dmc.Text("⚠", size="lg"),
        children=dmc.Group(
            justify="space-between",
            children=[
                dmc.Text(
                    f"{dead} ölü · {stale} bayat otomasyon var — veriler güncellenmiyor olabilir.",
                    size="sm",
                ),
                dmc.Anchor(
                    dmc.Button("Automation Health'e git", variant="filled", color="red", size="xs"),
                    href=href,
                    underline=False,
                ),
            ],
        ),
    )


def sync_status_badge(status: str | None) -> dmc.Badge:
    if not status:
        return proxy_config_badge()
    synced = str(status).lower() == "loki_synced"
    return dmc.Badge(
        "Loki synced" if synced else "Not synced",
        color="green" if synced else "red",
        variant="light",
        size="sm",
    )


def proxy_config_badge() -> dmc.Badge:
    return dmc.Badge(
        "No configured proxy",
        color="gray",
        variant="light",
        size="sm",
    )


def node_status_badge(node: dict) -> dmc.Badge:
    if str(node.get("proxy_config_status") or "") == "no_configured_proxy":
        return proxy_config_badge()
    return sync_status_badge(str(node.get("loki_sync_status") or "not_synced"))


def environment_status_badge(status: str | None, *, issue_count: int = 0) -> dmc.Badge:
    s = str(status or "").lower()
    if s == "connected":
        return dmc.Badge("Connected", color="green", variant="light", size="sm")
    if s == "connectivity_issue":
        label = f"Connectivity issue ({issue_count})" if issue_count else "Connectivity issue"
        return dmc.Badge(label, color="orange", variant="light", size="sm")
    return dmc.Badge("No configured proxy", color="gray", variant="light", size="sm")


def build_environment_health_grid(locations: list[dict], selected_dc: str | None) -> html.Div:
    if not locations:
        return dmc.Alert("No Loki root locations returned from hmdl-api.", color="gray", variant="light")

    cards = []
    for loc in locations:
        dc_code = str(loc.get("dc_code") or "").strip().upper()
        location_name = str(loc.get("location_name") or dc_code or "—")
        title = dc_code or location_name
        env_status = str(loc.get("environment_status") or "no_configured_proxy")
        issue_count = int(loc.get("connectivity_issue_count") or 0)
        proxy_count = int(loc.get("proxy_count") or 0)
        is_selected = bool(dc_code and selected_dc and dc_code == selected_dc.upper())

        card_body = dmc.Stack(
            gap=6,
            children=[
                dmc.Text(title, fw=700, size="sm"),
                dmc.Text(location_name if dc_code and location_name != dc_code else "", size="xs", c="dimmed"),
                environment_status_badge(env_status, issue_count=issue_count),
                dmc.Text(
                    f"{proxy_count} NiFi proxy" if proxy_count != 1 else "1 NiFi proxy",
                    size="xs",
                    c="dimmed",
                )
                if proxy_count
                else dmc.Text("No proxy configured", size="xs", c="dimmed"),
            ],
        )

        if dc_code:
            cards.append(
                html.Div(
                    id={"type": "hmdl-env-select", "dc": dc_code},
                    n_clicks=0,
                    style={"cursor": "pointer"},
                    children=[
                        dmc.Card(
                            withBorder=True,
                            padding="sm",
                            radius="md",
                            style={
                                "borderColor": "#552cf8" if is_selected else "#eef1f4",
                                "background": "#f6f2ff" if is_selected else "#ffffff",
                            },
                            children=card_body,
                        )
                    ],
                )
            )
        else:
            cards.append(
                dmc.Card(
                    withBorder=True,
                    padding="sm",
                    radius="md",
                    style={"borderColor": "#eef1f4", "opacity": 0.85},
                    children=card_body,
                )
            )

    return dmc.SimpleGrid(cols={"base": 1, "sm": 2, "md": 3, "lg": 4}, spacing="md", children=cards)


def category_chip(category: str, *, active: bool = False) -> dmc.Badge:
    label = CATEGORY_LABELS.get(category, category.replace("_", " ").title())
    color = CATEGORY_COLORS.get(category, "gray")
    return dmc.Badge(
        label,
        color=color,
        variant="filled" if active else "light",
        size="sm",
        style={"cursor": "pointer"},
    )


def category_filter_group(categories: list[str], active: str | None = None) -> dmc.Group:
    chips = [category_chip("all" if c == "all" else c, active=(active == c or (active is None and c == "all"))) for c in categories]
    return dmc.Group(gap="xs", children=chips)


def build_targets_table(rows: list[dict]) -> html.Div:
    if not rows:
        return dmc.Alert("No targets match the current filters.", color="gray", variant="light")

    def _fmt_ts(val: object) -> str:
        if not val:
            return "—"
        s = str(val)
        return s[:19].replace("T", " ")

    header = html.Tr(
        [
            html.Th("Entity", style={"textAlign": "left", "padding": "8px"}),
            html.Th("IP", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Proxy", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Category", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Platform status", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Last check", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Distributed", style={"textAlign": "left", "padding": "8px"}),
        ]
    )
    body_rows = []
    for r in rows:
        cat = str(r.get("inclusion_category") or "monitored")
        check_status = str(r.get("last_check_status") or "—")
        check_at = _fmt_ts(r.get("last_check_at"))
        check_label = check_status if check_at == "—" else f"{check_status} · {check_at}"
        body_rows.append(
            html.Tr(
                style={"borderBottom": "1px solid #eef1f4"},
                children=[
                    html.Td(str(r.get("entity_name") or "—"), style={"padding": "8px", "fontSize": "13px"}),
                    html.Td(str(r.get("ip") or ""), style={"padding": "8px", "fontSize": "13px"}),
                    html.Td(str(r.get("proxy_id") or ""), style={"padding": "8px", "fontSize": "12px"}),
                    html.Td(category_chip(cat), style={"padding": "8px"}),
                    html.Td(str(r.get("platform_status") or "—"), style={"padding": "8px", "fontSize": "12px"}),
                    html.Td(check_label, style={"padding": "8px", "fontSize": "12px"}),
                    html.Td(_fmt_ts(r.get("last_distributed_at")), style={"padding": "8px", "fontSize": "12px"}),
                ],
            )
        )
    return html.Div(
        style={"overflowX": "auto"},
        children=[
            html.Table(
                [header, *body_rows],
                style={"width": "100%", "borderCollapse": "collapse"},
            )
        ],
    )


COVERAGE_STATUS_LABELS: dict[str, str] = {
    "live": "Canlı",
    "stale": "Bayat",
    "missing": "Yok",
    "extra": "Envanter dışı",
    "partial": "Kısmi",
    "offline": "Offline",
    "unknown": "—",
}

COVERAGE_STATUS_COLORS: dict[str, str] = {
    "live": "green",
    "stale": "yellow",
    "missing": "red",
    "extra": "gray",
    "partial": "orange",
    "offline": "gray",
    "unknown": "gray",
}

UNMATCHED_REASON_LABELS: dict[str, str] = {
    "unknown_dc": "DC bilinmiyor",
    "no_hint": "Parent ipucu yok",
    "ambiguous": "Birden fazla vCenter, hangisi belirsiz",
    "unresolved_parent": "Parent çözülemedi",
    "no_collector": "Envanterde var, collector yok",
}

_SOURCE_LABELS: dict[str, str] = {
    "vmware": "VMware",
    "nutanix": "Nutanix",
    "ibm": "IBM",
    "netbackup": "NetBackup",
    "veeam": "Veeam",
    "zerto": "Zerto",
    "nutanix_snapshot": "Nutanix Snapshot",
}
_SOURCE_COLORS: dict[str, str] = {
    "vmware": "indigo",
    "nutanix": "violet",
    "ibm": "teal",
    "netbackup": "blue",
    "veeam": "cyan",
    "zerto": "grape",
    "nutanix_snapshot": "violet",
}

def coverage_status_badge(status: str | None) -> dmc.Badge:
    s = str(status or "unknown")
    return dmc.Badge(
        COVERAGE_STATUS_LABELS.get(s, s),
        color=COVERAGE_STATUS_COLORS.get(s, "gray"),
        variant="light",
        size="sm",
    )


def _coverage_count_card(title: str, bucket: dict, *, color: str) -> dmc.Paper:
    total = int((bucket or {}).get("total") or 0)
    collected = int((bucket or {}).get("collected") or 0)
    missing = int((bucket or {}).get("missing") or 0)
    live = int((bucket or {}).get("live") or 0)
    offline = int((bucket or {}).get("offline") or 0)
    badges = [
        dmc.Badge(f"{missing} eksik", color="red" if missing else "gray", variant="light", size="xs"),
        dmc.Badge(f"{live} canlı", color="green" if live else "gray", variant="light", size="xs"),
    ]
    if offline:
        badges.append(
            dmc.Badge(f"{offline} offline", color="gray", variant="light", size="xs")
        )
    return dmc.Paper(
        p="md",
        withBorder=True,
        radius="md",
        children=dmc.Stack(
            gap=4,
            children=[
                dmc.Text(title, size="xs", c="dimmed", fw=600),
                dmc.Text(f"{collected} / {total}", fw=800, size="xl", c=color),
                dmc.Group(gap="xs", children=badges),
            ],
        ),
    )


def _coverage_row(
    kind: str,
    name: str,
    dc: str,
    status: str,
    reason: str,
    *,
    extra: str | None = None,
) -> html.Tr:
    return html.Tr(
        style={"borderBottom": "1px solid #eef1f4"},
        children=[
            html.Td(
                dmc.Badge(
                    _SOURCE_LABELS.get(kind, kind),
                    color=_SOURCE_COLORS.get(kind, "gray"),
                    variant="dot",
                    size="sm",
                ),
                style={"padding": "8px"},
            ),
            html.Td(str(name or "—"), style={"padding": "8px", "fontSize": "13px", "fontWeight": 600}),
            html.Td(str(dc or "—"), style={"padding": "8px", "fontSize": "12px"}),
            html.Td(coverage_status_badge(status), style={"padding": "8px"}),
            html.Td(str(extra or reason or "—"), style={"padding": "8px", "fontSize": "12px", "color": "#555"}),
        ],
    )


def build_coverage_table(clusters: list[dict], hosts: list[dict]) -> html.Div:
    clusters = clusters or []
    hosts = hosts or []
    if not clusters and not hosts:
        return dmc.Alert("Bu filtreyle eşleşen cluster/IBM kaydı yok.", color="gray", variant="light")

    header = html.Tr(
        [
            html.Th("Kaynak", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Ad", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Location", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Durum", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Sebep", style={"textAlign": "left", "padding": "8px"}),
        ]
    )
    order = {"missing": 0, "stale": 1, "extra": 2, "live": 3, "unknown": 4}
    body_rows = []
    cluster_sorted = sorted(clusters, key=lambda c: (order.get(c.get("status"), 9), c.get("cluster_name") or ""))
    for c in cluster_sorted:
        body_rows.append(
            _coverage_row(
                str(c.get("source") or ""),
                str(c.get("cluster_name") or ""),
                str(c.get("dc") or ""),
                str(c.get("status") or ""),
                str(c.get("reason") or ""),
                extra=(
                    f"{c.get('reason') or '—'}"
                    + (
                        f" · parent {c.get('parent_display') or c.get('parent_name')}"
                        if (c.get("parent_display") or c.get("parent_name"))
                        else ""
                    )
                ),
            )
        )
    host_sorted = sorted(hosts, key=lambda h: (order.get(h.get("status"), 9), h.get("servername") or ""))
    for h in host_sorted:
        body_rows.append(
            _coverage_row(
                "ibm",
                str(h.get("servername") or ""),
                str(h.get("dc") or ""),
                str(h.get("status") or ""),
                str(h.get("reason") or ""),
            )
        )
    return html.Div(
        style={"overflowX": "auto"},
        children=[html.Table([header, *body_rows], style={"width": "100%", "borderCollapse": "collapse"})],
    )


def _vcenter_display_name(row: dict) -> str:
    """Collector entity name is the operator-facing name; parent key is the fallback."""
    return (
        str(row.get("endpoint_name") or "").strip()
        or str(row.get("parent_name") or "").strip()
        or "—"
    )


def _parent_key(row: dict) -> str:
    """Join key the API resolved between a cluster and its collector endpoint."""
    return str(row.get("parent_key") or row.get("parent_name") or "").strip()


def _collector_status_label(row: dict) -> str:
    check = str(row.get("collector_check_status") or "").strip()
    net = row.get("collector_network_ok")
    if not check and net is None:
        return "—"
    if net is False:
        return f"{check or 'fail'} · network yok"
    if check:
        return check
    return "OK" if net is True else "—"


def build_vcenter_table(rows: list[dict]) -> html.Div:
    rows = rows or []
    if not rows:
        return dmc.Alert("Bu filtreyle eşleşen vCenter/Prism kaydı yok.", color="gray", variant="light")
    order = {"missing": 0, "partial": 1, "stale": 2, "extra": 3, "live": 4, "unknown": 5}
    header = html.Tr(
        [
            html.Th("Kaynak", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Ad (vCenter / Prism)", style={"textAlign": "left", "padding": "8px"}),
            html.Th("IP", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Location", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Beklenen", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Toplanan", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Canlı", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Durum", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Collector", style={"textAlign": "left", "padding": "8px"}),
        ]
    )
    body = []
    for r in sorted(rows, key=lambda x: (order.get(x.get("status"), 9), x.get("parent_name") or "")):
        src = str(r.get("source") or "")
        body.append(
            html.Tr(
                style={"borderBottom": "1px solid #eef1f4"},
                children=[
                    html.Td(
                        dmc.Badge(
                            _SOURCE_LABELS.get(src, src),
                            color=_SOURCE_COLORS.get(src, "gray"),
                            variant="dot",
                            size="sm",
                        ),
                        style={"padding": "8px"},
                    ),
                    html.Td(_vcenter_display_name(r), style={"padding": "8px", "fontSize": "13px", "fontWeight": 600}),
                    html.Td(str(r.get("endpoint_ip") or "—"), style={"padding": "8px", "fontSize": "12px"}),
                    html.Td(str(r.get("dc") or "—"), style={"padding": "8px", "fontSize": "12px"}),
                    html.Td(str(r.get("expected_clusters") or 0), style={"padding": "8px", "fontSize": "12px"}),
                    html.Td(str(r.get("collected_clusters") or 0), style={"padding": "8px", "fontSize": "12px"}),
                    html.Td(str(r.get("live_clusters") or 0), style={"padding": "8px", "fontSize": "12px"}),
                    html.Td(coverage_status_badge(str(r.get("status") or "")), style={"padding": "8px"}),
                    html.Td(_collector_status_label(r), style={"padding": "8px", "fontSize": "12px", "color": "#555"}),
                ],
            )
        )
    return html.Div(
        style={"overflowX": "auto"},
        children=[html.Table([header, *body], style={"width": "100%", "borderCollapse": "collapse"})],
    )


def build_backup_endpoint_table(rows: list[dict]) -> html.Div:
    rows = rows or []
    if not rows:
        return dmc.Alert("Bu filtreyle eşleşen backup endpoint yok.", color="gray", variant="light")
    order = {"missing": 0, "stale": 1, "extra": 2, "live": 3, "unknown": 4}
    header = html.Tr(
        [
            html.Th("Endpoint", style={"textAlign": "left", "padding": "8px"}),
            html.Th("IP", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Location", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Network", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Collector", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Durum", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Sebep", style={"textAlign": "left", "padding": "8px"}),
        ]
    )
    body = []
    for r in sorted(rows, key=lambda x: (order.get(x.get("status"), 9), x.get("endpoint_name") or "")):
        net = r.get("network_ok")
        net_label = "OK" if net is True else ("Yok" if net is False else "—")
        check = str(r.get("collector_check_status") or "").strip() or "—"
        body.append(
            html.Tr(
                style={"borderBottom": "1px solid #eef1f4"},
                children=[
                    html.Td(
                        str(r.get("endpoint_name") or "—"),
                        style={"padding": "8px", "fontSize": "13px", "fontWeight": 600},
                    ),
                    html.Td(str(r.get("endpoint_ip") or "—"), style={"padding": "8px", "fontSize": "12px"}),
                    html.Td(str(r.get("dc") or "—"), style={"padding": "8px", "fontSize": "12px"}),
                    html.Td(net_label, style={"padding": "8px", "fontSize": "12px"}),
                    html.Td(check, style={"padding": "8px", "fontSize": "12px"}),
                    html.Td(coverage_status_badge(str(r.get("status") or "")), style={"padding": "8px"}),
                    html.Td(str(r.get("reason") or "—"), style={"padding": "8px", "fontSize": "12px", "color": "#555"}),
                ],
            )
        )
    return html.Div(
        style={"overflowX": "auto"},
        children=[html.Table([header, *body], style={"width": "100%", "borderCollapse": "collapse"})],
    )


def _vcenter_summary_card(bucket: dict, *, title: str = "vCenter / Prism") -> dmc.Paper:
    bucket = bucket or {}
    total = int(bucket.get("total") or 0)
    live = int(bucket.get("live") or 0)
    partial = int(bucket.get("partial") or 0)
    missing = int(bucket.get("missing") or 0)
    return dmc.Paper(
        p="md",
        withBorder=True,
        radius="md",
        children=dmc.Stack(
            gap=4,
            children=[
                dmc.Text(title, size="xs", c="dimmed", fw=600),
                dmc.Text(f"{live} / {total} canlı", fw=800, size="xl", c="indigo"),
                dmc.Group(
                    gap="xs",
                    children=[
                        dmc.Badge(f"{partial} kısmi", color="orange" if partial else "gray", variant="light", size="xs"),
                        dmc.Badge(f"{missing} eksik", color="red" if missing else "gray", variant="light", size="xs"),
                    ],
                ),
            ],
        ),
    )


def build_coverage_summary(summary: dict) -> dmc.SimpleGrid:
    summary = summary or {}
    cluster = summary.get("cluster") or {}
    host = summary.get("ibm_host") or {}
    backup = summary.get("backup_endpoint") or {}
    cards = [
        _coverage_count_card("Cluster (toplam)", cluster.get("all") or {}, color="indigo"),
        _coverage_count_card("VMware cluster", cluster.get("vmware") or {}, color="indigo"),
        _coverage_count_card("Nutanix cluster", cluster.get("nutanix") or {}, color="violet"),
        _coverage_count_card("IBM host", host, color="teal"),
        _vcenter_summary_card(summary.get("vcenter") or {}),
        _coverage_count_card("Backup endpoint", backup.get("all") or {}, color="blue"),
    ]
    return dmc.SimpleGrid(cols={"base": 2, "md": 3}, spacing="md", children=cards)


_PROBLEM_STATUSES = frozenset({"missing", "partial", "stale"})


def _worst_status(statuses: list[str]) -> str:
    order = ["missing", "partial", "stale", "extra", "unknown", "live"]
    rank = {s: i for i, s in enumerate(order)}
    best = "live"
    best_i = rank["live"]
    for s in statuses:
        i = rank.get(str(s or "unknown"), 4)
        if i < best_i:
            best_i = i
            best = str(s or "unknown")
    return best


def _rollup_group_status(statuses: list[str]) -> str:
    """DC / parent badge: mixed live+problem → partial (not the worst child alone)."""
    norms = [str(s or "unknown") for s in statuses]
    if not norms:
        return "unknown"
    uniq = set(norms)
    if uniq == {"live"}:
        return "live"
    problems = {"missing", "stale", "partial", "extra", "offline", "unknown"}
    if "live" in uniq and (uniq & problems):
        return "partial"
    return _worst_status(norms)


def _spoke_border_color(status: str) -> str:
    s = str(status or "unknown")
    if s in ("missing", "partial"):
        return "#e03131"
    if s == "stale":
        return "#f59f00"
    if s == "live":
        return "#2f9e44"
    return "#adb5bd"


def _aggregate_dc_spokes_from_vcenters(vcenters: list[dict]) -> list[dict]:
    by_dc: dict[str, list[str]] = defaultdict(list)
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "bad": 0})
    for v in vcenters or []:
        dc = str(v.get("dc") or "").strip().upper() or "Diğer"
        st = str(v.get("status") or "unknown")
        by_dc[dc].append(st)
        counts[dc]["total"] += 1
        if st in _PROBLEM_STATUSES:
            counts[dc]["bad"] += 1
    spokes = []
    for dc in sorted(by_dc):
        status = _worst_status(by_dc[dc])
        c = counts[dc]
        spokes.append(
            {
                "dc": dc,
                "label": dc,
                "status": status,
                "subtitle": f"{c['total']} parent · {c['bad']} sorun",
            }
        )
    return spokes


def _aggregate_dc_spokes_from_hosts(hosts: list[dict]) -> list[dict]:
    by_dc: dict[str, list[str]] = defaultdict(list)
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "bad": 0})
    for h in hosts or []:
        dc = str(h.get("dc") or "").strip().upper() or "Diğer"
        st = str(h.get("status") or "unknown")
        by_dc[dc].append(st)
        counts[dc]["total"] += 1
        if st in _PROBLEM_STATUSES:
            counts[dc]["bad"] += 1
    spokes = []
    for dc in sorted(by_dc):
        status = _worst_status(by_dc[dc])
        c = counts[dc]
        spokes.append(
            {
                "dc": dc,
                "label": dc,
                "status": status,
                "subtitle": f"{c['total']} host · {c['bad']} sorun",
            }
        )
    return spokes


def build_coverage_dc_cards(spokes: list[dict], selected_dc: str | None) -> html.Div:
    if not spokes:
        return dmc.Alert("Bu ürün için DC kaydı yok.", color="gray", variant="light")
    cards = []
    selected = (selected_dc or "").strip().upper()
    for s in spokes:
        dc = str(s.get("dc") or "").upper()
        is_selected = bool(dc and selected and dc == selected)
        card = dmc.Card(
            withBorder=True,
            padding="sm",
            radius="md",
            style={
                "borderColor": "#552cf8" if is_selected else _spoke_border_color(str(s.get("status") or "")),
                "background": "#f6f2ff" if is_selected else "#ffffff",
                "cursor": "pointer",
            },
            children=dmc.Stack(
                gap=4,
                children=[
                    dmc.Text(dc or "—", fw=700, size="sm"),
                    coverage_status_badge(str(s.get("status") or "")),
                    dmc.Text(str(s.get("subtitle") or ""), size="xs", c="dimmed"),
                ],
            ),
        )
        cards.append(
            html.Div(
                id={"type": "hmdl-coverage-dc-pick", "dc": dc},
                n_clicks=0,
                children=card,
            )
        )
    return dmc.SimpleGrid(cols={"base": 2, "sm": 3, "md": 4}, spacing="md", children=cards)


def _cluster_child_table(clusters: list[dict], *, show_unmatched_reason: bool = False) -> html.Div:
    if not clusters:
        return dmc.Text("Bağlı cluster kaydı yok.", size="sm", c="dimmed")
    order = {"missing": 0, "stale": 1, "extra": 2, "live": 3, "offline": 4, "unknown": 5}
    headers = [
        html.Th("Cluster", style={"textAlign": "left", "padding": "6px"}),
        html.Th("Durum", style={"textAlign": "left", "padding": "6px"}),
        html.Th("Sebep", style={"textAlign": "left", "padding": "6px"}),
    ]
    if show_unmatched_reason:
        headers.insert(2, html.Th("Neden", style={"textAlign": "left", "padding": "6px"}))
    header = html.Tr(headers)
    body = []
    for c in sorted(clusters, key=lambda x: (order.get(x.get("status"), 9), x.get("cluster_name") or "")):
        conflict = str(c.get("parent_conflict_with") or "").strip()
        name_cell: object = str(c.get("cluster_name") or "—")
        if conflict:
            name_cell = dmc.Group(
                gap=6,
                wrap="nowrap",
                children=[
                    dmc.Text(str(c.get("cluster_name") or "—"), size="sm", fw=600),
                    dmc.Tooltip(
                        label=(
                            f"NetBox description bu parent'ı seçti; discovery "
                            f"'{conflict}' diyordu. NetBox kazandı."
                        ),
                        children=dmc.Badge("çelişki", color="orange", variant="light", size="xs"),
                    ),
                ],
            )
        cells = [
            html.Td(
                name_cell,
                style={"padding": "6px", "fontSize": "12px", "fontWeight": 600},
            ),
            html.Td(coverage_status_badge(str(c.get("status") or "")), style={"padding": "6px"}),
        ]
        if show_unmatched_reason:
            code = str(c.get("unmatched_reason") or "").strip()
            cells.append(
                html.Td(
                    UNMATCHED_REASON_LABELS.get(code, code or "—"),
                    style={"padding": "6px", "fontSize": "12px", "color": "#555"},
                )
            )
        cells.append(
            html.Td(
                str(c.get("reason") or "—"),
                style={"padding": "6px", "fontSize": "12px", "color": "#555"},
            )
        )
        body.append(html.Tr(style={"borderBottom": "1px solid #f1f3f5"}, children=cells))
    return html.Div(
        style={"overflowX": "auto"},
        children=[html.Table([header, *body], style={"width": "100%", "borderCollapse": "collapse"})],
    )


def _parent_accordion_control(
    *,
    name: str,
    ip: str | None,
    dc: str | None,
    status: str,
    counters: str,
    collector: str,
) -> dmc.Group:
    return dmc.Group(
        justify="space-between",
        wrap="nowrap",
        children=[
            dmc.Group(
                gap="sm",
                wrap="nowrap",
                children=[
                    dmc.Text(name, fw=700, size="sm"),
                    dmc.Code(ip or "IP yok", style={"fontSize": "11px"}),
                    dmc.Badge(dc or "—", variant="light", color="gray", size="xs"),
                    coverage_status_badge(status),
                ],
            ),
            dmc.Group(
                gap="xs",
                wrap="nowrap",
                children=[
                    dmc.Text(counters, size="xs", c="dimmed"),
                    dmc.Text(f"collector: {collector}", size="xs", c="dimmed"),
                ],
            ),
        ],
    )


def build_vcenter_expand_table(vcenters: list[dict], clusters: list[dict]) -> html.Div:
    """Expandable vCenter/Prism rows with child clusters."""
    vcenters = vcenters or []
    clusters = clusters or []
    if not vcenters and not clusters:
        return dmc.Alert("Bu filtreyle eşleşen kayıt yok.", color="gray", variant="light")

    by_parent: dict[str, list[dict]] = defaultdict(list)
    orphan: list[dict] = []
    parent_keys = {_parent_key(v) for v in vcenters if _parent_key(v)}
    for c in clusters:
        key = _parent_key(c)
        if key and key in parent_keys:
            by_parent[key].append(c)
        else:
            orphan.append(c)

    order = {"missing": 0, "partial": 1, "stale": 2, "extra": 3, "live": 4, "unknown": 5}
    items = []
    for i, v in enumerate(sorted(vcenters, key=lambda x: (order.get(x.get("status"), 9), _parent_key(x)))):
        parent = _parent_key(v)
        kids = by_parent.get(parent, [])
        exp = int(v.get("expected_clusters") or 0)
        live = int(v.get("live_clusters") or 0)
        missing_kids = sum(1 for k in kids if k.get("status") == "missing")
        control = _parent_accordion_control(
            name=_vcenter_display_name(v),
            ip=str(v.get("endpoint_ip") or "").strip() or None,
            dc=str(v.get("dc") or "").strip() or None,
            status=str(v.get("status") or ""),
            counters=f"{live}/{exp} canlı · {len(kids)} cluster"
            + (f" · {missing_kids} eksik" if missing_kids else ""),
            collector=_collector_status_label(v),
        )
        panel = dmc.Stack(
            gap="xs",
            children=[
                dmc.Text(
                    f"Envanter anahtarı: {str(v.get('parent_name') or '—')}"
                    + (" · collector target'tan türetildi" if v.get("origin") == "endpoint" else ""),
                    size="xs",
                    c="dimmed",
                ),
                _cluster_child_table(kids),
            ],
        )
        items.append(
            dmc.AccordionItem(
                value=f"vc-{i}-{parent or 'x'}",
                children=[
                    dmc.AccordionControl(control),
                    dmc.AccordionPanel(panel),
                ],
            )
        )

    children: list = []
    if items:
        children.append(dmc.Accordion(variant="separated", radius="md", children=items))
    if orphan:
        children.append(dmc.Space(h="sm"))
        children.append(dmc.Text("Parent eşleşmeyen cluster'lar", fw=700, size="sm"))
        children.append(_cluster_child_table(orphan, show_unmatched_reason=True))
    return html.Div(children=children)


def _ibm_host_child_table(hosts: list[dict]) -> html.Div:
    if not hosts:
        return dmc.Text("Bu HMC'ye bağlı host kaydı yok.", size="sm", c="dimmed")
    order = {"missing": 0, "stale": 1, "extra": 2, "offline": 3, "live": 4, "unknown": 5}
    header = html.Tr(
        [
            html.Th("Host", style={"textAlign": "left", "padding": "6px"}),
            html.Th("Durum", style={"textAlign": "left", "padding": "6px"}),
            html.Th("Sebep", style={"textAlign": "left", "padding": "6px"}),
        ]
    )
    body = []
    for h in sorted(hosts, key=lambda x: (order.get(x.get("status"), 9), x.get("servername") or "")):
        name_cell: object = str(h.get("servername") or "—")
        if h.get("is_offline") or str(h.get("status") or "") == "offline":
            name_cell = dmc.Group(
                gap=6,
                wrap="nowrap",
                children=[
                    dmc.Text(str(h.get("servername") or "—"), size="sm", fw=600),
                    dmc.Badge("offline", color="gray", variant="light", size="xs"),
                ],
            )
        body.append(
            html.Tr(
                style={"borderBottom": "1px solid #f1f3f5"},
                children=[
                    html.Td(name_cell, style={"padding": "6px", "fontSize": "12px", "fontWeight": 600}),
                    html.Td(coverage_status_badge(str(h.get("status") or "")), style={"padding": "6px"}),
                    html.Td(
                        str(h.get("reason") or "—"),
                        style={"padding": "6px", "fontSize": "12px", "color": "#555"},
                    ),
                ],
            )
        )
    return html.Div(
        style={"overflowX": "auto"},
        children=[html.Table([header, *body], style={"width": "100%", "borderCollapse": "collapse"})],
    )


def build_hmc_expand_table(hmcs: list[dict], hosts: list[dict]) -> html.Div:
    """IBM Power: real HMC parents + unmatched hosts listed below (not as fake HMCs)."""
    hmcs = hmcs or []
    hosts = hosts or []
    if not hmcs and not hosts:
        return dmc.Alert("Bu filtreyle eşleşen IBM kaydı yok.", color="gray", variant="light")

    unmatched_label = "HMC eşleşmedi"
    matched_hmcs = [
        m
        for m in hmcs
        if str(m.get("hmc_name") or "").strip() != unmatched_label
    ]
    unmatched_hosts = [
        h
        for h in hosts
        if str(h.get("parent_name") or "").strip() in ("", unmatched_label)
    ]

    by_hmc: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for h in hosts:
        name = str(h.get("parent_name") or "").strip()
        if not name or name == unmatched_label:
            continue
        dc = str(h.get("dc") or "").strip()
        by_hmc[(name, dc)].append(h)

    order = {
        "missing": 0,
        "partial": 1,
        "stale": 2,
        "extra": 3,
        "offline": 4,
        "live": 5,
        "unknown": 6,
    }
    items = []
    for i, m in enumerate(
        sorted(
            matched_hmcs,
            key=lambda x: (order.get(x.get("status"), 9), x.get("hmc_name") or "", x.get("dc") or ""),
        )
    ):
        name = str(m.get("hmc_name") or "—")
        ip = str(m.get("endpoint_ip") or "").strip()
        dc = str(m.get("dc") or "").strip()
        kids = by_hmc.get((name, dc), [])
        expected = int(m.get("expected_hosts") or 0)
        live = int(m.get("live_hosts") or 0)
        check = str(m.get("collector_check_status") or "").strip() or "—"
        control = _parent_accordion_control(
            name=name,
            ip=ip or None,
            dc=dc or None,
            status=str(m.get("status") or ""),
            counters=f"{live}/{expected} canlı host",
            collector=check,
        )
        items.append(
            dmc.AccordionItem(
                value=f"hmc-{i}-{dc}-{name}",
                children=[
                    dmc.AccordionControl(control),
                    dmc.AccordionPanel(_ibm_host_child_table(kids)),
                ],
            )
        )

    children: list = []
    if items:
        children.append(dmc.Accordion(variant="separated", radius="md", children=items))
    if unmatched_hosts:
        if children:
            children.append(dmc.Space(h="sm"))
        children.append(
            dmc.Text(
                "HMC eşleşmeyen host'lar — envanterde var, collector yok",
                fw=700,
                size="sm",
            )
        )
        children.append(_ibm_host_child_table(unmatched_hosts))
    if not children:
        return dmc.Alert("Bu filtreyle eşleşen IBM kaydı yok.", color="gray", variant="light")
    return html.Div(children=children)


def build_product_summary_cards(summary: dict, product: str) -> dmc.SimpleGrid:
    summary = summary or {}
    product = (product or "vmware").lower()
    if product == "ibm":
        hmc_bucket = summary.get("ibm_hmc") or {}
        return dmc.SimpleGrid(
            cols={"base": 1, "sm": 2},
            spacing="md",
            children=[
                _coverage_count_card("IBM host", summary.get("ibm_host") or {}, color="teal"),
                _vcenter_summary_card(hmc_bucket, title="HMC"),
            ],
        )
    cluster = (summary.get("cluster") or {}).get(product) or {}
    return dmc.SimpleGrid(
        cols={"base": 1, "sm": 2},
        spacing="md",
        children=[
            _coverage_count_card(
                f"{_SOURCE_LABELS.get(product, product)} cluster",
                cluster,
                color=_SOURCE_COLORS.get(product, "indigo"),
            ),
            _vcenter_summary_card(summary.get("vcenter") or {}),
        ],
    )


def build_coverage_virtualization_section(
    data: dict,
    *,
    product: str = "vmware",
    selected_dc: str | None = None,
) -> html.Div:
    """Virtualization product panel: interactive topology + expandable parent table."""
    from src.components.hmdl_coverage_flow import build_coverage_flow, build_coverage_graph

    data = data or {}
    product = (product or "vmware").lower()
    if product not in ("vmware", "nutanix", "ibm"):
        product = "vmware"
    selected = (selected_dc or "").strip().upper() or None
    product_label = _SOURCE_LABELS.get(product, product)

    graph = build_coverage_graph(
        data,
        product=product,
        product_label=product_label,
        selected_dc=selected,
    )
    blocks: list = [
        build_product_summary_cards(data.get("summary") or {}, product),
        dmc.Space(h="md"),
        build_coverage_flow(graph),
        dmc.Space(h="md"),
    ]

    if product == "ibm":
        blocks.append(dmc.Text("HMC → host", fw=700, mb="xs"))
        blocks.append(build_hmc_expand_table(data.get("ibm_hmcs") or [], data.get("ibm_hosts") or []))
        ibm_gaps = [
            c
            for c in (data.get("clusters") or [])
            if str(c.get("source") or "").lower() == "ibm"
        ]
        if ibm_gaps:
            blocks.append(dmc.Space(h="sm"))
            blocks.append(
                dmc.Text("IBM / RHV cluster — envanterde var, collector yok", fw=700, size="sm")
            )
            blocks.append(_cluster_child_table(ibm_gaps, show_unmatched_reason=True))
        return html.Div(children=blocks)

    parent_open_label = "vCenter" if product == "vmware" else "cluster'lar"
    blocks.append(
        dmc.Text(
            f"{product_label} parent'lar — satırı açınca {parent_open_label}",
            fw=700,
            mb="xs",
        )
    )
    blocks.append(
        build_vcenter_expand_table(data.get("vcenters") or [], data.get("clusters") or [])
    )
    return html.Div(children=blocks)


def build_coverage_backup_stub() -> html.Div:
    """Deprecated — Backup sekmesi artık build_coverage_backup_section kullanır."""
    return dmc.Alert(
        "Backup coverage artık NetBackup / Veeam / Zerto ürün panellerinde.",
        title="Backup",
        color="blue",
        variant="light",
    )


def build_backup_summary_cards(summary: dict, product: str) -> dmc.SimpleGrid:
    summary = summary or {}
    product = (product or "netbackup").lower()
    bucket = (summary.get("backup_endpoint") or {}).get(product) or {}
    return dmc.SimpleGrid(
        cols={"base": 1, "sm": 1},
        spacing="md",
        children=[
            _coverage_count_card(
                f"{_SOURCE_LABELS.get(product, product)} endpoint",
                bucket,
                color=_SOURCE_COLORS.get(product, "blue"),
            ),
        ],
    )


def build_backup_dc_expand_table(rows: list[dict]) -> html.Div:
    """DC accordion — satırı açınca o lokasyondaki backup endpoint'ler."""
    rows = rows or []
    if not rows:
        return dmc.Alert("Bu filtreyle eşleşen backup endpoint yok.", color="gray", variant="light")

    by_dc: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_dc[str(r.get("dc") or "").strip().upper() or "Diğer"].append(r)

    order = {"missing": 0, "stale": 1, "extra": 2, "live": 3, "unknown": 4}
    items = []
    for i, dc in enumerate(sorted(by_dc)):
        kids = sorted(
            by_dc[dc],
            key=lambda x: (order.get(x.get("status"), 9), x.get("endpoint_name") or ""),
        )
        live = sum(1 for k in kids if k.get("status") == "live")
        missing = sum(1 for k in kids if k.get("status") == "missing")
        statuses = [str(k.get("status") or "") for k in kids]
        control = dmc.Group(
            justify="space-between",
            wrap="nowrap",
            children=[
                dmc.Group(
                    gap="sm",
                    wrap="nowrap",
                    children=[
                        dmc.Text(dc, fw=700, size="sm"),
                        coverage_status_badge(_rollup_group_status(statuses)),
                    ],
                ),
                dmc.Text(
                    f"{live}/{len(kids)} canlı"
                    + (f" · {missing} eksik" if missing else ""),
                    size="xs",
                    c="dimmed",
                ),
            ],
        )
        items.append(
            dmc.AccordionItem(
                value=f"backup-dc-{i}",
                children=[
                    dmc.AccordionControl(control),
                    dmc.AccordionPanel(build_backup_endpoint_table(kids)),
                ],
            )
        )
    return html.Div(children=[dmc.Accordion(variant="separated", radius="md", children=items)])


def build_coverage_backup_section(
    data: dict,
    *,
    product: str = "netbackup",
    selected_dc: str | None = None,
) -> html.Div:
    """Backup product panel: hub → DC → endpoint topology + DC expand table."""
    from src.components.hmdl_coverage_flow import (
        build_backup_coverage_graph,
        build_coverage_flow,
    )

    data = data or {}
    product = (product or "netbackup").lower()
    if product not in ("netbackup", "veeam", "zerto", "nutanix_snapshot"):
        product = "netbackup"
    selected = (selected_dc or "").strip().upper() or None
    product_label = _SOURCE_LABELS.get(product, product)
    rows = [
        r
        for r in (data.get("backup_endpoints") or [])
        if str(r.get("source") or "").lower() == product
    ]

    graph = build_backup_coverage_graph(
        data,
        product=product,
        product_label=product_label,
        selected_dc=selected,
    )
    return html.Div(
        children=[
            build_backup_summary_cards(data.get("summary") or {}, product),
            dmc.Space(h="md"),
            build_coverage_flow(graph, flow_id="hmdl-backup-flow"),
            dmc.Space(h="md"),
            dmc.Text(f"{product_label} endpoint'ler — DC satırını aç", fw=700, mb="xs"),
            build_backup_dc_expand_table(rows),
        ]
    )


def build_coverage_section(data: dict) -> html.Div:
    """Legacy flat coverage section (overview / tests). Prefer virtualization panel on Coverage page."""
    data = data or {}
    return html.Div(
        children=[
            build_coverage_summary(data.get("summary") or {}),
            dmc.Space(h="md"),
            dmc.Text("vCenter / Prism rollup", fw=700, mb="xs"),
            build_vcenter_table(data.get("vcenters") or []),
            dmc.Space(h="md"),
            dmc.Text("Cluster / IBM host", fw=700, mb="xs"),
            build_coverage_table(data.get("clusters") or [], data.get("ibm_hosts") or []),
            dmc.Space(h="md"),
            dmc.Text("Backup endpoints", fw=700, mb="xs"),
            build_backup_endpoint_table(data.get("backup_endpoints") or []),
        ]
    )


def build_runs_strip(runs: list[dict]) -> dmc.Paper:
    """Recent collector sync runs for Sync Health."""
    runs = runs or []
    if not runs:
        return dmc.Paper(
            p="md",
            withBorder=True,
            radius="md",
            mb="lg",
            children=[dmc.Text("Recent sync runs yok.", size="sm", c="dimmed")],
        )
    header = html.Tr(
        [
            html.Th("Run", style={"textAlign": "left", "padding": "6px"}),
            html.Th("AWX job", style={"textAlign": "left", "padding": "6px"}),
            html.Th("Proxy", style={"textAlign": "left", "padding": "6px"}),
            html.Th("Status", style={"textAlign": "left", "padding": "6px"}),
            html.Th("Δ", style={"textAlign": "left", "padding": "6px"}),
            html.Th("Finished", style={"textAlign": "left", "padding": "6px"}),
        ]
    )
    body = []
    for r in runs[:15]:
        added = int(r.get("added_count") or 0)
        removed = int(r.get("removed_count") or 0)
        finished = str(r.get("finished_at") or "")[:19].replace("T", " ") or "—"
        status = str(r.get("status") or "—")
        color = "green" if status.lower() in ("ok", "success", "completed") else "orange"
        body.append(
            html.Tr(
                children=[
                    html.Td(str(r.get("run_id") or "—")[:28], style={"fontSize": "12px", "padding": "6px"}),
                    html.Td(str(r.get("awx_job_id") or "—"), style={"fontSize": "12px", "padding": "6px"}),
                    html.Td(str(r.get("proxy_id") or "—"), style={"fontSize": "12px", "padding": "6px"}),
                    html.Td(dmc.Badge(status, color=color, variant="light", size="xs"), style={"padding": "6px"}),
                    html.Td(f"+{added}/-{removed}", style={"fontSize": "12px", "padding": "6px"}),
                    html.Td(finished, style={"fontSize": "12px", "padding": "6px"}),
                ]
            )
        )
    return dmc.Paper(
        p="md",
        withBorder=True,
        radius="md",
        mb="lg",
        children=[
            dmc.Text("Recent collector sync runs", fw=700, mb="sm"),
            html.Div(
                style={"overflowX": "auto"},
                children=[
                    html.Table(
                        [header, *body],
                        style={"width": "100%", "fontSize": "13px", "borderCollapse": "collapse"},
                    )
                ],
            ),
        ],
    )


def build_diff_panel(diffs: list[dict]) -> dmc.Paper:
    if not diffs:
        return dmc.Paper(
            p="md",
            withBorder=True,
            radius="md",
            children=[dmc.Text("No recent diffs for this datacenter.", size="sm", c="dimmed")],
        )
    rows = []
    for d in diffs[:15]:
        action = str(d.get("action") or "")
        color = "green" if action == "added" else "red" if action == "removed" else "gray"
        rows.append(
            html.Tr(
                children=[
                    html.Td(str(d.get("created_at") or "")[:19], style={"fontSize": "12px", "padding": "6px"}),
                    html.Td(dmc.Badge(action, color=color, variant="light", size="xs"), style={"padding": "6px"}),
                    html.Td(str(d.get("ip") or ""), style={"fontSize": "12px", "padding": "6px"}),
                    html.Td(str(d.get("proxy_id") or ""), style={"fontSize": "12px", "padding": "6px"}),
                    html.Td(str(d.get("reason") or "")[:60], style={"fontSize": "12px", "padding": "6px"}),
                ]
            )
        )
    return dmc.Paper(
        p="md",
        withBorder=True,
        radius="md",
        children=[
            dmc.Text("Recent diffs", fw=700, mb="sm"),
            html.Div(
                style={"overflowX": "auto"},
                children=[
                    html.Table(
                        [
                            html.Tr(
                                [
                                    html.Th("Time"),
                                    html.Th("Action"),
                                    html.Th("IP"),
                                    html.Th("Proxy"),
                                    html.Th("Reason"),
                                ]
                            ),
                            *rows,
                        ],
                        style={"width": "100%", "fontSize": "13px", "borderCollapse": "collapse"},
                    )
                ],
            ),
        ],
    )
