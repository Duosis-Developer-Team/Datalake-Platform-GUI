"""UI helpers for HMDL Datalake Sync Health pages."""

from __future__ import annotations

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
    "unknown": "—",
}

COVERAGE_STATUS_COLORS: dict[str, str] = {
    "live": "green",
    "stale": "yellow",
    "missing": "red",
    "extra": "gray",
    "partial": "orange",
    "unknown": "gray",
}

_SOURCE_LABELS: dict[str, str] = {
    "vmware": "VMware",
    "nutanix": "Nutanix",
    "ibm": "IBM",
    "netbackup": "NetBackup",
    "veeam": "Veeam",
    "zerto": "Zerto",
}
_SOURCE_COLORS: dict[str, str] = {
    "vmware": "indigo",
    "nutanix": "violet",
    "ibm": "teal",
    "netbackup": "blue",
    "veeam": "cyan",
    "zerto": "grape",
}

INGEST_VERDICT_LABELS: dict[str, str] = {
    "healthy": "Sağlıklı",
    "no_network": "Erişim yok",
    "network_ok_no_data": "Veri yok",
    "stale": "Veri eski",
    "unmatched": "Eşleşmedi",
}

INGEST_VERDICT_COLORS: dict[str, str] = {
    "healthy": "green",
    "no_network": "red",
    "network_ok_no_data": "orange",
    "stale": "yellow",
    "unmatched": "gray",
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
    return dmc.Paper(
        p="md",
        withBorder=True,
        radius="md",
        children=dmc.Stack(
            gap=4,
            children=[
                dmc.Text(title, size="xs", c="dimmed", fw=600),
                dmc.Text(f"{collected} / {total}", fw=800, size="xl", c=color),
                dmc.Group(
                    gap="xs",
                    children=[
                        dmc.Badge(f"{missing} eksik", color="red" if missing else "gray", variant="light", size="xs"),
                        dmc.Badge(f"{live} canlı", color="green" if live else "gray", variant="light", size="xs"),
                    ],
                ),
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
    expected_source: str | None = None,
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
            html.Td(str(expected_source or "—"), style={"padding": "8px", "fontSize": "12px"}),
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
            html.Th("Expected src", style={"textAlign": "left", "padding": "8px"}),
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
                expected_source=str(c.get("expected_source") or "") or None,
                extra=(
                    f"{c.get('reason') or '—'}"
                    + (f" · parent {c.get('parent_name')}" if c.get("parent_name") else "")
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
                expected_source=str(h.get("expected_source") or "") or None,
            )
        )
    return html.Div(
        style={"overflowX": "auto"},
        children=[html.Table([header, *body_rows], style={"width": "100%", "borderCollapse": "collapse"})],
    )


def build_vcenter_table(rows: list[dict]) -> html.Div:
    rows = rows or []
    if not rows:
        return dmc.Alert("Bu filtreyle eşleşen vCenter/Prism kaydı yok.", color="gray", variant="light")
    order = {"missing": 0, "partial": 1, "stale": 2, "extra": 3, "live": 4, "unknown": 5}
    header = html.Tr(
        [
            html.Th("Kaynak", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Parent", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Location", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Beklenen", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Toplanan", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Canlı", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Durum", style={"textAlign": "left", "padding": "8px"}),
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
                    html.Td(str(r.get("parent_name") or "—"), style={"padding": "8px", "fontSize": "13px", "fontWeight": 600}),
                    html.Td(str(r.get("dc") or "—"), style={"padding": "8px", "fontSize": "12px"}),
                    html.Td(str(r.get("expected_clusters") or 0), style={"padding": "8px", "fontSize": "12px"}),
                    html.Td(str(r.get("collected_clusters") or 0), style={"padding": "8px", "fontSize": "12px"}),
                    html.Td(str(r.get("live_clusters") or 0), style={"padding": "8px", "fontSize": "12px"}),
                    html.Td(coverage_status_badge(str(r.get("status") or "")), style={"padding": "8px"}),
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
            html.Th("Kaynak", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Endpoint", style={"textAlign": "left", "padding": "8px"}),
            html.Th("IP", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Location", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Expected src", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Network", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Durum", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Sebep", style={"textAlign": "left", "padding": "8px"}),
        ]
    )
    body = []
    for r in sorted(rows, key=lambda x: (order.get(x.get("status"), 9), x.get("endpoint_name") or "")):
        src = str(r.get("source") or "")
        net = r.get("network_ok")
        net_label = "OK" if net is True else ("Yok" if net is False else "—")
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
                    html.Td(str(r.get("endpoint_name") or "—"), style={"padding": "8px", "fontSize": "13px", "fontWeight": 600}),
                    html.Td(str(r.get("endpoint_ip") or "—"), style={"padding": "8px", "fontSize": "12px"}),
                    html.Td(str(r.get("dc") or "—"), style={"padding": "8px", "fontSize": "12px"}),
                    html.Td(str(r.get("expected_source") or "—"), style={"padding": "8px", "fontSize": "12px"}),
                    html.Td(net_label, style={"padding": "8px", "fontSize": "12px"}),
                    html.Td(coverage_status_badge(str(r.get("status") or "")), style={"padding": "8px"}),
                    html.Td(str(r.get("reason") or "—"), style={"padding": "8px", "fontSize": "12px", "color": "#555"}),
                ],
            )
        )
    return html.Div(
        style={"overflowX": "auto"},
        children=[html.Table([header, *body], style={"width": "100%", "borderCollapse": "collapse"})],
    )


def _vcenter_summary_card(bucket: dict) -> dmc.Paper:
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
                dmc.Text("vCenter / Prism", size="xs", c="dimmed", fw=600),
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


def build_coverage_section(data: dict) -> html.Div:
    """Summary cards + vCenter / cluster / backup tables for Datalake Coverage."""
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


def ingest_verdict_badge(verdict: str | None) -> dmc.Badge:
    v = str(verdict or "unmatched")
    return dmc.Badge(
        INGEST_VERDICT_LABELS.get(v, v),
        color=INGEST_VERDICT_COLORS.get(v, "gray"),
        variant="light",
        size="sm",
    )


def build_ingest_health_section(data: dict) -> html.Div:
    data = data or {}
    summary = data.get("summary") or {}
    items = data.get("items") or []
    kpi = dmc.SimpleGrid(
        cols={"base": 2, "md": 6},
        spacing="md",
        mb="md",
        children=[
            kpi_card("Toplam", int(summary.get("total") or 0), color="gray"),
            kpi_card("Sağlıklı", int(summary.get("healthy") or 0), color="green"),
            kpi_card("Erişim yok", int(summary.get("no_network") or 0), color="red"),
            kpi_card("Veri yok", int(summary.get("network_ok_no_data") or 0), color="orange"),
            kpi_card("Veri eski", int(summary.get("stale") or 0), color="yellow"),
            kpi_card("Eşleşmedi", int(summary.get("unmatched") or 0), color="gray"),
        ],
    )
    if not items:
        return html.Div([kpi, dmc.Alert("Bu filtreyle eşleşen endpoint yok.", color="gray", variant="light")])

    order = {
        "network_ok_no_data": 0,
        "no_network": 1,
        "stale": 2,
        "unmatched": 3,
        "healthy": 4,
    }
    header = html.Tr(
        [
            html.Th("DC", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Tip", style={"textAlign": "left", "padding": "8px"}),
            html.Th("IP", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Entity", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Network", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Last ingest", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Age (h)", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Verdict", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Detail", style={"textAlign": "left", "padding": "8px"}),
        ]
    )
    body = []
    for r in sorted(items, key=lambda x: (order.get(x.get("verdict"), 9), x.get("dc_code") or "", x.get("endpoint_ip") or "")):
        age = r.get("ingest_age_hours")
        age_s = f"{age:.1f}" if isinstance(age, (int, float)) else "—"
        last = str(r.get("last_ingest_at") or "")[:19].replace("T", " ") or "—"
        body.append(
            html.Tr(
                style={"borderBottom": "1px solid #eef1f4"},
                children=[
                    html.Td(str(r.get("dc_code") or "—"), style={"padding": "8px", "fontSize": "12px"}),
                    html.Td(str(r.get("collector_type") or "—"), style={"padding": "8px", "fontSize": "12px"}),
                    html.Td(str(r.get("endpoint_ip") or "—"), style={"padding": "8px", "fontSize": "12px"}),
                    html.Td(str(r.get("entity_name") or "—"), style={"padding": "8px", "fontSize": "12px", "fontWeight": 600}),
                    html.Td("OK" if r.get("network_access") else "Yok", style={"padding": "8px", "fontSize": "12px"}),
                    html.Td(last, style={"padding": "8px", "fontSize": "12px"}),
                    html.Td(age_s, style={"padding": "8px", "fontSize": "12px"}),
                    html.Td(ingest_verdict_badge(str(r.get("verdict") or "")), style={"padding": "8px"}),
                    html.Td(str(r.get("detail_message") or "—")[:80], style={"padding": "8px", "fontSize": "11px", "color": "#555"}),
                ],
            )
        )
    return html.Div(
        children=[
            kpi,
            html.Div(
                style={"overflowX": "auto"},
                children=[html.Table([header, *body], style={"width": "100%", "borderCollapse": "collapse"})],
            ),
        ]
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
