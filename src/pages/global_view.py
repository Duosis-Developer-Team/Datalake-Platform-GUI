import math
import pandas as pd
import plotly.express as px
import dash
from dash import html, dcc, callback, Input, Output, State
import dash_mantine_components as dmc
from dash_iconify import DashIconify
from src.services import api_client as api
from src.utils.time_range import default_time_range
from src.utils.export_helpers import records_to_dataframe, dash_send_dataframe

CITY_COORDINATES = {
    "ISTANBUL":    {"lat": 41.01, "lon": 28.96},
    "ANKARA":      {"lat": 39.93, "lon": 32.85},
    "IZMIR":       {"lat": 38.42, "lon": 27.13},
    "AZERBAYCAN":  {"lat": 40.41, "lon": 49.87},
    "ALMANYA":     {"lat": 50.11, "lon": 8.68},
    "INGILTERE":   {"lat": 51.51, "lon": -0.13},
    "OZBEKISTAN":  {"lat": 41.30, "lon": 69.24},
    "HOLLANDA":    {"lat": 52.37, "lon": 4.90},
    "FRANSA":      {"lat": 48.85, "lon": 2.35},
}

_CITY_OFFSETS = [
    (0.00, 0.00), (0.06, 0.00), (-0.06, 0.00),
    (0.00, 0.09), (0.00, -0.09), (0.06, 0.09),
    (-0.06, 0.09), (0.06, -0.09),
]


def _global_export_rows(summaries: list) -> list[dict]:
    """Flatten DC summary list for CSV/Excel/PDF."""
    rows: list[dict] = []
    for dc in summaries or []:
        if not isinstance(dc, dict):
            continue
        dc_id = dc.get("id", "")
        site = dc.get("site_name", "")
        rows.append({"dc_id": dc_id, "field": "site_name", "value": site})
        stats = dc.get("stats") or {}
        if isinstance(stats, dict):
            for k, v in stats.items():
                rows.append({"dc_id": dc_id, "field": str(k), "value": v})
        for k in ("host_count", "vm_count", "cluster_count", "platform_count"):
            if k in dc and k not in (stats or {}):
                rows.append({"dc_id": dc_id, "field": k, "value": dc.get(k)})
    return rows


def _build_map_dataframe(summaries):
    city_index: dict[str, int] = {}
    rows = []
    for dc in summaries:
        site_name = (dc.get("site_name") or "").upper().strip()
        base = CITY_COORDINATES.get(site_name)
        if not base:
            continue
        idx = city_index.get(site_name, 0)
        city_index[site_name] = idx + 1
        dlat, dlon = _CITY_OFFSETS[idx % len(_CITY_OFFSETS)]
        dc_id = dc.get("id", "")
        stats = dc.get("stats", {})
        cpu_pct = stats.get("used_cpu_pct", 0.0)
        ram_pct = stats.get("used_ram_pct", 0.0)
        health = (cpu_pct + ram_pct) / 2.0 if (cpu_pct + ram_pct) > 0 else 0.0
        rows.append({
            "id": dc_id,
            "name": dc.get("name", dc_id),
            "location": dc.get("location", site_name.title()),
            "lat": base["lat"] + dlat,
            "lon": base["lon"] + dlon,
            "host_count": dc.get("host_count", 0),
            "vm_count": dc.get("vm_count", 0),
            "platform_count": dc.get("platform_count", 0),
            "cluster_count": dc.get("cluster_count", 0),
            "cpu_pct": round(cpu_pct, 1),
            "ram_pct": round(ram_pct, 1),
            "health": round(health, 1),
            "total_energy_kw": float(stats.get("total_energy_kw", 0.0) or 0.0),
            "bubble_size": math.log1p(dc.get("vm_count", 0)),
        })
    return pd.DataFrame(rows)


def _create_map_figure(df):
    if df.empty:
        fig = px.scatter_mapbox(
            lat=[41.0082],
            lon=[28.9784],
            zoom=4,
        )
        fig.update_layout(
            mapbox_style="carto-positron",
            margin=dict(l=0, r=0, t=0, b=0),
            height=600,
            paper_bgcolor="rgba(0,0,0,0)",
        )
        return fig

    fig = px.scatter_mapbox(
        df,
        lat="lat",
        lon="lon",
        size="bubble_size",
        size_max=25,
        color="health",
        color_continuous_scale=[
            [0.0, "#05CD99"],
            [0.5, "#FFB547"],
            [1.0, "#E85347"],
        ],
        range_color=[0, 100],
        custom_data=["id", "name", "location", "vm_count", "host_count", "health"],
        zoom=4,
        center={"lat": 45.0, "lon": 20.0},
    )

    fig.update_layout(
        mapbox_style="carto-positron",
        margin=dict(l=0, r=0, t=0, b=0),
        height=600,
        paper_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(
            bgcolor="rgba(255, 255, 255, 0.95)",
            bordercolor="rgba(67, 24, 255, 0.15)",
            font=dict(
                family="DM Sans, sans-serif",
                size=13,
                color="#2B3674",
            ),
            align="left",
        ),
        coloraxis_colorbar=dict(
            title="Utilization %",
            thickness=12,
            len=0.5,
            bgcolor="rgba(255,255,255,0.8)",
            bordercolor="rgba(67,24,255,0.1)",
            borderwidth=1,
            tickfont=dict(size=11, family="DM Sans, sans-serif"),
            title_font=dict(size=12, family="DM Sans, sans-serif"),
        ),
    )

    fig.update_traces(
        marker=dict(
            opacity=0.85,
            sizemin=6,
        ),
        hovertemplate=(
            "<b style='font-size:14px;'>%{customdata[1]}</b><br>"
            "\U0001f4cd %{customdata[2]}<br>"
            "\U0001f4bb VMs: %{customdata[3]:,} | \U0001f5a5\ufe0f Hosts: %{customdata[4]:,}<br>"
            "\u26a1 Health: %%%{customdata[5]:.1f}"
            "<extra></extra>"
        ),
    )

    return fig


def build_global_view(time_range=None):
    tr = time_range or default_time_range()
    summaries = api.get_all_datacenters_summary(tr)
    df = _build_map_dataframe(summaries)
    map_fig = _create_map_figure(df)

    export_rows = _global_export_rows(summaries)

    return html.Div([
        dcc.Store(id="global-export-store", data={"rows": export_rows}),
        dcc.Download(id="global-export-download"),
        dmc.Paper(
            p="xl",
            radius="md",
            style={
                "background": "rgba(255, 255, 255, 0.80)",
                "backdropFilter": "blur(12px)",
                "WebkitBackdropFilter": "blur(12px)",
                "boxShadow": "0 4px 24px rgba(67, 24, 255, 0.07), 0 1px 4px rgba(0, 0, 0, 0.04)",
                "borderBottom": "1px solid rgba(255, 255, 255, 0.6)",
                "marginBottom": "28px",
            },
            children=[
                dmc.Group(
                    justify="space-between",
                    align="center",
                    children=[
                        dmc.Stack(
                            gap=10,
                            children=[
                                dmc.Group(
                                    gap="sm",
                                    align="center",
                                    children=[
                                        DashIconify(
                                            icon="solar:globe-bold-duotone",
                                            width=28,
                                            color="#4318FF",
                                        ),
                                        html.H2(
                                            "Global View",
                                            style={
                                                "margin": 0,
                                                "fontWeight": 900,
                                                "letterSpacing": "-0.02em",
                                                "lineHeight": 1.2,
                                                "fontSize": "1.75rem",
                                                "background": "linear-gradient(90deg, #1a1b41 0%, #4318FF 100%)",
                                                "WebkitBackgroundClip": "text",
                                                "WebkitTextFillColor": "transparent",
                                                "backgroundClip": "text",
                                            },
                                        ),
                                    ],
                                ),
                                dmc.Badge(
                                    children=[
                                        dmc.Group(
                                            gap=6,
                                            align="center",
                                            children=[
                                                DashIconify(
                                                    icon="solar:calendar-mark-bold-duotone",
                                                    width=13,
                                                ),
                                                f"{tr.get('start', '')} \u2013 {tr.get('end', '')}",
                                            ],
                                        )
                                    ],
                                    variant="light",
                                    color="indigo",
                                    radius="xl",
                                    size="md",
                                    style={"textTransform": "none", "fontWeight": 500, "letterSpacing": 0},
                                ),
                            ],
                        ),
                        dmc.Group(
                            gap="sm",
                            align="center",
                            children=[
                                dmc.Group(
                                    gap=6,
                                    align="center",
                                    children=[
                                        dmc.Text("Export", size="xs", c="dimmed"),
                                        dmc.Button(
                                            "CSV",
                                            id="global-export-csv",
                                            size="xs",
                                            variant="light",
                                            color="gray",
                                        ),
                                        dmc.Button(
                                            "Excel",
                                            id="global-export-xlsx",
                                            size="xs",
                                            variant="light",
                                            color="gray",
                                        ),
                                        dmc.Button(
                                            "PDF",
                                            id="global-export-pdf",
                                            size="xs",
                                            variant="light",
                                            color="gray",
                                        ),
                                    ],
                                ),
                                dmc.Badge(
                                    children=[
                                        dmc.Group(
                                            gap=6,
                                            align="center",
                                            children=[
                                                DashIconify(
                                                    icon="solar:check-circle-bold-duotone",
                                                    width=15,
                                                    color="#05CD99",
                                                ),
                                                f"{len(summaries)} Active DCs",
                                            ],
                                        )
                                    ],
                                    variant="light",
                                    color="teal",
                                    radius="xl",
                                    size="lg",
                                    style={
                                        "textTransform": "none",
                                        "fontWeight": 600,
                                        "letterSpacing": 0,
                                        "padding": "8px 14px",
                                    },
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        ),

        dmc.Paper(
            radius="lg",
            style={
                "margin": "0 32px",
                "overflow": "hidden",
                "boxShadow": "0 2px 16px rgba(67, 24, 255, 0.06), 0 1px 4px rgba(0,0,0,0.04)",
                "border": "1px solid rgba(255, 255, 255, 0.7)",
            },
            children=[
                dcc.Graph(
                    id="global-map-graph",
                    figure=map_fig,
                    config={
                        "displayModeBar": False,
                        "scrollZoom": True,
                    },
                    style={"height": "600px", "borderRadius": "12px"},
                ),
            ],
        ),

        html.Div(
            id="global-dc-info-card",
            style={"padding": "0 32px", "marginTop": "24px"},
            children=[],
        ),
    ])


def build_dc_info_card(dc_id, tr):
    data = api.get_dc_details(dc_id, tr)
    meta = data.get("meta", {})
    intel = data.get("intel", {})
    power = data.get("power", {})
    energy = data.get("energy", {})
    platforms = data.get("platforms", {})

    dc_name = meta.get("name", dc_id)
    dc_location = meta.get("location", "\u2014")

    cpu_cap = intel.get("cpu_cap", 0.0)
    cpu_used = intel.get("cpu_used", 0.0)
    cpu_pct = round(cpu_used / cpu_cap * 100, 1) if cpu_cap > 0 else 0.0
    ram_cap = intel.get("ram_cap", 0.0)
    ram_used = intel.get("ram_used", 0.0)
    ram_pct = round(ram_used / ram_cap * 100, 1) if ram_cap > 0 else 0.0
    storage_cap = intel.get("storage_cap", 0.0)
    storage_used = intel.get("storage_used", 0.0)
    storage_pct = round(storage_used / storage_cap * 100, 1) if storage_cap > 0 else 0.0

    nutanix = platforms.get("nutanix", {})
    vmware = platforms.get("vmware", {})
    ibm = platforms.get("ibm", {})

    arch_items = []
    if vmware.get("clusters", 0) > 0 or vmware.get("hosts", 0) > 0:
        arch_items.append(f"VMware ({vmware.get('clusters', 0)} cluster, {vmware.get('hosts', 0)} host)")
    if nutanix.get("hosts", 0) > 0:
        arch_items.append(f"Nutanix ({nutanix.get('hosts', 0)} host)")
    if ibm.get("hosts", 0) > 0:
        arch_items.append(f"IBM Power ({ibm.get('hosts', 0)} host, {ibm.get('lpars', 0)} LPAR)")
    arch_text = " \u00b7 ".join(arch_items) if arch_items else "\u2014"

    def _pct_color(v):
        if v >= 80:
            return "red"
        if v >= 50:
            return "orange"
        return "teal"

    return dmc.Paper(
        p="xl",
        radius="lg",
        style={
            "background": "rgba(255, 255, 255, 0.90)",
            "backdropFilter": "blur(14px)",
            "WebkitBackdropFilter": "blur(14px)",
            "boxShadow": "0 8px 32px rgba(67, 24, 255, 0.10), 0 2px 8px rgba(0,0,0,0.04)",
            "border": "1px solid rgba(67, 24, 255, 0.08)",
            "animation": "fadeInUp 0.3s ease-out",
        },
        children=[
            dmc.Group(
                justify="space-between",
                align="flex-start",
                children=[
                    dmc.Group(
                        gap="md",
                        align="center",
                        children=[
                            dmc.ThemeIcon(
                                size="xl",
                                radius="md",
                                variant="light",
                                color="indigo",
                                children=DashIconify(icon="solar:server-square-bold-duotone", width=24),
                            ),
                            dmc.Stack(
                                gap=0,
                                children=[
                                    dmc.Text(dc_name, fw=800, size="xl", c="#2B3674"),
                                    dmc.Text(dc_location, size="sm", c="#A3AED0", fw=500),
                                ],
                            ),
                        ],
                    ),
                    dcc.Link(
                        dmc.Button(
                            "Open Details",
                            variant="light",
                            color="indigo",
                            radius="md",
                            rightSection=DashIconify(icon="solar:arrow-right-linear", width=16),
                        ),
                        href=f"/datacenter/{dc_id}",
                        style={"textDecoration": "none"},
                    ),
                ],
            ),
            dmc.Divider(my="md", color="rgba(67, 24, 255, 0.08)"),
            dmc.SimpleGrid(
                cols=4,
                spacing="lg",
                children=[
                    dmc.Stack(
                        gap=4,
                        align="center",
                        children=[
                            dmc.RingProgress(
                                size=90,
                                thickness=8,
                                roundCaps=True,
                                sections=[{"value": cpu_pct, "color": _pct_color(cpu_pct)}],
                                label=dmc.Text(f"{cpu_pct:.0f}%", ta="center", fw=700, size="sm"),
                            ),
                            dmc.Text("CPU", size="xs", fw=600, c="#A3AED0"),
                        ],
                    ),
                    dmc.Stack(
                        gap=4,
                        align="center",
                        children=[
                            dmc.RingProgress(
                                size=90,
                                thickness=8,
                                roundCaps=True,
                                sections=[{"value": ram_pct, "color": _pct_color(ram_pct)}],
                                label=dmc.Text(f"{ram_pct:.0f}%", ta="center", fw=700, size="sm"),
                            ),
                            dmc.Text("RAM", size="xs", fw=600, c="#A3AED0"),
                        ],
                    ),
                    dmc.Stack(
                        gap=4,
                        align="center",
                        children=[
                            dmc.RingProgress(
                                size=90,
                                thickness=8,
                                roundCaps=True,
                                sections=[{"value": storage_pct, "color": _pct_color(storage_pct)}],
                                label=dmc.Text(f"{storage_pct:.0f}%", ta="center", fw=700, size="sm"),
                            ),
                            dmc.Text("Storage", size="xs", fw=600, c="#A3AED0"),
                        ],
                    ),
                    dmc.Stack(
                        gap=6,
                        justify="center",
                        children=[
                            dmc.Group(
                                gap="xs",
                                children=[
                                    DashIconify(icon="solar:server-bold-duotone", width=14, color="#A3AED0"),
                                    dmc.Text(f"{intel.get('hosts', 0) + power.get('hosts', 0):,} Hosts", size="sm", c="#2B3674", fw=600),
                                ],
                            ),
                            dmc.Group(
                                gap="xs",
                                children=[
                                    DashIconify(icon="solar:laptop-bold-duotone", width=14, color="#A3AED0"),
                                    dmc.Text(f"{intel.get('vms', 0) + power.get('lpar_count', 0):,} VMs", size="sm", c="#2B3674", fw=600),
                                ],
                            ),
                            dmc.Group(
                                gap="xs",
                                children=[
                                    DashIconify(icon="material-symbols:bolt-outline", width=14, color="#A3AED0"),
                                    dmc.Text(f"{energy.get('total_kw', 0):.1f} kW", size="sm", c="#2B3674", fw=600),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
            dmc.Divider(my="md", color="rgba(67, 24, 255, 0.08)"),
            dmc.Group(
                gap="xs",
                children=[
                    DashIconify(icon="solar:layers-minimalistic-bold-duotone", width=16, color="#4318FF"),
                    dmc.Text("Architecture:", size="sm", fw=600, c="#2B3674"),
                    dmc.Text(arch_text, size="sm", c="#A3AED0"),
                ],
            ),
        ],
    )


@callback(
    Output("global-export-download", "data"),
    Input("global-export-csv", "n_clicks"),
    Input("global-export-xlsx", "n_clicks"),
    Input("global-export-pdf", "n_clicks"),
    State("global-export-store", "data"),
    prevent_initial_call=True,
)
def export_global_view(nc, nx, np, store):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    tid = ctx.triggered[0]["prop_id"].split(".")[0]
    fmt_map = {"global-export-csv": "csv", "global-export-xlsx": "xlsx", "global-export-pdf": "pdf"}
    fmt = fmt_map.get(tid)
    if not fmt:
        return dash.no_update
    store = store or {}
    rows = store.get("rows") or []
    df = records_to_dataframe(rows)
    return dash_send_dataframe(df, "global_view_dc_summary", fmt)
