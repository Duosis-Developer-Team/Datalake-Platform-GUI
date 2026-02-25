import dash
import dash_mantine_components as dmc
import plotly.graph_objects as go
from dash import dcc
from dash_iconify import DashIconify

dash.register_page(__name__, path="/overview", name="Overview")

# ── Renk Paleti ─────────────────────────────────────────────────────────────
_INDIGO = "#4c6ef5"
_VIOLET = "#845ef7"
_SKY    = "#74c0fc"
_TEAL   = "#38d9a9"


# ── Mock Zaman Serisi Verileri (saatlik, son 24 saat) ───────────────────────

def _hours():
    return [f"{i:02d}:00" for i in range(24)]


def _cpu_series():
    """Sabah düşük, öğleden sonra pik, akşam düşer."""
    return [55, 52, 50, 48, 50, 56, 63, 71, 78, 82, 80, 77,
            75, 74, 76, 79, 77, 73, 68, 64, 60, 57, 55, 53]


def _ram_series():
    """RAM sürekli yüksek seyreder, gece biraz düşer."""
    return [68, 67, 66, 65, 66, 68, 71, 74, 77, 79, 80, 81,
            82, 82, 83, 84, 83, 82, 80, 78, 76, 74, 72, 70]


def _net_series():
    """Ağ trafiği mesai saatlerinde pik yapar."""
    return [12, 10, 9, 8, 9, 15, 28, 45, 62, 71, 74, 78,
            75, 72, 70, 68, 65, 55, 40, 28, 22, 18, 15, 13]


# ── Sparkline Figür Fabrikası ────────────────────────────────────────────────

def _sparkline_fig(series, color):
    r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
    fill_color = f"rgba({r},{g},{b},0.12)"

    fig = go.Figure(
        go.Scatter(
            x=_hours(),
            y=series,
            mode="lines",
            line=dict(color=color, width=2, shape="spline"),
            fill="tozeroy",
            fillcolor=fill_color,
            hovertemplate="%{x}: <b>%{y}</b><extra></extra>",
        )
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=0, b=0),
        showlegend=False,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        height=80,
    )
    return fig


# ── Sparkline Kart Bileşeni ─────────────────────────────────────────────────

def _spark_card(title, subtitle, value_str, series, color, icon):
    return dmc.Paper(
        [
            dmc.Group(
                [
                    dmc.ThemeIcon(
                        DashIconify(icon=icon, width=18),
                        color="indigo",
                        variant="light",
                        size="lg",
                        radius="md",
                    ),
                    dmc.Stack(
                        [
                            dmc.Text(title, fw=700, size="sm"),
                            dmc.Text(value_str, fw=800, size="xl", c=color),
                        ],
                        gap=0,
                    ),
                ],
                gap="sm",
                align="center",
                mb="xs",
            ),
            dcc.Graph(
                figure=_sparkline_fig(series, color),
                config={"displayModeBar": False},
                style={"height": "80px"},
            ),
            dmc.Text(subtitle, size="xs", c="dimmed", mt=2),
        ],
        className="chart-paper",
        p="md",
        radius="xl",
        withBorder=False,
    )


# ── Vendor Donut Grafik ──────────────────────────────────────────────────────

def _vendor_donut_fig():
    fig = go.Figure(
        go.Pie(
            labels=["VMware", "Nutanix", "IBM Power"],
            values=[60, 25, 15],
            hole=0.62,
            marker=dict(
                colors=[_INDIGO, _VIOLET, _SKY],
                line=dict(width=0),
            ),
            textinfo="label+percent",
            textfont=dict(size=12),
            hovertemplate="%{label}: <b>%{percent}</b><extra></extra>",
        )
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=0, b=0),
        showlegend=False,
        annotations=[dict(
            text="<b>Vendor<br>Mix</b>",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=13, color="#495057"),
        )],
        height=260,
    )
    return fig


def _legend_dot(color, label):
    return dmc.Group(
        [
            dmc.Box(style={
                "width": 10, "height": 10,
                "borderRadius": "50%",
                "backgroundColor": color,
                "flexShrink": 0,
            }),
            dmc.Text(label, size="xs"),
        ],
        gap=4,
        align="center",
    )


# ── Sistem Olay Günlüğü (Timeline) ──────────────────────────────────────────

_EVENTS = [
    {
        "title": "DC11 CPU Alarmı",
        "desc":  "CPU kullanımı %87'ye ulaştı — VMware Cluster 3.",
        "icon":  "mdi:alert-circle",
        "color": "red",
        "time":  "14:32",
    },
    {
        "title": "AZ11 Yedekleme Tamamlandı",
        "desc":  "Tüm VM'ler başarıyla yedeklendi (312 GB aktarıldı).",
        "icon":  "mdi:backup-restore",
        "color": "teal",
        "time":  "13:15",
    },
    {
        "title": "DC12 Yeni Cluster Eklendi",
        "desc":  "Nutanix AHV — 3 node, 96 çekirdek, 768 GB RAM.",
        "icon":  "mdi:server-plus",
        "color": "indigo",
        "time":  "11:08",
    },
    {
        "title": "Query-Service Cache Miss",
        "desc":  "Redis TTL doldu — tam veri yenilendi (41s).",
        "icon":  "mdi:database-refresh",
        "color": "orange",
        "time":  "09:45",
    },
    {
        "title": "Nutanix Cluster Sağlığı: OK",
        "desc":  "AZ12 — tüm node'lar up, disk hatası yok.",
        "icon":  "mdi:heart-pulse",
        "color": "green",
        "time":  "08:00",
    },
]


def _timeline():
    items = [
        dmc.TimelineItem(
            title=dmc.Group(
                [
                    dmc.Text(e["title"], fw=700, size="sm"),
                    dmc.Badge(e["time"], color="gray", variant="outline", size="xs"),
                ],
                justify="space-between",
                align="center",
            ),
            bullet=DashIconify(icon=e["icon"], width=14),
            children=[
                dmc.Text(e["desc"], size="xs", c="dimmed", mt=2),
            ],
        )
        for e in _EVENTS
    ]
    return dmc.Timeline(
        children=items,
        active=len(_EVENTS) - 1,
        bulletSize=22,
        lineWidth=2,
        color="indigo",
    )


# ── Sayfa Layout ─────────────────────────────────────────────────────────────

def layout(**kwargs):
    sparklines = dmc.SimpleGrid(
        [
            _spark_card(
                "Global CPU Trendi",
                "Son 24 saatin platform geneli CPU kullanımı",
                f"{_cpu_series()[-1]}%",
                _cpu_series(),
                _INDIGO,
                "mdi:cpu-64-bit",
            ),
            _spark_card(
                "Global RAM Trendi",
                "Son 24 saatin platform geneli bellek kullanımı",
                f"{_ram_series()[-1]}%",
                _ram_series(),
                _VIOLET,
                "mdi:memory",
            ),
            _spark_card(
                "Ağ Trafiği",
                "Son 24 saatin ortalama bant genişliği",
                f"{_net_series()[-1]} Gbps",
                _net_series(),
                _SKY,
                "mdi:network",
            ),
        ],
        cols={"base": 1, "sm": 3},
        spacing="md",
        mb="xl",
    )

    vendor_panel = dmc.Paper(
        [
            dmc.Group(
                [
                    dmc.ThemeIcon(
                        DashIconify(icon="mdi:chart-donut", width=18),
                        color="indigo",
                        variant="light",
                        size="lg",
                        radius="md",
                    ),
                    dmc.Stack(
                        [
                            dmc.Text("Altyapı Dağılımı", fw=700, size="md"),
                            dmc.Text("Hypervisor vendor mix", c="dimmed", size="xs"),
                        ],
                        gap=0,
                    ),
                ],
                gap="sm",
                mb="sm",
            ),
            dcc.Graph(
                figure=_vendor_donut_fig(),
                config={"displayModeBar": False},
                style={"height": "260px"},
            ),
            dmc.SimpleGrid(
                [
                    _legend_dot(_INDIGO, "VMware 60%"),
                    _legend_dot(_VIOLET, "Nutanix 25%"),
                    _legend_dot(_SKY,    "IBM Power 15%"),
                ],
                cols=3,
                mt="sm",
            ),
        ],
        className="chart-paper",
        p="xl",
        radius="xl",
        withBorder=False,
    )

    timeline_panel = dmc.Paper(
        [
            dmc.Group(
                [
                    dmc.ThemeIcon(
                        DashIconify(icon="mdi:timeline-clock", width=18),
                        color="indigo",
                        variant="light",
                        size="lg",
                        radius="md",
                    ),
                    dmc.Stack(
                        [
                            dmc.Text("Sistem Olay Günlüğü", fw=700, size="md"),
                            dmc.Text("Son 24 saat", c="dimmed", size="xs"),
                        ],
                        gap=0,
                    ),
                ],
                gap="sm",
                mb="md",
            ),
            _timeline(),
        ],
        className="chart-paper",
        p="xl",
        radius="xl",
        withBorder=False,
    )

    bottom = dmc.SimpleGrid(
        [vendor_panel, timeline_panel],
        cols={"base": 1, "sm": 2},
        spacing="md",
    )

    return dmc.Container(
        [
            dmc.Group(
                [
                    dmc.Stack(
                        [
                            dmc.Title("Executive Overview", order=2, fw=800),
                            dmc.Text(
                                "Bulutistan Altyapı Komuta Merkezi — Anlık Platform Durumu",
                                c="dimmed",
                                size="sm",
                            ),
                        ],
                        gap=2,
                    ),
                    dmc.Badge(
                        "CANLI",
                        color="teal",
                        variant="dot",
                        size="lg",
                    ),
                ],
                justify="space-between",
                align="flex-start",
                mb="xl",
            ),
            sparklines,
            bottom,
        ],
        pt="xl",
        fluid=True,
    )
