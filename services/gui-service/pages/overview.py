"""
pages/overview.py — Executive Command Center

Task 4.1: Mock veriler kaldırıldı. Sparkline grafikleri artık Redis sliding
window (trend:cpu_pct, trend:ram_pct, trend:energy_kw) verilerinden besleniyor.

Mimari:
  - dcc.Interval(id="overview-trends-interval", interval=300_000ms)
    → Her 5 dakikada bir + ilk yükleme anında callback tetiklenir.
  - @callback → GET /overview/trends (api_client) → 3 Scatter figür güncellenir.
  - prevent_initial_call=False: İlk açılışta da callback çalışır,
    sampler'ın anında yazdığı ilk veri hemen görünür.
  - API hatası veya boş Redis → no_update (sessiz degradation, sayfa çökmez).
"""

from datetime import datetime, timezone

import dash
import dash_mantine_components as dmc
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, no_update
from dash_iconify import DashIconify

from services.api_client import get_overview_trends

dash.register_page(__name__, path="/overview", name="Overview")

# ── Renk Paleti ─────────────────────────────────────────────────────────────
_INDIGO = "#4c6ef5"
_VIOLET = "#845ef7"
_TEAL   = "#38d9a9"
_SKY    = "#74c0fc"


# ── Sparkline Figür Fabrikası ────────────────────────────────────────────────

def _sparkline_fig(labels: list, values: list, color: str) -> go.Figure:
    """
    Verilen labels (X ekseni) ve values (Y ekseni) ile dolgu çizgi grafiği oluşturur.
    labels boşsa boş, şeffaf bir figür döner — sayfa çökmez.
    """
    r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
    fill_color = f"rgba({r},{g},{b},0.12)"

    # ISO timestamp'leri HH:MM formatına dönüştür (eksen okunabilirliği)
    x_labels: list = []
    for lbl in labels:
        try:
            dt = datetime.fromisoformat(lbl)
            x_labels.append(dt.astimezone(timezone.utc).strftime("%H:%M"))
        except (ValueError, TypeError):
            x_labels.append(str(lbl))

    fig = go.Figure(
        go.Scatter(
            x=x_labels if x_labels else [None],
            y=values    if values    else [None],
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


def _empty_fig(color: str) -> go.Figure:
    """Redis boşken veya hata olduğunda gösterilecek boş figür."""
    return _sparkline_fig([], [], color)


# ── Sparkline Kart Bileşeni ─────────────────────────────────────────────────

def _spark_card(title: str, subtitle: str, graph_id: str, color: str, icon: str):
    """
    Başlangıç render'ında boş figür gösterir; callback anında veriyi doldurur.
    """
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
                            dmc.Text(id=f"{graph_id}-value", fw=800, size="xl", c=color,
                                     children="—"),
                        ],
                        gap=0,
                    ),
                ],
                gap="sm",
                align="center",
                mb="xs",
            ),
            dcc.Graph(
                id=graph_id,
                figure=_empty_fig(color),
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
                "Son örneklerin platform geneli CPU kullanımı",
                "spark-cpu",
                _INDIGO,
                "mdi:cpu-64-bit",
            ),
            _spark_card(
                "Global RAM Trendi",
                "Son örneklerin platform geneli bellek kullanımı",
                "spark-ram",
                _VIOLET,
                "mdi:memory",
            ),
            _spark_card(
                "Toplam Enerji",
                "Son örneklerin platform toplam enerji tüketimi",
                "spark-energy",
                _SKY,
                "mdi:lightning-bolt",
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
            # ── Interval: her 5 dk'da bir (prevent_initial_call=False → ilk açılışta da) ──
            dcc.Interval(
                id="overview-trends-interval",
                interval=300_000,   # 5 dakika (ms)
                n_intervals=0,
            ),
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


# ── Callback: Sparkline Güncelleme ───────────────────────────────────────────

@callback(
    Output("spark-cpu",          "figure"),
    Output("spark-ram",          "figure"),
    Output("spark-energy",       "figure"),
    Output("spark-cpu-value",    "children"),
    Output("spark-ram-value",    "children"),
    Output("spark-energy-value", "children"),
    Input("overview-trends-interval", "n_intervals"),
    prevent_initial_call=False,  # İlk yükleme anında da tetiklenir
)
def _refresh_sparklines(n_intervals):
    """
    GET /overview/trends → 3 Sparkline figür + anlık değer metni günceller.

    Hata veya boş Redis durumunda no_update dönerek mevcut durumu korur
    (boş figür başlangıçta zaten render edilmiş olur).
    """
    try:
        data = get_overview_trends()

        cpu    = data.get("cpu_pct",   {})
        ram    = data.get("ram_pct",   {})
        energy = data.get("energy_kw", {})

        fig_cpu    = _sparkline_fig(cpu.get("labels",    []), cpu.get("values",    []), _INDIGO)
        fig_ram    = _sparkline_fig(ram.get("labels",    []), ram.get("values",    []), _VIOLET)
        fig_energy = _sparkline_fig(energy.get("labels", []), energy.get("values", []), _SKY)

        # Anlık değer: son eleman (listenin son elemanı = en yeni ölçüm)
        cpu_val    = f"{cpu['values'][-1]:.1f}%"    if cpu.get("values")    else "—"
        ram_val    = f"{ram['values'][-1]:.1f}%"    if ram.get("values")    else "—"
        energy_val = f"{energy['values'][-1]:.1f} kW" if energy.get("values") else "—"

        return fig_cpu, fig_ram, fig_energy, cpu_val, ram_val, energy_val

    except Exception:  # noqa: BLE001
        # API çökmüş veya Redis henüz dolu değil — mevcut görseli koru
        return no_update, no_update, no_update, no_update, no_update, no_update
