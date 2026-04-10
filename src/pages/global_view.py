import math
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import plotly.graph_objects as go
import dash
from dash import html, dcc, callback, Input, Output, State
import dash_mantine_components as dmc
from dash_iconify import DashIconify
import dash_globe_component
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

def build_3d_rack_overlay(dc_id, dc_name, racks):
    if not racks:
        return []

    grouped = {}
    for r in racks:
        h = r.get("hall_name") or "Main Hall"
        grouped.setdefault(h, []).append(r)

    layer_delay = 1
    hall_layers = []

    for hall, r_list in grouped.items():
        cards = []
        for i, r in enumerate(r_list):
            name = str(r.get("name") or "?")
            u = r.get("u_height") or 0
            pwr = r.get("kabin_enerji") or "—"
            status = (r.get("status") or "unknown").lower()

            scolor = "#05CD99" if status == "active" else ("#4385F4" if status == "planned" else "#FFB547")

            card = html.Div(
                className="rack-micro-card",
                style={"--card-delay": str(i)},
                children=[
                    html.Div(
                        style={"display": "flex", "justifyContent": "space-between", "alignItems": "center"},
                        children=[
                            html.Span(name, style={"fontWeight": "800", "color": "#2B3674", "fontSize": "13px"}),
                            html.Span("●", style={"color": scolor, "fontSize": "12px", "textShadow": f"0 0 8px {scolor}"})
                        ]
                    ),
                    html.Div(
                        style={"display": "flex", "gap": "6px", "alignItems": "center", "marginTop": "6px"},
                        children=[
                            DashIconify(icon="solar:ruler-bold-duotone", width=12, color="#A3AED0"),
                            html.Span(f"{u}U", style={"fontSize": "11px", "color": "#A3AED0", "fontWeight": "600"}),
                            html.Span("·", style={"color": "#A3AED0", "margin": "0 2px"}),
                            DashIconify(icon="solar:bolt-circle-bold-duotone", width=12, color="#A3AED0"),
                            html.Span(f"{pwr}", style={"fontSize": "11px", "color": "#A3AED0", "fontWeight": "600"})
                        ]
                    )
                ]
            )
            cards.append(card)

        hall_layers.append(
            html.Div(
                className="hall-layer",
                style={"--delay": str(layer_delay)},
                children=[
                    html.Div(
                        style={"display": "flex", "alignItems": "center", "gap": "8px", "marginBottom": "12px"},
                        children=[
                            DashIconify(icon="solar:server-square-bold-duotone", width=18, color="#05CD99"),
                            html.Div(hall, className="hall-title")
                        ]
                    ),
                    html.Div(cards, className="rack-micro-grid")
                ]
            )
        )
        layer_delay += 1

    return html.Div(
        className="hologram-scene",
        children=[
            html.Div(
                className="dc-hologram-base",
                children=[
                    html.Div(
                        style={"display": "flex", "justifyContent": "space-between", "alignItems": "flex-start", "marginBottom": "20px"},
                        children=[
                            html.Div([
                                dmc.Text(dc_name, c="white", fw=800, size="xl", style={"letterSpacing": "1px"}),
                                dmc.Text(f"{len(racks)} Cabinets Total", size="sm", style={"color": "rgba(255,255,255,0.7)", "marginTop": "2px"}),
                            ]),
                            dmc.ActionIcon(
                                DashIconify(icon="solar:close-circle-bold-duotone", width=26),
                                id="close-3d-overlay-btn",
                                variant="transparent",
                                color="gray",
                                size="lg",
                                style={"pointerEvents": "auto", "display": "block"}
                            )
                        ]
                    ),
                    html.Div(hall_layers, className="hologram-halls"),
                    dmc.Group(
                        justify="flex-end",
                        mt="xl",
                        style={"pointerEvents": "auto"},
                        children=[
                            dcc.Link(
                                dmc.Button(
                                    "Racks Details",
                                    variant="white",
                                    size="sm",
                                    radius="md",
                                    color="indigo",
                                    rightSection=DashIconify(icon="solar:arrow-right-bold-duotone", width=16)
                                ),
                                href=f"/dc-detail/{dc_id}",
                                style={"textDecoration": "none"}
                            )
                        ]
                    )
                ]
            )
        ]
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

DC_COORDINATES = {
    "DC11":      {"lat": 41.037961428839395,  "lon": 28.932597596324076},
    "DC13":      {"lat": 40.99624339876133,   "lon": 29.171462274232628},
    "DC15":      {"lat": 41.07269534784402,   "lon": 28.657853053455625},
    "DC17":      {"lat": 41.10716190578305,   "lon": 28.80144412392166},
    "DC12":      {"lat": 38.32499698249641,   "lon": 27.14179605187827},
    "DC14":      {"lat": 39.79603052359003,   "lon": 32.422135925099674},
    "DC16":      {"lat": 39.78445603075798,   "lon": 32.813705565035825},
    "AZ11":      {"lat": 40.38073354513049,   "lon": 49.8333150827992},
    "ICT11":     {"lat": 50.144014412507744,  "lon": 8.739884781472139},
    "ICT21":     {"lat": 51.528941788230235,  "lon": 0.27753550495317736},
    "Vadi Ofis": {"lat": 41.112041365157516,  "lon": 28.987566791632712},
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
    "ISTANBUL":   {"lon": 28.96,  "lat": 41.01, "scale": 33.0},
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
    (0.00,  0.00), (1.50,  0.00), (-1.50,  0.00),
    (0.00,  1.50), (0.00, -1.50), ( 1.50,  1.50),
    (-1.50, 1.50), (1.50, -1.50),
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


def _build_globe_data(summaries):
    city_index: dict[str, int] = {}
    data = []
    for dc in summaries:
        dc_id = dc.get("id", "")
        site_name = (dc.get("site_name") or "").upper().strip()
        exact = DC_COORDINATES.get(dc_id)
        if exact:
            lat = exact["lat"]
            lng = exact["lon"]
        else:
            base = CITY_COORDINATES.get(site_name)
            if not base:
                continue
            idx = city_index.get(site_name, 0)
            city_index[site_name] = idx + 1
            dlat, dlon = _CITY_OFFSETS[idx % len(_CITY_OFFSETS)]
            lat = base["lat"] + dlat
            lng = base["lon"] + dlon
        stats = dc.get("stats", {})
        cpu_pct = stats.get("used_cpu_pct", 0.0)
        ram_pct = stats.get("used_ram_pct", 0.0)
        health = (cpu_pct + ram_pct) / 2.0
        color = "#F04438" if health >= 70 else ("#F79009" if health >= 40 else "#17B26A")
        capacity = max(dc.get("vm_count", 0) or 0, (dc.get("host_count", 0) or 0) * 5)
        # Using a square root for more pronounced but controlled scaling, smaller base size
        size = round(min(0.07, max(0.015, 0.015 + math.sqrt(capacity) * 0.0012)), 4)
        data.append({
            "lat": float(lat),
            "lng": float(lng),
            "dc_id": dc_id,
            "size": size,
            "color": color,
            "site_name": dc.get("site_name", ""),
            "status": (dc.get("status") or "active").lower(),
            "vm_count": dc.get("vm_count", 0) or 0,
            "host_count": dc.get("host_count", 0) or 0,
            "health": round(health, 1),
        })
    return data


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
            uirevision="globe",
            geo=dict(
                resolution=50,
                projection_type="orthographic",
                showland=True,
                landcolor="#EEF2FB",
                showsubunits=True,
                subunitcolor="rgba(67, 24, 255, 0.08)",
                subunitwidth=0.4,
                showocean=True,
                oceancolor="#C8D8F0",
                showcountries=True,
                countrycolor="rgba(67, 24, 255, 0.30)",
                countrywidth=1.0,
                showcoastlines=True,
                coastlinecolor="rgba(40, 100, 200, 0.70)",
                coastlinewidth=1.2,
                showlakes=True,
                lakecolor="#B8CCE8",
                showrivers=True,
                rivercolor="rgba(60, 130, 210, 0.40)",
                riverwidth=0.6,
                framecolor="rgba(67, 24, 255, 0.15)",
                framewidth=1.5,
                lonaxis=dict(showgrid=True, gridcolor="rgba(67, 24, 255, 0.05)", gridwidth=0.3, dtick=30),
                lataxis=dict(showgrid=True, gridcolor="rgba(67, 24, 255, 0.05)", gridwidth=0.3, dtick=30),
                projection_rotation=dict(lon=28.96, lat=41.01, roll=0),
                projection_scale=1.0,
                bgcolor="rgba(0,0,0,0)",
            ),
            transition=dict(duration=400, easing="cubic-in-out"),
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

    def get_dynamic_sizes(row):
        total_infrastructure = row.get("vm_count", 0) + row.get("host_count", 0)
        # Dynamic scale factor using square root to smooth out enormous variances (e.g., 0 to 5000)
        scale_factor = math.sqrt(total_infrastructure)
        
        # Base sizes + scalable increments
        pin = max(10, min(45, 10 + (scale_factor * 0.7)))
        halo = max(24, min(90, 24 + (scale_factor * 1.6)))
        shadow = max(8, min(32, pin * 0.65))
        
        return halo, pin, shadow

    sizes = [get_dynamic_sizes(row) for _, row in df.iterrows()]
    halo_sizes = [size[0] for size in sizes]
    pin_sizes = [size[1] for size in sizes]
    shadow_sizes = [size[2] for size in sizes]

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
        uirevision="globe",
        geo=dict(
            resolution=50,
            projection_type="orthographic",
            showland=True,
            landcolor="#EEF2FB",
            showsubunits=True,
            subunitcolor="rgba(67, 24, 255, 0.08)",
            subunitwidth=0.4,
            showocean=True,
            oceancolor="#C8D8F0",
            showcountries=True,
            countrycolor="rgba(67, 24, 255, 0.30)",
            countrywidth=1.0,
            showcoastlines=True,
            coastlinecolor="rgba(40, 100, 200, 0.70)",
            coastlinewidth=1.2,
            showlakes=True,
            lakecolor="#B8CCE8",
            showrivers=True,
            rivercolor="rgba(60, 130, 210, 0.40)",
            riverwidth=0.6,
            framecolor="rgba(67, 24, 255, 0.15)",
            framewidth=1.5,
            lonaxis=dict(showgrid=True, gridcolor="rgba(67, 24, 255, 0.05)", gridwidth=0.3, dtick=30),
            lataxis=dict(showgrid=True, gridcolor="rgba(67, 24, 255, 0.05)", gridwidth=0.3, dtick=30),
            projection_rotation=dict(lon=28.96, lat=41.01, roll=0),
            projection_scale=1.0,
            bgcolor="rgba(0,0,0,0)",
        ),
        transition=dict(duration=400, easing="cubic-in-out"),
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
        style={"width": "100%"},
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

    def _fetch(dc):
        return dc, api.get_dc_details(dc.get("id", ""), tr)

    with ThreadPoolExecutor(max_workers=min(len(dcs), 8)) as pool:
        futures = {pool.submit(_fetch, dc): dc for dc in dcs}
        dc_detail_map = {}
        for future in as_completed(futures):
            dc, data = future.result()
            dc_detail_map[dc.get("id", "")] = data

    dc_cards = []
    for dc in dcs:
        dc_id = dc.get("id", "")
        data = dc_detail_map.get(dc_id, {})
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
                    dmc.Group(justify="flex-end", gap="xs", children=[
                        dmc.Button(
                            "Detail",
                            id={"type": "open-3d-hologram-btn", "index": dc_id},
                            variant="light",
                            color="indigo",
                            radius="md",
                            size="xs",
                            rightSection=DashIconify(icon="solar:magic-stick-3-bold-duotone", width=14),
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


def build_global_view(time_range=None, visible_sections=None):
    tr = time_range or default_time_range()
    vs = visible_sections

    def gvs(code: str) -> bool:
        return vs is None or code in vs

    summaries = api.get_all_datacenters_summary(tr)
    globe_data_array = _build_globe_data(summaries)
    export_rows = _global_export_table(summaries)

    return html.Div([
        dcc.Store(id="selected-region-store", data=None),
        dcc.Store(id="global-export-store", data={"rows": export_rows}),
        dcc.Download(id="global-export-download"),
        dcc.Store(id="current-view-mode", data="globe"),
        dcc.Store(id="selected-building-dc-store", data=None),
        dcc.Store(id="last-clicked-dc-id", data=None),
        dcc.Interval(id="building-reveal-timer", interval=1800, n_intervals=0, disabled=True, max_intervals=1),
        html.Div(id="globe-layer", children=[
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
                                (
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
                                    )
                                    if gvs("action:global:export")
                                    else html.Div()
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
                        (
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
                                        style={
                                            "position": "relative", "width": "100%", "height": "600px",
                                            "overflow": "hidden", "borderRadius": "12px", "background": "transparent",
                                        },
                                        children=[
                                            dash_globe_component.DashGlobe(
                                                id="global-map-graph",
                                                pointsData=globe_data_array,
                                                focusRegion=None,
                                                globeImageUrl="//unpkg.com/three-globe/example/img/earth-day.jpg",
                                                width="100%",
                                                height=600,
                                            ),
                                        ],
                                    ),
                                ],
                            )
                            if gvs("sec:global:globe")
                            else html.Div()
                        ),
                    ],
                ),
                dmc.GridCol(
                    span=4,
                    children=[
                        (
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
                                        w="100%",
                                        type="auto",
                                        children=[_build_region_menu(summaries)],
                                    ),
                                ],
                            )
                            if gvs("sec:global:regions")
                            else html.Div()
                        ),
                    ],
                ),
            ],
        ),

        (
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
            )
            if gvs("sec:global:detail")
            else html.Div()
        ),
        (
            html.Div(
                id="global-3d-modal-container",
                style={
                    "position": "fixed", "top": 0, "left": 0, "width": "100%", "height": "100%",
                    "backgroundColor": "rgba(30, 40, 80, 0.45)", "backdropFilter": "blur(8px)",
                    "WebkitBackdropFilter": "blur(12px)",
                    "zIndex": 9999, "display": "none", "alignItems": "center", "justifyContent": "center"
                },
                children=[],
            )
            if gvs("sec:global:3d")
            else html.Div()
        ),
        ]),
        html.Div(
            id="building-reveal-layer",
            style={"display": "none"},
            children=[
                html.Div(
                    className="building-reveal-inner",
                    children=[
                        DashIconify(
                            icon="noto:office-building",
                            width=280,
                            className="building-reveal-icon",
                        ),
                        html.Div(
                            id="building-reveal-dc-name",
                            className="building-reveal-name",
                            children="",
                        ),
                        html.Div(className="building-reveal-dots", children=[
                            html.Span(className="brd-dot"),
                            html.Span(className="brd-dot"),
                            html.Span(className="brd-dot"),
                        ]),
                    ],
                ),
            ],
        ),
        (
            html.Div(
                id="floor-map-layer",
                style={"display": "none"},
                children=[],
            )
            if gvs("sec:global:floor")
            else html.Div()
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
            dmc.Group(justify="flex-end", gap="sm", children=[
                dmc.Button(
                    "Detail",
                    id={"type": "open-3d-hologram-btn", "index": dc_id},
                    variant="light",
                    color="indigo",
                    radius="md",
                    size="sm",
                    rightSection=DashIconify(icon="solar:magic-stick-3-bold-duotone", width=16),
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
