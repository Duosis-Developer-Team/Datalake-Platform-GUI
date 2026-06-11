"""UI helpers for HMDL Datalake Sync Health pages."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import html

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

    header = html.Tr(
        [
            html.Th("Entity", style={"textAlign": "left", "padding": "8px"}),
            html.Th("IP", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Proxy", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Category", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Platform status", style={"textAlign": "left", "padding": "8px"}),
        ]
    )
    body_rows = []
    for r in rows:
        cat = str(r.get("inclusion_category") or "monitored")
        body_rows.append(
            html.Tr(
                style={"borderBottom": "1px solid #eef1f4"},
                children=[
                    html.Td(str(r.get("entity_name") or "—"), style={"padding": "8px", "fontSize": "13px"}),
                    html.Td(str(r.get("ip") or ""), style={"padding": "8px", "fontSize": "13px"}),
                    html.Td(str(r.get("proxy_id") or ""), style={"padding": "8px", "fontSize": "12px"}),
                    html.Td(category_chip(cat), style={"padding": "8px"}),
                    html.Td(str(r.get("platform_status") or "—"), style={"padding": "8px", "fontSize": "12px"}),
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
    "unknown": "—",
}

COVERAGE_STATUS_COLORS: dict[str, str] = {
    "live": "green",
    "stale": "yellow",
    "missing": "red",
    "extra": "gray",
    "unknown": "gray",
}

_SOURCE_LABELS: dict[str, str] = {"vmware": "VMware", "nutanix": "Nutanix", "ibm": "IBM"}
_SOURCE_COLORS: dict[str, str] = {"vmware": "indigo", "nutanix": "violet", "ibm": "teal"}


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


def build_coverage_summary(summary: dict) -> dmc.SimpleGrid:
    summary = summary or {}
    cluster = summary.get("cluster") or {}
    host = summary.get("ibm_host") or {}
    cards = [
        _coverage_count_card("Cluster (toplam)", cluster.get("all") or {}, color="indigo"),
        _coverage_count_card("VMware cluster", cluster.get("vmware") or {}, color="indigo"),
        _coverage_count_card("Nutanix cluster", cluster.get("nutanix") or {}, color="violet"),
        _coverage_count_card("IBM host", host, color="teal"),
    ]
    return dmc.SimpleGrid(cols={"base": 2, "md": 4}, spacing="md", children=cards)


def _coverage_row(kind: str, name: str, dc: str, status: str, reason: str) -> html.Tr:
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
            html.Td(str(reason or "—"), style={"padding": "8px", "fontSize": "12px", "color": "#555"}),
        ],
    )


def build_coverage_table(clusters: list[dict], hosts: list[dict]) -> html.Div:
    clusters = clusters or []
    hosts = hosts or []
    if not clusters and not hosts:
        return dmc.Alert("Bu filtreyle eşleşen kayıt yok.", color="gray", variant="light")

    header = html.Tr(
        [
            html.Th("Kaynak", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Ad", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Location", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Durum", style={"textAlign": "left", "padding": "8px"}),
            html.Th("Sebep", style={"textAlign": "left", "padding": "8px"}),
        ]
    )
    # Missing first, then stale, then the rest — so problems surface at the top.
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
            )
        )
    host_sorted = sorted(hosts, key=lambda h: (order.get(h.get("status"), 9), h.get("servername") or ""))
    for h in host_sorted:
        body_rows.append(
            _coverage_row("ibm", str(h.get("servername") or ""), str(h.get("dc") or ""), str(h.get("status") or ""), str(h.get("reason") or ""))
        )
    return html.Div(
        style={"overflowX": "auto"},
        children=[html.Table([header, *body_rows], style={"width": "100%", "borderCollapse": "collapse"})],
    )


def build_coverage_section(data: dict) -> html.Div:
    """Summary cards + present/absent table for the Datalake Coverage section."""
    data = data or {}
    return html.Div(
        children=[
            build_coverage_summary(data.get("summary") or {}),
            dmc.Space(h="md"),
            build_coverage_table(data.get("clusters") or [], data.get("ibm_hosts") or []),
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
