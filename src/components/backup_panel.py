from typing import Iterable

from dash import html, dcc
import dash_mantine_components as dmc
from dash_iconify import DashIconify
import plotly.graph_objects as go

from src.utils.format_units import smart_bytes, pct_float


def _kpi_card(title: str, value: str, icon: str, color: str = "indigo"):
    return dmc.Paper(
        className="nexus-card",
        shadow="sm",
        radius="md",
        withBorder=False,
        style={"padding": "16px"},
        children=[
            dmc.Group(
                gap="sm",
                align="center",
                children=[
                    dmc.ThemeIcon(
                        size="lg",
                        radius="md",
                        variant="light",
                        color=color,
                        children=DashIconify(icon=icon, width=22),
                    ),
                    html.Div(
                        children=[
                            html.Div(
                                title,
                                style={
                                    "fontSize": "0.8rem",
                                    "color": "#A3AED0",
                                    "marginBottom": "2px",
                                },
                            ),
                            html.Div(
                                value,
                                style={
                                    "fontSize": "1.2rem",
                                    "color": "#2B3674",
                                    "fontWeight": 700,
                                },
                            ),
                        ]
                    ),
                ],
            ),
        ],
    )


def _usage_pie(used: float, total: float, title: str) -> go.Figure:
    used_val = max(float(used or 0), 0.0)
    total_val = max(float(total or 0), 0.0)
    free_val = max(total_val - used_val, 0.0) if total_val > 0 else 0.0
    if total_val <= 0:
        values = [0, 1]
    else:
        values = [used_val, free_val]

    fig = go.Figure(
        data=[
            go.Pie(
                labels=["Used", "Free"],
                values=values,
                hole=0.7,
                marker=dict(
                    colors=["#4318FF", "#E9EDF7"],
                    line=dict(color="#FFFFFF", width=1),
                ),
                textinfo="none",
                hovertemplate="%{label}: %{percent:.1%}<extra></extra>",
                sort=False,
                direction="clockwise",
            )
        ]
    )
    fig.update_layout(
        margin=dict(l=10, r=10, t=30, b=10),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.1, xanchor="center", x=0.5),
        title=dict(text=title, x=0.5, xanchor="center", font=dict(size=12)),
    )
    return fig


# ---------------------------------------------------------------------------
# NetBackup
# ---------------------------------------------------------------------------


def _aggregate_netbackup(data: dict, selected_pools: Iterable[str] | None) -> dict:
    rows = data.get("rows") or []
    all_pools = [r.get("name") for r in rows if r.get("name")]
    available_pools = list({p for p in all_pools if p})

    chosen = set(selected_pools or available_pools)
    active_rows: list[dict] = []
    total_usable = 0
    total_avail = 0
    total_used = 0

    for r in rows:
        name = r.get("name")
        if not name or (chosen and name not in chosen):
            continue
        active_rows.append(r)
        total_usable += int(r.get("usablesizebytes", 0) or 0)
        total_avail += int(r.get("availablespacebytes", 0) or 0)
        total_used += int(r.get("usedcapacitybytes", 0) or 0)

    utilisation_pct = pct_float(total_used, total_usable) if total_usable else 0.0
    return {
        "pools": available_pools,
        "active_pools": sorted({r.get("name") for r in active_rows if r.get("name")}),
        "rows": active_rows,
        "total_usable": total_usable,
        "total_avail": total_avail,
        "total_used": total_used,
        "utilisation_pct": utilisation_pct,
    }


def build_netbackup_panel(data: dict, selected_pools: Iterable[str] | None):
    agg = _aggregate_netbackup(data, selected_pools)
    selector_value = list(selected_pools) if selected_pools else agg["pools"]

    fig = _usage_pie(
        used=agg["total_used"],
        total=max(agg["total_usable"], agg["total_used"] + agg["total_avail"]),
        title="NetBackup Capacity Utilisation",
    )

    header = html.Div(
        style={
            "display": "flex",
            "justifyContent": "space-between",
            "alignItems": "center",
            "marginBottom": "16px",
        },
        children=[
            dmc.Group(
                gap="md",
                children=[
                    DashIconify(
                        icon="solar:database-bold-duotone",
                        width=28,
                        style={"color": "#4318FF"},
                    ),
                    html.Div(
                        children=[
                            html.H3(
                                "NetBackup Disk Pools",
                                style={
                                    "margin": 0,
                                    "fontSize": "1rem",
                                    "color": "#2B3674",
                                },
                            ),
                            html.P(
                                "Latest usable, free and used capacity per selected pools.",
                                style={
                                    "margin": "2px 0 0 0",
                                    "fontSize": "0.8rem",
                                    "color": "#A3AED0",
                                },
                            ),
                        ]
                    ),
                ],
            ),
            dmc.MultiSelect(
                id="backup-nb-pool-selector",
                data=[{"label": p, "value": p} for p in agg["pools"]],
                value=selector_value,
                clearable=True,
                searchable=True,
                nothingFoundMessage="No pools",
                placeholder="Select pools",
                size="sm",
                style={"minWidth": "260px"},
            ),
        ],
    )

    kpis = dmc.SimpleGrid(
        cols=4,
        spacing="lg",
        children=[
            _kpi_card(
                "Total usable",
                smart_bytes(agg["total_usable"]),
                "solar:database-bold-duotone",
            ),
            _kpi_card(
                "Total used",
                smart_bytes(agg["total_used"]),
                "solar:pie-chart-2-bold-duotone",
            ),
            _kpi_card(
                "Free space",
                smart_bytes(max(agg["total_avail"], 0)),
                "solar:folder-with-files-bold-duotone",
            ),
            _kpi_card(
                "Utilisation",
                f"{agg['utilisation_pct']:.1f}%",
                "solar:chart-square-bold-duotone",
            ),
        ],
    )

    pie_card = html.Div(
        className="nexus-card",
        style={
            "padding": "16px",
            "height": "260px",
            "display": "flex",
            "flexDirection": "column",
            "alignItems": "center",
            "justifyContent": "center",
        },
        children=dcc.Graph(
            figure=fig,
            config={"displayModeBar": False},
            style={"height": "100%", "width": "100%"},
        ),
    )

    # Table
    header_cells = [
        "Name",
        "Type",
        "Storage Category",
        "Disk Volume",
        "Volume State",
        "Usable",
        "Available",
        "Used",
    ]
    table_head = html.Thead(
        html.Tr(
            [
                html.Th(h, style={"fontSize": "0.75rem", "color": "#A3AED0"})
                for h in header_cells
            ]
        )
    )

    body_rows = []
    for r in agg["rows"]:
        body_rows.append(
            html.Tr(
                children=[
                    html.Td(r.get("name")),
                    html.Td(r.get("stype")),
                    html.Td(r.get("storagecategory")),
                    html.Td(r.get("diskvolumes_name")),
                    html.Td(r.get("diskvolumes_state")),
                    html.Td(smart_bytes(r.get("usablesizebytes", 0) or 0)),
                    html.Td(smart_bytes(r.get("availablespacebytes", 0) or 0)),
                    html.Td(smart_bytes(r.get("usedcapacitybytes", 0) or 0)),
                ]
            )
        )

    table = dmc.Table(
        striped=True,
        highlightOnHover=True,
        withTableBorder=False,
        withColumnBorders=False,
        className="nexus-table",
        children=[table_head, html.Tbody(body_rows)],
    )

    return html.Div(
        children=[
            header,
            dmc.SimpleGrid(cols=2, spacing="lg", children=[kpis, pie_card]),
            html.Div(style={"height": "20px"}),
            html.Div(
                className="nexus-card",
                style={"padding": "16px", "marginTop": "8px"},
                children=table,
            ),
        ]
    )


# ---------------------------------------------------------------------------
# Zerto
# ---------------------------------------------------------------------------


def _aggregate_zerto(data: dict, selected_sites: Iterable[str] | None) -> dict:
    rows = data.get("rows") or []
    all_sites = [r.get("name") for r in rows if r.get("name")]
    available_sites = list({s for s in all_sites if s})

    chosen = set(selected_sites or available_sites)
    active_rows: list[dict] = []
    total_prov = 0
    total_used = 0
    total_in = 0.0
    total_out = 0.0

    for r in rows:
        name = r.get("name")
        if not name or (chosen and name not in chosen):
            continue
        active_rows.append(r)
        total_prov += int(r.get("provisioned_storage_mb", 0) or 0)
        total_used += int(r.get("used_storage_mb", 0) or 0)
        total_in += float(r.get("incoming_throughput_mb", 0.0) or 0.0)
        total_out += float(r.get("outgoing_bandwidth_mb", 0.0) or 0.0)

    utilisation_pct = pct_float(total_used, total_prov) if total_prov else 0.0
    return {
        "sites": available_sites,
        "active_sites": sorted({r.get("name") for r in active_rows if r.get("name")}),
        "rows": active_rows,
        "total_provisioned_mb": total_prov,
        "total_used_mb": total_used,
        "incoming_mb": total_in,
        "outgoing_mb": total_out,
        "utilisation_pct": utilisation_pct,
    }


def build_zerto_panel(data: dict, selected_sites: Iterable[str] | None):
    agg = _aggregate_zerto(data, selected_sites)
    selector_value = list(selected_sites) if selected_sites else agg["sites"]

    fig = _usage_pie(
        used=agg["total_used_mb"],
        total=agg["total_provisioned_mb"],
        title="Zerto Storage Utilisation (MB)",
    )

    header = html.Div(
        style={
            "display": "flex",
            "justifyContent": "space-between",
            "alignItems": "center",
            "marginBottom": "16px",
        },
        children=[
            dmc.Group(
                gap="md",
                children=[
                    DashIconify(
                        icon="solar:shield-check-bold-duotone",
                        width=28,
                        style={"color": "#12B886"},
                    ),
                    html.Div(
                        children=[
                            html.H3(
                                "Zerto Sites",
                                style={
                                    "margin": 0,
                                    "fontSize": "1rem",
                                    "color": "#2B3674",
                                },
                            ),
                            html.P(
                                "Provisioned and used storage with connectivity status.",
                                style={
                                    "margin": "2px 0 0 0",
                                    "fontSize": "0.8rem",
                                    "color": "#A3AED0",
                                },
                            ),
                        ]
                    ),
                ],
            ),
            dmc.MultiSelect(
                id="backup-zerto-site-selector",
                data=[{"label": s, "value": s} for s in agg["sites"]],
                value=selector_value,
                clearable=True,
                searchable=True,
                nothingFoundMessage="No sites",
                placeholder="Select sites",
                size="sm",
                style={"minWidth": "260px"},
            ),
        ],
    )

    kpis = dmc.SimpleGrid(
        cols=4,
        spacing="lg",
        children=[
            _kpi_card(
                "Total provisioned",
                f"{agg['total_provisioned_mb']:,} MB",
                "solar:hdd-bold-duotone",
                color="teal",
            ),
            _kpi_card(
                "Total used",
                f"{agg['total_used_mb']:,} MB",
                "solar:pie-chart-2-bold-duotone",
                color="teal",
            ),
            _kpi_card(
                "Incoming throughput",
                f"{agg['incoming_mb']:.1f} MB",
                "solar:incoming-call-bold-duotone",
                color="teal",
            ),
            _kpi_card(
                "Outgoing bandwidth",
                f"{agg['outgoing_mb']:.1f} MB",
                "solar:outgoing-call-bold-duotone",
                color="teal",
            ),
        ],
    )

    pie_card = html.Div(
        className="nexus-card",
        style={
            "padding": "16px",
            "height": "260px",
            "display": "flex",
            "flexDirection": "column",
            "alignItems": "center",
            "justifyContent": "center",
        },
        children=dcc.Graph(
            figure=fig,
            config={"displayModeBar": False},
            style={"height": "100%", "width": "100%"},
        ),
    )

    # Table with pastel row coloring based on is_connected.
    header_cells = [
        "Name",
        "Site Type",
        "Connected",
        "Provisioned (MB)",
        "Used (MB)",
        "Incoming (MB)",
        "Outgoing (MB)",
    ]
    table_head = html.Thead(
        html.Tr(
            [
                html.Th(h, style={"fontSize": "0.75rem", "color": "#A3AED0"})
                for h in header_cells
            ]
        )
    )

    body_rows = []
    for r in agg["rows"]:
        is_conn = r.get("is_connected")
        if is_conn is True:
            bg = "#E6F9E6"  # pastel green
        elif is_conn is False:
            bg = "#FFE6E6"  # pastel red
        else:
            bg = "transparent"

        body_rows.append(
            html.Tr(
                style={"backgroundColor": bg},
                children=[
                    html.Td(r.get("name")),
                    html.Td(r.get("site_type")),
                    html.Td("True" if is_conn else "False"),
                    html.Td(f"{int(r.get('provisioned_storage_mb', 0) or 0):,}"),
                    html.Td(f"{int(r.get('used_storage_mb', 0) or 0):,}"),
                    html.Td(f"{float(r.get('incoming_throughput_mb', 0.0) or 0.0):.1f}"),
                    html.Td(f"{float(r.get('outgoing_bandwidth_mb', 0.0) or 0.0):.1f}"),
                ],
            )
        )

    table = dmc.Table(
        striped=True,
        highlightOnHover=True,
        withTableBorder=False,
        withColumnBorders=False,
        className="nexus-table",
        children=[table_head, html.Tbody(body_rows)],
    )

    return html.Div(
        children=[
            header,
            dmc.SimpleGrid(cols=2, spacing="lg", children=[kpis, pie_card]),
            html.Div(style={"height": "20px"}),
            html.Div(
                className="nexus-card",
                style={"padding": "16px", "marginTop": "8px"},
                children=table,
            ),
        ]
    )


# ---------------------------------------------------------------------------
# Veeam
# ---------------------------------------------------------------------------


def _aggregate_veeam(data: dict, selected_repos: Iterable[str] | None) -> dict:
    rows = data.get("rows") or []
    all_repos = [r.get("name") for r in rows if r.get("name")]
    available_repos = list({n for n in all_repos if n})

    chosen = set(selected_repos or available_repos)
    active_rows: list[dict] = []
    total_capacity = 0.0
    total_free = 0.0
    total_used = 0.0

    for r in rows:
        name = r.get("name")
        if not name or (chosen and name not in chosen):
            continue
        active_rows.append(r)
        total_capacity += float(r.get("capacity_gb", 0.0) or 0.0)
        total_free += float(r.get("free_gb", 0.0) or 0.0)
        total_used += float(r.get("used_space_gb", 0.0) or 0.0)

    utilisation_pct = pct_float(total_used, total_capacity) if total_capacity else 0.0
    return {
        "repos": available_repos,
        "active_repos": sorted({r.get("name") for r in active_rows if r.get("name")}),
        "rows": active_rows,
        "total_capacity_gb": total_capacity,
        "total_free_gb": total_free,
        "total_used_gb": total_used,
        "utilisation_pct": utilisation_pct,
    }


def build_veeam_panel(data: dict, selected_repos: Iterable[str] | None):
    agg = _aggregate_veeam(data, selected_repos)
    selector_value = list(selected_repos) if selected_repos else agg["repos"]

    fig = _usage_pie(
        used=agg["total_used_gb"],
        total=agg["total_capacity_gb"],
        title="Veeam Repository Utilisation (GB)",
    )

    header = html.Div(
        style={
            "display": "flex",
            "justifyContent": "space-between",
            "alignItems": "center",
            "marginBottom": "16px",
        },
        children=[
            dmc.Group(
                gap="md",
                children=[
                    DashIconify(
                        icon="solar:cloud-storage-bold-duotone",
                        width=28,
                        style={"color": "#15AABF"},
                    ),
                    html.Div(
                        children=[
                            html.H3(
                                "Veeam Repositories",
                                style={
                                    "margin": 0,
                                    "fontSize": "1rem",
                                    "color": "#2B3674",
                                },
                            ),
                            html.P(
                                "Capacity, free and used space per repository.",
                                style={
                                    "margin": "2px 0 0 0",
                                    "fontSize": "0.8rem",
                                    "color": "#A3AED0",
                                },
                            ),
                        ]
                    ),
                ],
            ),
            dmc.MultiSelect(
                id="backup-veeam-repo-selector",
                data=[{"label": r, "value": r} for r in agg["repos"]],
                value=selector_value,
                clearable=True,
                searchable=True,
                nothingFoundMessage="No repositories",
                placeholder="Select repositories",
                size="sm",
                style={"minWidth": "260px"},
            ),
        ],
    )

    kpis = dmc.SimpleGrid(
        cols=4,
        spacing="lg",
        children=[
            _kpi_card(
                "Total capacity",
                f"{agg['total_capacity_gb']:.1f} GB",
                "solar:database-bold-duotone",
                color="cyan",
            ),
            _kpi_card(
                "Total used",
                f"{agg['total_used_gb']:.1f} GB",
                "solar:pie-chart-2-bold-duotone",
                color="cyan",
            ),
            _kpi_card(
                "Free space",
                f"{agg['total_free_gb']:.1f} GB",
                "solar:folder-with-files-bold-duotone",
                color="cyan",
            ),
            _kpi_card(
                "Utilisation",
                f"{agg['utilisation_pct']:.1f}%",
                "solar:chart-square-bold-duotone",
                color="cyan",
            ),
        ],
    )

    pie_card = html.Div(
        className="nexus-card",
        style={
            "padding": "16px",
            "height": "260px",
            "display": "flex",
            "flexDirection": "column",
            "alignItems": "center",
            "justifyContent": "center",
        },
        children=dcc.Graph(
            figure=fig,
            config={"displayModeBar": False},
            style={"height": "100%", "width": "100%"},
        ),
    )

    header_cells = [
        "Name",
        "Host",
        "Type",
        "Capacity (GB)",
        "Free (GB)",
        "Used (GB)",
        "Online",
    ]
    table_head = html.Thead(
        html.Tr(
            [
                html.Th(h, style={"fontSize": "0.75rem", "color": "#A3AED0"})
                for h in header_cells
            ]
        )
    )

    body_rows = []
    for r in agg["rows"]:
        body_rows.append(
            html.Tr(
                children=[
                    html.Td(r.get("name")),
                    html.Td(r.get("host_name")),
                    html.Td(r.get("type")),
                    html.Td(f"{float(r.get('capacity_gb', 0.0) or 0.0):.1f}"),
                    html.Td(f"{float(r.get('free_gb', 0.0) or 0.0):.1f}"),
                    html.Td(f"{float(r.get('used_space_gb', 0.0) or 0.0):.1f}"),
                    html.Td("True" if r.get("is_online") else "False"),
                ]
            )
        )

    table = dmc.Table(
        striped=True,
        highlightOnHover=True,
        withTableBorder=False,
        withColumnBorders=False,
        className="nexus-table",
        children=[table_head, html.Tbody(body_rows)],
    )

    return html.Div(
        children=[
            header,
            dmc.SimpleGrid(cols=2, spacing="lg", children=[kpis, pie_card]),
            html.Div(style={"height": "20px"}),
            html.Div(
                className="nexus-card",
                style={"padding": "16px", "marginTop": "8px"},
                children=table,
            ),
        ]
    )

