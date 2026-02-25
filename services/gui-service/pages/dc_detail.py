import dash
import dash_mantine_components as dmc
from dash import callback, ctx, dcc, Output, Input, State
from dash_iconify import DashIconify
import plotly.graph_objects as go

from services.api_client import get_summary, get_dc_detail

dash.register_page(__name__, path_template="/datacenters/<dc_code>", name="DC Detay")

_STATUS_COLOR = {"Healthy": "green", "Degraded": "orange", "Unreachable": "red"}

_INDIGO = "#4c6ef5"
_VIOLET = "#845ef7"
_SKY    = "#74c0fc"
_EMPTY  = "#e9ecef"

_INTERVAL_MS = 900_000  # 15 dakika


# ── Chart Factories ────────────────────────────────────────────────────────────

def _donut_fig(used, cap, color):
    free = max(cap - used, 0)
    pct  = round(used / cap * 100) if cap > 0 else 0
    fig  = go.Figure(go.Pie(
        values=[used, free],
        labels=["Kullanılan", "Serbest"],
        hole=0.62,
        marker=dict(colors=[color, _EMPTY], line=dict(width=0)),
        textinfo="none",
        hovertemplate="<b>%{label}</b><br>%{value:.1f}<extra></extra>",
        direction="clockwise",
    ))
    fig.update_layout(
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom", y=-0.30,
            xanchor="center", x=0.5,
            font=dict(size=11),
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=8, b=52, l=8, r=8),
        annotations=[dict(
            text=f"<b>{pct}%</b>",
            x=0.5, y=0.5,
            font=dict(size=22, color="#1a1b2e"),
            showarrow=False,
        )],
    )
    return fig


def _bar_fig(x, y, colors):
    fig = go.Figure(go.Bar(
        x=x, y=y,
        marker=dict(color=colors, line=dict(width=0)),
        hovertemplate="<b>%{x}</b>: %{y}<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=8, b=8, l=40, r=8),
        xaxis=dict(showgrid=False, tickfont=dict(size=12)),
        yaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.06)", tickfont=dict(size=12)),
        bargap=0.40,
    )
    return fig


# ── Simulation Logic ───────────────────────────────────────────────────────────

def _apply_cluster_filter(intel, cluster_val):
    """Return proportionally scaled intel values for a single cluster selection.

    Distribution model: higher-indexed clusters carry more utilisation load
    (non-uniform, deterministic). Capacity is split equally per cluster.
    """
    cpu_used  = float(intel.get("cpu_used",     0))
    cpu_cap   = float(intel.get("cpu_cap",      1))
    ram_used  = float(intel.get("ram_used",     0))
    ram_cap   = float(intel.get("ram_cap",      1))
    stor_used = float(intel.get("storage_used", 0))
    stor_cap  = float(intel.get("storage_cap",  1))
    clusters  = int(intel.get("clusters", 1)) or 1

    if not cluster_val or cluster_val == "all" or not cluster_val.startswith("c"):
        return dict(cpu_used=cpu_used, cpu_cap=cpu_cap,
                    ram_used=ram_used, ram_cap=ram_cap,
                    stor_used=stor_used, stor_cap=stor_cap)

    idx          = int(cluster_val[1:]) - 1              # 0-indexed
    total_weight = clusters * (clusters + 1) / 2         # sum(1..N)
    usage_w      = (idx + 1) / total_weight              # proportional load share
    cap_w        = 1.0 / clusters                        # equal capacity split

    return dict(
        cpu_used  = cpu_used  * usage_w,
        cpu_cap   = cpu_cap   * cap_w,
        ram_used  = ram_used  * usage_w,
        ram_cap   = ram_cap   * cap_w,
        stor_used = stor_used * usage_w,
        stor_cap  = stor_cap  * cap_w,
    )


# ── UI Helpers ─────────────────────────────────────────────────────────────────

def _chart_card(title, fig, height=240, graph_id=None):
    graph_kwargs = {"id": graph_id} if graph_id else {}
    return dmc.Paper(
        [
            dmc.Text(title, fw=600, size="sm", c="dimmed", mb="xs"),
            dcc.Graph(
                figure=fig,
                config={"displayModeBar": False, "responsive": True},
                style={"height": f"{height}px"},
                **graph_kwargs,
            ),
        ],
        className="chart-paper",
        p="md",
        radius="lg",
        withBorder=False,
    )


def _stat_pill(icon, label, value, color):
    return dmc.Paper(
        dmc.Group(
            [
                dmc.ThemeIcon(
                    DashIconify(icon=icon, width=16),
                    color=color, variant="light", size="md", radius="sm",
                ),
                dmc.Stack(
                    [dmc.Text(value, fw=700, size="md"), dmc.Text(label, c="dimmed", size="xs")],
                    gap=0,
                ),
            ],
            gap="sm",
            align="center",
        ),
        className="chart-paper",
        p="sm",
        radius="md",
        withBorder=False,
    )


def _filter_bar(select_id, select_data, placeholder="Seçiniz..."):
    return dmc.Paper(
        dmc.Group(
            [
                dmc.ThemeIcon(
                    DashIconify(icon="mdi:filter-variant", width=16),
                    color="indigo", variant="light", size="md", radius="xl",
                ),
                dmc.Text("Filtrele:", fw=700, size="sm", c="dimmed"),
                dmc.Select(
                    id=select_id,
                    data=select_data,
                    value=select_data[0]["value"] if select_data else None,
                    placeholder=placeholder,
                    size="sm",
                    w=220,
                    radius="xl",
                    clearable=False,
                ),
            ],
            gap="sm",
            align="center",
        ),
        className="chart-paper",
        p="sm",
        radius="xl",
        withBorder=False,
        mb="md",
    )


# ── Tab Builders ───────────────────────────────────────────────────────────────

def _intel_tab(intel):
    cpu_used  = float(intel.get("cpu_used",     0))
    cpu_cap   = float(intel.get("cpu_cap",      1))
    ram_used  = float(intel.get("ram_used",     0))
    ram_cap   = float(intel.get("ram_cap",      1))
    stor_used = float(intel.get("storage_used", 0))
    stor_cap  = float(intel.get("storage_cap",  1))
    clusters  = int(intel.get("clusters", 0))
    hosts     = int(intel.get("hosts",    0))
    vms       = int(intel.get("vms",      0))

    cluster_opts = [{"label": "Tümü", "value": "all"}] + [
        {"label": f"Cluster {i + 1}", "value": f"c{i + 1}"}
        for i in range(clusters)
    ]

    charts = dmc.SimpleGrid(
        [
            _chart_card("CPU Kullanımı (GHz)",     _donut_fig(cpu_used,  cpu_cap,  _INDIGO),
                        graph_id="intel-cpu-graph"),
            _chart_card("RAM Kullanımı (GB)",       _donut_fig(ram_used,  ram_cap,  _VIOLET),
                        graph_id="intel-ram-graph"),
            _chart_card("Depolama Kullanımı (TB)",  _donut_fig(stor_used, stor_cap, _SKY),
                        graph_id="intel-storage-graph"),
        ],
        cols={"base": 1, "sm": 3},
        spacing="md",
    )

    pills = dmc.SimpleGrid(
        [
            _stat_pill("mdi:lan",             "Cluster",      str(clusters), "indigo"),
            _stat_pill("mdi:server",           "Host",         str(hosts),    "blue"),
            _stat_pill("mdi:desktop-classic",  "Sanal Makine", str(vms),      "violet"),
        ],
        cols={"base": 3},
        spacing="md",
    )

    return dmc.Box([
        _filter_bar("intel-cluster-filter", cluster_opts, "Cluster seç..."),
        dcc.Loading(
            children=[dmc.Stack([charts, pills], gap="md")],
            type="dot",
            color="#4c6ef5",
        ),
    ])


def _power_tab(power, energy):
    total_kw  = float(energy.get("total_kw", 0))
    ibm_hosts = int(power.get("hosts", 0))
    ibm_vms   = int(power.get("vms",   0))

    kpi = dmc.Paper(
        dmc.Group(
            [
                DashIconify(icon="mdi:lightning-bolt", width=40, color=_VIOLET),
                dmc.Stack(
                    [
                        dmc.Text(
                            id="power-kpi-kw",
                            children=f"{total_kw:.1f} kW",
                            fw=900, size="xl",
                        ),
                        dmc.Text("Toplam Enerji Tüketimi", c="dimmed", size="sm"),
                    ],
                    gap=2,
                ),
            ],
            align="center",
            gap="md",
        ),
        className="chart-paper",
        p="lg",
        radius="lg",
        withBorder=False,
    )

    bar = _chart_card(
        "IBM Altyapı Envanteri (Hosts & VMs)",
        _bar_fig(["IBM Hosts", "IBM VMs"], [ibm_hosts, ibm_vms], [_VIOLET, _INDIGO]),
        height=260,
        graph_id="power-bar-graph",
    )

    src_opts = [
        {"label": "Tümü",      "value": "all"},
        {"label": "IBM Power", "value": "ibm"},
        {"label": "vCenter",   "value": "vcenter"},
    ]

    return dmc.Box([
        _filter_bar("power-source-filter", src_opts, "Kaynak seç..."),
        dcc.Loading(
            children=[dmc.Stack([kpi, bar], gap="md")],
            type="dot",
            color="#4c6ef5",
        ),
    ])


# ── Unified Callback (Auto-Refresh + Filter) ───────────────────────────────────
#
# Tek callback tüm çıktıları yönetir:
#   - dcc.Interval tetiklenirse → API'den taze veri çek, store'u güncelle
#   - Filtre Input'u tetiklenirse → mevcut store verisini kullan, filtre uygula
#   - Her iki durumda da 5 grafik çıktısı + store birlikte güncellenir

@callback(
    Output("intel-cpu-graph",     "figure"),
    Output("intel-ram-graph",     "figure"),
    Output("intel-storage-graph", "figure"),
    Output("power-bar-graph",     "figure"),
    Output("power-kpi-kw",        "children"),
    Output("dc-detail-store",     "data"),
    Input("dc-detail-interval",   "n_intervals"),
    Input("intel-cluster-filter", "value"),
    Input("power-source-filter",  "value"),
    State("dc-code-store",        "data"),
    State("dc-detail-store",      "data"),
    prevent_initial_call=True,
)
def _refresh_and_render(n, cluster_val, src_val, dc_code, detail_data):
    # Interval tetiklendiğinde taze veri çek; filtre değişiminde mevcut veriyi koru
    if ctx.triggered_id == "dc-detail-interval" and dc_code:
        try:
            detail_data = get_dc_detail(dc_code)
        except Exception:
            pass  # sessiz başarısızlık: mevcut veri korunur

    intel  = (detail_data or {}).get("intel",  {})
    power  = (detail_data or {}).get("power",  {})
    energy = (detail_data or {}).get("energy", {})

    # Intel grafikleri (cluster filtresiyle)
    filtered = _apply_cluster_filter(intel, cluster_val)
    cpu_fig  = _donut_fig(filtered["cpu_used"],  filtered["cpu_cap"],  _INDIGO)
    ram_fig  = _donut_fig(filtered["ram_used"],  filtered["ram_cap"],  _VIOLET)
    stor_fig = _donut_fig(filtered["stor_used"], filtered["stor_cap"], _SKY)

    # Power grafikleri (kaynak filtresiyle)
    ibm_hosts = int(  (power  or {}).get("hosts",    0))
    ibm_vms   = int(  (power  or {}).get("vms",      0))
    total_kw  = float((energy or {}).get("total_kw", 0))

    if src_val == "vcenter":
        power_fig = _bar_fig(
            ["IBM Hosts", "IBM VMs", "vCenter Hosts", "vCenter VMs"],
            [ibm_hosts, ibm_vms, 0, 0],
            [_VIOLET, _INDIGO, "#adb5bd", "#ced4da"],
        )
        kpi_text = "Veri Yok"
    else:
        power_fig = _bar_fig(["IBM Hosts", "IBM VMs"], [ibm_hosts, ibm_vms], [_VIOLET, _INDIGO])
        kpi_text  = f"{total_kw:.1f} kW"

    return cpu_fig, ram_fig, stor_fig, power_fig, kpi_text, detail_data


# ── Page Layout ────────────────────────────────────────────────────────────────

def layout(dc_code=None, **kwargs):
    if not dc_code:
        return dmc.Text("DC kodu belirtilmedi.", c="red")

    # Status badge (from cached summary)
    status_badge = None
    try:
        summaries = get_summary()
        dc_data = next((d for d in summaries if d.get("id") == dc_code), None)
        if dc_data and dc_data.get("status"):
            color = _STATUS_COLOR.get(dc_data["status"], "gray")
            status_badge = dmc.Badge(
                dc_data["status"], color=color, variant="light", size="md", radius="sm",
            )
    except Exception:
        pass

    # Fetch full detail
    detail_raw  = {}
    error_alert = None
    intel_panel = dmc.Text("VMware & Nutanix metrikleri yüklenemedi.", c="dimmed", mt="md")
    power_panel = dmc.Text("IBM enerji verileri yüklenemedi.", c="dimmed", mt="md")
    try:
        detail      = get_dc_detail(dc_code)
        detail_raw  = detail
        intel_panel = _intel_tab(detail.get("intel", {}))
        power_panel = _power_tab(detail.get("power", {}), detail.get("energy", {}))
    except Exception as exc:
        error_alert = dmc.Alert(
            str(exc),
            title="Detay Verisi Yüklenemedi",
            color="red",
            icon=DashIconify(icon="mdi:alert-circle-outline"),
            mb="md",
        )

    hero = dmc.Box(
        [
            dmc.Anchor(
                "← Veri Merkezleri",
                href="/datacenters",
                size="sm",
                c="dimmed",
                display="block",
                mb="xs",
            ),
            dmc.Group(
                [dmc.Title(dc_code, order=2, fw=800)] + ([status_badge] if status_badge else []),
                align="center",
                gap="sm",
            ),
        ],
        className="dc-hero",
    )

    tabs = dmc.Tabs(
        [
            dmc.TabsList([
                dmc.TabsTab(
                    "Intel Virtualization", value="intel",
                    leftSection=DashIconify(icon="mdi:cpu-64-bit", width=16),
                ),
                dmc.TabsTab(
                    "Power Virtualization", value="power",
                    leftSection=DashIconify(icon="mdi:lightning-bolt-outline", width=16),
                ),
                dmc.TabsTab(
                    "Backup", value="backup",
                    leftSection=DashIconify(icon="mdi:backup-restore", width=16),
                ),
            ]),
            dmc.TabsPanel(intel_panel, value="intel", pt="md"),
            dmc.TabsPanel(power_panel, value="power", pt="md"),
            dmc.TabsPanel(
                dmc.Text(
                    "Yedekleme durumu — ileriki aşamalarda eklenecek.",
                    c="dimmed", mt="md",
                ),
                value="backup",
            ),
        ],
        value="intel",
    )

    stores   = [
        dcc.Store(id="dc-detail-store", data=detail_raw),
        dcc.Store(id="dc-code-store",   data=dc_code),
    ]
    interval = dcc.Interval(id="dc-detail-interval", interval=_INTERVAL_MS, n_intervals=0)
    body     = ([error_alert] if error_alert else []) + [tabs]
    return dmc.Container(stores + [interval, hero] + body, pt="xl", fluid=True)
