import math
import random
import pandas as pd
import plotly.graph_objects as go
import dash
from dash import html, dcc, callback, Input, Output, State
import dash_mantine_components as dmc
from dash_iconify import DashIconify
from src.services import api_client as api
from src.utils.time_range import default_time_range
from src.utils.export_helpers import (
    records_to_dataframe,
    dataframes_to_excel_with_meta,
    csv_bytes_with_report_header,
    dash_send_excel_workbook,
    dash_send_csv_bytes,
    build_report_info_df,
)

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

REGION_HIERARCHY = {
    "Europe": {
        "icon": "solar:earth-bold-duotone",
        "children": {
            "ALMANYA":   {"label": "Germany",         "flag": "twemoji:flag-germany"},
            "INGILTERE": {"label": "United Kingdom",  "flag": "twemoji:flag-united-kingdom"},
            "HOLLANDA":  {"label": "Netherlands",     "flag": "twemoji:flag-netherlands"},
            "FRANSA":    {"label": "France",          "flag": "twemoji:flag-france"},
        },
    },
    "Turkey Region": {
        "icon": "twemoji:flag-turkey",
        "children": {
            "ISTANBUL": {"label": "Istanbul"},
            "ANKARA":   {"label": "Ankara"},
            "IZMIR":    {"label": "Izmir"},
        },
    },
    "Asia & CIS": {
        "icon": "solar:earth-bold-duotone",
        "children": {
            "AZERBAYCAN": {"label": "Azerbaijan", "flag": "twemoji:flag-azerbaijan"},
            "OZBEKISTAN": {"label": "Uzbekistan",  "flag": "twemoji:flag-uzbekistan"},
        },
    },
}

REGION_ZOOM_TARGETS = {
    "ISTANBUL":   {"lon": 28.96,  "lat": 41.01, "scale": 40.0},
    "ANKARA":     {"lon": 32.85,  "lat": 39.93, "scale": 15.0},
    "IZMIR":      {"lon": 27.13,  "lat": 38.42, "scale": 15.0},
    "AZERBAYCAN": {"lon": 49.87,  "lat": 40.41, "scale": 6.0},
    "ALMANYA":    {"lon": 8.68,   "lat": 50.11, "scale": 6.0},
    "INGILTERE":  {"lon": -0.13,  "lat": 51.51, "scale": 6.0},
    "OZBEKISTAN": {"lon": 69.24,  "lat": 41.30, "scale": 6.0},
    "HOLLANDA":   {"lon": 4.90,   "lat": 52.37, "scale": 6.0},
    "FRANSA":     {"lon": 2.35,   "lat": 48.85, "scale": 6.0},
}

_CITY_OFFSETS = [
    (0.00, 0.00), (0.12, 0.00), (-0.12, 0.00),
    (0.00, 0.18), (0.00, -0.18), (0.12, 0.18),
    (-0.12, 0.18), (0.12, -0.18),
]


def _global_export_table(summaries: list) -> list[dict]:
    """One row per DC with readable columns for CSV/Excel."""
    rows: list[dict] = []
    for dc in summaries or []:
        if not isinstance(dc, dict):
            continue
        stats = dc.get("stats") or {}
        site = dc.get("site_name", "")
        rows.append(
            {
                "DC_ID": dc.get("id", ""),
                "Site_Name": site,
                "Location": dc.get("location", ""),
                "Region": site or dc.get("location", ""),
                "Hosts": dc.get("host_count", 0),
                "VMs": dc.get("vm_count", 0),
                "Clusters": dc.get("cluster_count", 0),
                "Platforms": dc.get("platform_count", 0),
                "CPU_Used_pct": stats.get("used_cpu_pct", ""),
                "RAM_Used_pct": stats.get("used_ram_pct", ""),
                "Total_Energy_kW": stats.get("total_energy_kw", ""),
                "IBM_Energy_kW": stats.get("ibm_kw", ""),
            }
        )
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
            "site_name": dc.get("site_name", ""),
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


def _health_colors(health_value):
    if health_value >= 70:
        return {
            "pin": "#E85347",
            "pin_rgba": "rgba(232, 83, 71, 0.95)",
            "halo": "rgba(232, 83, 71, 0.18)",
            "shadow": "rgba(120, 30, 20, 0.35)",
            "gradient": "rgba(255, 180, 170, 0.90)",
        }
    if health_value >= 40:
        return {
            "pin": "#FFB547",
            "pin_rgba": "rgba(255, 181, 71, 0.95)",
            "halo": "rgba(255, 181, 71, 0.18)",
            "shadow": "rgba(140, 100, 20, 0.35)",
            "gradient": "rgba(255, 230, 180, 0.90)",
        }
    return {
        "pin": "#05CD99",
        "pin_rgba": "rgba(5, 205, 153, 0.95)",
        "halo": "rgba(5, 205, 153, 0.18)",
        "shadow": "rgba(2, 90, 60, 0.35)",
        "gradient": "rgba(150, 245, 220, 0.90)",
    }


def _create_map_figure(df):
    fig = go.Figure()

    if df.empty:
        fig.update_layout(
            geo=dict(
                projection_type="orthographic",
                showland=True,
                landcolor="#F4F7FE",
                showocean=True,
                oceancolor="rgba(255, 255, 255, 0.95)",
                showcountries=True,
                countrycolor="rgba(67, 24, 255, 0.12)",
                countrywidth=0.8,
                showcoastlines=True,
                coastlinecolor="rgba(67, 24, 255, 0.15)",
                coastlinewidth=0.6,
                showlakes=False,
                showrivers=False,
                framecolor="rgba(67, 24, 255, 0.06)",
                framewidth=1,
                lonaxis=dict(showgrid=True, gridcolor="rgba(67, 24, 255, 0.06)", gridwidth=0.5, dtick=15),
                lataxis=dict(showgrid=True, gridcolor="rgba(67, 24, 255, 0.06)", gridwidth=0.5, dtick=15),
                projection_rotation=dict(lon=28.96, lat=41.01, roll=0),
                projection_scale=1.0,
                bgcolor="rgba(0,0,0,0)",
            ),
            margin=dict(l=0, r=0, t=0, b=0),
            height=600,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            showlegend=False,
        )
        return fig

    color_maps = [_health_colors(h) for h in df["health"]]

    shadow_colors = [c["shadow"] for c in color_maps]
    halo_colors = [c["halo"] for c in color_maps]
    pin_colors = [c["pin"] for c in color_maps]
    pin_rgba_colors = [c["pin_rgba"] for c in color_maps]
    gradient_colors = [c["gradient"] for c in color_maps]

    halo_sizes = [max(32, min(60, math.log1p(row["vm_count"]) * 10 + 24)) for _, row in df.iterrows()]
    pin_sizes = [max(14, min(26, math.log1p(row["vm_count"]) * 4 + 10)) for _, row in df.iterrows()]
    shadow_sizes = [max(10, min(18, s * 0.55)) for s in pin_sizes]

    ping_values = [random.randint(8, 180) for _ in range(len(df))]

    hover_template = (
        "<b style='font-size:15px;color:#2B3674;'>%{customdata[1]}</b><br>"
        "<span style='color:#7B8EC8;'>━━━━━━━━━━━━━━━━━━━</span><br>"
        "📍 <span style='color:#A3AED0;'>%{customdata[2]}</span><br>"
        "💻 <b>%{customdata[3]:,}</b> VMs  ·  🖥️ <b>%{customdata[4]:,}</b> Hosts<br>"
        "⚡ Health: <b>%{customdata[5]:.1f}%%</b><br>"
        "<span style='color:#7B8EC8;'>━━━━━━━━━━━━━━━━━━━</span><br>"
        "🏓 <span style='color:#A3AED0;'>Ping: </span><b>%{customdata[6]}ms</b>"
        " · <span style='color:#05CD99;'>Active Route</span>"
        "<extra></extra>"
    )

    customdata_vals = []
    for i, (_, row) in enumerate(df.iterrows()):
        customdata_vals.append([
            row["id"], row["name"], row["location"],
            row["vm_count"], row["host_count"], row["health"],
            ping_values[i], row.get("site_name", ""),
        ])

    fig.add_trace(go.Scattergeo(
        lat=df["lat"] - 0.3,
        lon=df["lon"] + 0.15,
        mode="markers",
        marker=dict(
            size=shadow_sizes,
            color=shadow_colors,
            opacity=0.3,
            symbol="circle",
        ),
        hoverinfo="skip",
        name="",
    ))

    fig.add_trace(go.Scattergeo(
        lat=df["lat"],
        lon=df["lon"],
        mode="markers",
        marker=dict(
            size=halo_sizes,
            color=halo_colors,
            opacity=0.5,
            symbol="circle",
        ),
        hoverinfo="skip",
        name="",
    ))

    fig.add_trace(go.Scattergeo(
        lat=df["lat"],
        lon=df["lon"],
        mode="markers",
        marker=dict(
            size=pin_sizes,
            color=pin_colors,
            opacity=1.0,
            symbol="circle",
            gradient=dict(
                type="radial",
                color=gradient_colors,
            ),
            line=dict(
                width=2,
                color=pin_rgba_colors,
            ),
        ),
        customdata=customdata_vals,
        hovertemplate=hover_template,
        hoverlabel=dict(
            bgcolor="rgba(255, 255, 255, 0.92)",
            bordercolor="rgba(67, 24, 255, 0.25)",
            font=dict(
                family="DM Sans, sans-serif",
                size=13,
                color="#2B3674",
            ),
            align="left",
        ),
        name="",
    ))

    fig.update_layout(
        geo=dict(
            projection_type="orthographic",
            showland=True,
            landcolor="#F4F7FE",
            showocean=True,
            oceancolor="rgba(255, 255, 255, 0.95)",
            showcountries=True,
            countrycolor="rgba(67, 24, 255, 0.12)",
            countrywidth=0.8,
            showcoastlines=True,
            coastlinecolor="rgba(67, 24, 255, 0.15)",
            coastlinewidth=0.6,
            showlakes=False,
            showrivers=False,
            framecolor="rgba(67, 24, 255, 0.06)",
            framewidth=1,
            lonaxis=dict(showgrid=True, gridcolor="rgba(67, 24, 255, 0.06)", gridwidth=0.5, dtick=15),
            lataxis=dict(showgrid=True, gridcolor="rgba(67, 24, 255, 0.06)", gridwidth=0.5, dtick=15),
            projection_rotation=dict(lon=28.96, lat=41.01, roll=0),
            projection_scale=1.0,
            bgcolor="rgba(0,0,0,0)",
        ),
        margin=dict(l=0, r=0, t=0, b=0),
        height=600,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )

    return fig


def _pct_color(v):
    if v >= 80:
        return "red"
    if v >= 50:
        return "orange"
    return "teal"


def _build_region_menu(summaries):
    region_dc_counts = {}
    region_health = {}
    for dc in summaries:
        sn = (dc.get("site_name") or "").upper().strip()
        region_dc_counts[sn] = region_dc_counts.get(sn, 0) + 1
        stats = dc.get("stats", {})
        cpu = stats.get("used_cpu_pct", 0.0)
        ram = stats.get("used_ram_pct", 0.0)
        region_health.setdefault(sn, []).append((cpu + ram) / 2.0)
    avg_health = {k: sum(v) / len(v) for k, v in region_health.items() if v}

    items = []
    for group_name, group_data in REGION_HIERARCHY.items():
        children_components = []
        group_total = 0
        for site_key, site_data in group_data["children"].items():
            count = region_dc_counts.get(site_key, 0)
            group_total += count
            flag_icon = site_data.get("flag")
            left_section = DashIconify(icon=flag_icon, width=18) if flag_icon else None
            avg = avg_health.get(site_key, 0)
            children_components.append(
                dmc.NavLink(
                    id={"type": "region-nav", "region": site_key},
                    label=site_data["label"],
                    description=f"Avg Load: {avg:.0f}%",
                    leftSection=left_section,
                    rightSection=dmc.Badge(
                        f"{count} DC{'s' if count != 1 else ''}",
                        size="xs",
                        variant="light",
                        color="indigo" if count > 0 else "gray",
                    ),
                    className="region-nav-link",
                )
            )
        items.append(
            dmc.AccordionItem(
                value=group_name,
                children=[
                    dmc.AccordionControl(
                        dmc.Group(
                            gap="sm",
                            children=[
                                DashIconify(icon=group_data["icon"], width=20, color="#4318FF"),
                                dmc.Text(group_name, fw=700, size="sm", c="#2B3674"),
                                dmc.Badge(f"{group_total} DCs", variant="light", color="gray", size="xs"),
                            ],
                        )
                    ),
                    dmc.AccordionPanel(p="xs", children=children_components),
                ],
            )
        )

    return dmc.Accordion(
        id="region-accordion",
        variant="separated",
        radius="md",
        chevronPosition="right",
        multiple=True,
        value=[],
        className="region-accordion",
        children=items,
    )


def build_region_detail_panel(region, tr):
    summaries = api.get_all_datacenters_summary(tr)
    region_upper = (region or "").upper().strip()
    dcs = [dc for dc in summaries if (dc.get("site_name") or "").upper().strip() == region_upper]

    if not dcs:
        return dmc.Paper(
            p="xl",
            radius="lg",
            children=[dmc.Text("No datacenters found for this region.", c="#A3AED0")],
        )

    total_vms = sum(dc.get("vm_count", 0) for dc in dcs)
    total_hosts = sum(dc.get("host_count", 0) for dc in dcs)

    dc_cards = []
    for dc in dcs:
        dc_id = dc.get("id", "")
        data = api.get_dc_details(dc_id, tr)
        meta = data.get("meta", {})
        intel = data.get("intel", {})
        power = data.get("power", {})
        energy = data.get("energy", {})
        platforms = data.get("platforms", {})

        dc_name = meta.get("name", dc_id)

        cpu_cap = intel.get("cpu_cap", 0.0)
        cpu_used = intel.get("cpu_used", 0.0)
        cpu_pct = round(cpu_used / cpu_cap * 100, 1) if cpu_cap > 0 else 0.0
        ram_cap = intel.get("ram_cap", 0.0)
        ram_used = intel.get("ram_used", 0.0)
        ram_pct = round(ram_used / ram_cap * 100, 1) if ram_cap > 0 else 0.0
        storage_cap = intel.get("storage_cap", 0.0)
        storage_used = intel.get("storage_used", 0.0)
        storage_pct = round(storage_used / storage_cap * 100, 1) if storage_cap > 0 else 0.0

        health_val = (cpu_pct + ram_pct) / 2.0
        health_color = "red" if health_val >= 70 else ("orange" if health_val >= 40 else "teal")

        total_kw = float(energy.get("total_kw", 0.0) or 0.0)
        total_hosts = intel.get("hosts", 0) + power.get("hosts", 0)
        total_vms_dc = intel.get("vms", 0) + power.get("lpar_count", 0)

        vmware = platforms.get("vmware", {})
        nutanix = platforms.get("nutanix", {})
        ibm = platforms.get("ibm", {})
        arch_items = []
        if vmware.get("clusters", 0) > 0 or vmware.get("hosts", 0) > 0:
            arch_items.append(f"VMware ({vmware.get('clusters', 0)}C, {vmware.get('hosts', 0)}H)")
        if nutanix.get("hosts", 0) > 0:
            arch_items.append(f"Nutanix ({nutanix.get('hosts', 0)}H)")
        if ibm.get("hosts", 0) > 0:
            arch_items.append(f"IBM ({ibm.get('hosts', 0)}H, {ibm.get('lpars', 0)}L)")
        arch_text = " \u00b7 ".join(arch_items) if arch_items else "\u2014"

        dc_cards.append(
            dmc.Paper(
                p="lg",
                radius="md",
                className="detail-dc-card",
                style={
                    "background": "rgba(255,255,255,0.95)",
                    "border": "1px solid rgba(67,24,255,0.08)",
                    "boxShadow": "0 2px 12px rgba(67,24,255,0.06)",
                },
                children=[
                    dmc.Group(
                        justify="space-between",
                        mb="sm",
                        children=[
                            dmc.Text(dc_name, fw=700, size="md", c="#2B3674"),
                            dmc.Badge(f"{health_val:.0f}% Health", color=health_color, variant="light", size="sm"),
                        ],
                    ),
                    dmc.SimpleGrid(
                        cols=4,
                        spacing="xs",
                        mb="xs",
                        children=[
                            dmc.Stack(gap=2, align="center", children=[
                                dmc.RingProgress(size=64, thickness=5, roundCaps=True,
                                    sections=[{"value": cpu_pct, "color": _pct_color(cpu_pct)}],
                                    label=dmc.Text(f"{cpu_pct:.0f}%", ta="center", fw=700, size="xs")),
                                dmc.Text("CPU", size="xs", fw=600, c="#A3AED0"),
                            ]),
                            dmc.Stack(gap=2, align="center", children=[
                                dmc.RingProgress(size=64, thickness=5, roundCaps=True,
                                    sections=[{"value": ram_pct, "color": _pct_color(ram_pct)}],
                                    label=dmc.Text(f"{ram_pct:.0f}%", ta="center", fw=700, size="xs")),
                                dmc.Text("RAM", size="xs", fw=600, c="#A3AED0"),
                            ]),
                            dmc.Stack(gap=2, align="center", children=[
                                dmc.RingProgress(size=64, thickness=5, roundCaps=True,
                                    sections=[{"value": storage_pct, "color": _pct_color(storage_pct)}],
                                    label=dmc.Text(f"{storage_pct:.0f}%", ta="center", fw=700, size="xs")),
                                dmc.Text("Storage", size="xs", fw=600, c="#A3AED0"),
                            ]),
                            dmc.Stack(gap=4, justify="center", children=[
                                dmc.Group(gap="xs", children=[
                                    DashIconify(icon="solar:server-bold-duotone", width=12, color="#A3AED0"),
                                    dmc.Text(f"{total_hosts:,}h", size="xs", c="#2B3674", fw=600),
                                ]),
                                dmc.Group(gap="xs", children=[
                                    DashIconify(icon="solar:laptop-bold-duotone", width=12, color="#A3AED0"),
                                    dmc.Text(f"{total_vms_dc:,}vm", size="xs", c="#2B3674", fw=600),
                                ]),
                                dmc.Group(gap="xs", children=[
                                    DashIconify(icon="material-symbols:bolt-outline", width=12, color="#A3AED0"),
                                    dmc.Text(f"{total_kw:.1f}kW", size="xs", c="#2B3674", fw=600),
                                ]),
                            ]),
                        ],
                    ),
                    dmc.Divider(my="xs", color="rgba(67,24,255,0.06)"),
                    dmc.Group(gap="xs", mb="sm", children=[
                        DashIconify(icon="solar:layers-minimalistic-bold-duotone", width=12, color="#4318FF"),
                        dmc.Text(arch_text, size="xs", c="#A3AED0"),
                    ]),
                    dmc.Group(justify="flex-end", children=[
                        dcc.Link(
                            dmc.Button(
                                "Rack Details",
                                variant="light",
                                color="indigo",
                                radius="md",
                                size="xs",
                                rightSection=DashIconify(icon="solar:arrow-right-bold-duotone", width=14),
                            ),
                            href=f"/datacenter/{dc_id}",
                            style={"textDecoration": "none"},
                        ),
                    ]),
                ],
            )
        )

    return html.Div(
        className="detail-panel-animate",
        children=[
            dmc.Paper(
                p="xl",
                radius="lg",
                style={
                    "background": "rgba(255,255,255,0.90)",
                    "backdropFilter": "blur(14px)",
                    "WebkitBackdropFilter": "blur(14px)",
                    "boxShadow": "0 8px 32px rgba(67,24,255,0.10), 0 2px 8px rgba(0,0,0,0.04)",
                    "border": "1px solid rgba(67,24,255,0.08)",
                },
                children=[
                    dmc.Group(
                        justify="space-between",
                        align="center",
                        children=[
                            dmc.Group(gap="sm", align="center", children=[
                                DashIconify(icon="solar:map-point-bold-duotone", width=24, color="#4318FF"),
                                dmc.Text(region_upper.title(), fw=800, size="xl", c="#2B3674"),
                            ]),
                            dmc.Group(gap="sm", children=[
                                dmc.Badge(f"{len(dcs)} DCs", color="indigo", variant="light"),
                                dmc.Badge(f"{total_vms:,} VMs", color="teal", variant="light"),
                                dmc.Badge(f"{total_hosts:,} Hosts", color="gray", variant="light"),
                            ]),
                        ],
                    ),
                    dmc.Divider(my="md", color="rgba(67,24,255,0.08)"),
                    dmc.SimpleGrid(
                        cols={"base": 1, "sm": 2, "lg": 3},
                        spacing="lg",
                        children=dc_cards,
                    ),
                ],
            ),
        ],
    )


def build_global_view(time_range=None):
    tr = time_range or default_time_range()
    summaries = api.get_all_datacenters_summary(tr)
    df = _build_map_dataframe(summaries)
    map_fig = _create_map_figure(df)

    export_rows = _global_export_table(summaries)

    return html.Div([
        dcc.Store(id="selected-region-store", data=None),
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

        dmc.Grid(
            gutter="lg",
            style={"margin": "0 32px"},
            children=[
                dmc.GridCol(
                    span=8,
                    children=[
                        dmc.Paper(
                            radius="lg",
                            style={
                                "overflow": "hidden",
                                "boxShadow": "0 2px 16px rgba(67,24,255,0.06), 0 1px 4px rgba(0,0,0,0.04)",
                                "border": "1px solid rgba(255,255,255,0.7)",
                            },
                            children=[
                                dmc.Group(
                                    justify="flex-end",
                                    px="md",
                                    pt="md",
                                    children=[
                                        dmc.Button(
                                            "Reset",
                                            id="global-map-reset-btn",
                                            variant="subtle",
                                            color="gray",
                                            radius="md",
                                            size="xs",
                                            leftSection=DashIconify(icon="solar:refresh-circle-bold-duotone", width=16),
                                        ),
                                    ],
                                ),
                                html.Div(
                                    style={"width": "100%", "overflow": "hidden"},
                                    children=[
                                        dcc.Graph(
                                            id="global-map-graph",
                                            figure=map_fig,
                                            config={"displayModeBar": False, "scrollZoom": True, "responsive": True},
                                            style={"height": "600px", "width": "100%", "borderRadius": "12px"},
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),
                dmc.GridCol(
                    span=4,
                    children=[
                        dmc.Paper(
                            id="region-menu-panel",
                            radius="lg",
                            h=600,
                            p="lg",
                            style={
                                "boxShadow": "0 2px 16px rgba(67,24,255,0.06), 0 1px 4px rgba(0,0,0,0.04)",
                                "border": "1px solid rgba(255,255,255,0.7)",
                                "background": "rgba(255,255,255,0.90)",
                            },
                            children=[
                                dmc.Group(
                                    justify="space-between",
                                    align="center",
                                    mb="sm",
                                    children=[
                                        dmc.Group(gap="sm", children=[
                                            DashIconify(icon="solar:map-bold-duotone", width=20, color="#4318FF"),
                                            dmc.Text("Regions", fw=700, size="md", c="#2B3674"),
                                        ]),
                                        dmc.Badge(f"{len(summaries)} DCs", variant="light", color="indigo", size="sm"),
                                    ],
                                ),
                                dmc.Divider(mb="sm", color="rgba(67,24,255,0.08)"),
                                dmc.ScrollArea(
                                    h=510,
                                    type="auto",
                                    children=[_build_region_menu(summaries)],
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        ),

        dcc.Loading(
            id="detail-loading",
            type="circle",
            color="#4318FF",
            children=html.Div(
                id="global-detail-panel",
                style={"padding": "0 32px", "marginTop": "24px"},
                children=[
                    html.Div(
                        style={"textAlign": "center", "padding": "48px 0"},
                        children=[
                            DashIconify(icon="solar:map-point-search-bold-duotone", width=48, color="#A3AED0"),
                            dmc.Text(
                                "Select a region from the menu or click a pin on the map",
                                c="#A3AED0",
                                size="sm",
                                mt="md",
                            ),
                        ],
                    )
                ],
            ),
        ),
    ])


def build_dc_info_card(dc_id, tr, site_name=""):
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

    health_val = (cpu_pct + ram_pct) / 2.0
    health_color = "red" if health_val >= 70 else ("orange" if health_val >= 40 else "teal")
    total_kw = float(energy.get("total_kw", 0.0) or 0.0)
    total_hosts = intel.get("hosts", 0) + power.get("hosts", 0)
    total_vms = intel.get("vms", 0) + power.get("lpar_count", 0)

    vmware = platforms.get("vmware", {})
    nutanix = platforms.get("nutanix", {})
    ibm = platforms.get("ibm", {})
    arch_items = []
    if vmware.get("clusters", 0) > 0 or vmware.get("hosts", 0) > 0:
        arch_items.append(f"VMware ({vmware.get('clusters', 0)}C, {vmware.get('hosts', 0)}H)")
    if nutanix.get("hosts", 0) > 0:
        arch_items.append(f"Nutanix ({nutanix.get('hosts', 0)}H)")
    if ibm.get("hosts", 0) > 0:
        arch_items.append(f"IBM ({ibm.get('hosts', 0)}H, {ibm.get('lpars', 0)}L)")
    arch_text = " \u00b7 ".join(arch_items) if arch_items else "\u2014"

    return dmc.Paper(
        p="xl",
        radius="lg",
        className="detail-dc-card",
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
                align="center",
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
                    dmc.Badge(f"{health_val:.0f}% Health", color=health_color, variant="light", size="md"),
                ],
            ),
            dmc.Divider(my="md", color="rgba(67, 24, 255, 0.08)"),
            dmc.SimpleGrid(
                cols=4,
                spacing="lg",
                children=[
                    dmc.Stack(gap=4, align="center", children=[
                        dmc.RingProgress(size=80, thickness=7, roundCaps=True,
                            sections=[{"value": cpu_pct, "color": _pct_color(cpu_pct)}],
                            label=dmc.Text(f"{cpu_pct:.0f}%", ta="center", fw=700, size="sm")),
                        dmc.Text("CPU", size="xs", fw=600, c="#A3AED0"),
                    ]),
                    dmc.Stack(gap=4, align="center", children=[
                        dmc.RingProgress(size=80, thickness=7, roundCaps=True,
                            sections=[{"value": ram_pct, "color": _pct_color(ram_pct)}],
                            label=dmc.Text(f"{ram_pct:.0f}%", ta="center", fw=700, size="sm")),
                        dmc.Text("RAM", size="xs", fw=600, c="#A3AED0"),
                    ]),
                    dmc.Stack(gap=4, align="center", children=[
                        dmc.RingProgress(size=80, thickness=7, roundCaps=True,
                            sections=[{"value": storage_pct, "color": _pct_color(storage_pct)}],
                            label=dmc.Text(f"{storage_pct:.0f}%", ta="center", fw=700, size="sm")),
                        dmc.Text("Storage", size="xs", fw=600, c="#A3AED0"),
                    ]),
                    dmc.Stack(gap=6, justify="center", children=[
                        dmc.Group(gap="xs", children=[
                            DashIconify(icon="solar:server-bold-duotone", width=14, color="#A3AED0"),
                            dmc.Text(f"{total_hosts:,} Hosts", size="sm", c="#2B3674", fw=600),
                        ]),
                        dmc.Group(gap="xs", children=[
                            DashIconify(icon="solar:laptop-bold-duotone", width=14, color="#A3AED0"),
                            dmc.Text(f"{total_vms:,} VMs", size="sm", c="#2B3674", fw=600),
                        ]),
                        dmc.Group(gap="xs", children=[
                            DashIconify(icon="material-symbols:bolt-outline", width=14, color="#A3AED0"),
                            dmc.Text(f"{total_kw:.1f} kW", size="sm", c="#2B3674", fw=600),
                        ]),
                    ]),
                ],
            ),
            dmc.Divider(my="md", color="rgba(67, 24, 255, 0.08)"),
            dmc.Group(gap="xs", mb="md", children=[
                DashIconify(icon="solar:layers-minimalistic-bold-duotone", width=16, color="#4318FF"),
                dmc.Text("Architecture:", size="sm", fw=600, c="#2B3674"),
                dmc.Text(arch_text, size="sm", c="#A3AED0"),
            ]),
            dmc.Group(justify="flex-end", children=[
                dcc.Link(
                    dmc.Button(
                        "Rack Details",
                        variant="light",
                        color="indigo",
                        radius="md",
                        size="sm",
                        rightSection=DashIconify(icon="solar:arrow-right-bold-duotone", width=16),
                    ),
                    href=f"/datacenter/{dc_id}",
                    style={"textDecoration": "none"},
                ),
            ]),
        ],
    )


@callback(
    Output("global-export-download", "data"),
    Input("global-export-csv", "n_clicks"),
    Input("global-export-xlsx", "n_clicks"),
    State("global-export-store", "data"),
    State("app-time-range", "data"),
    State("selected-region-store", "data"),
    prevent_initial_call=True,
)
def export_global_view(nc, nx, store, time_range, selected_region):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    tid = ctx.triggered[0]["prop_id"].split(".")[0]
    fmt_map = {"global-export-csv": "csv", "global-export-xlsx": "xlsx"}
    fmt = fmt_map.get(tid)
    if not fmt:
        return dash.no_update
    store = store or {}
    rows = store.get("rows") or []
    df = records_to_dataframe(rows)
    extra = {}
    if selected_region is not None:
        extra["map_selected_region"] = selected_region
    sheets = {"DC_Summary": df}
    if fmt == "xlsx":
        content = dataframes_to_excel_with_meta(sheets, time_range, "Global_View", extra or None)
        return dash_send_excel_workbook(content, "global_view")
    report_info = build_report_info_df(time_range, "Global_View", extra or None)
    return dash_send_csv_bytes(
        csv_bytes_with_report_header(report_info, [("DC_Summary", df)]),
        "global_view",
    )
