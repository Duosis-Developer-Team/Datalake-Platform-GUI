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
