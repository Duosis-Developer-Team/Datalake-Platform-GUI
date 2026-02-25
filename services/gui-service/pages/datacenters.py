import dash
import dash_mantine_components as dmc
from dash import callback, dcc, Output, Input
from dash_iconify import DashIconify

from services.api_client import get_summary

dash.register_page(__name__, path="/datacenters", name="Data Centers")

_STATUS_COLOR = {"Healthy": "green", "Degraded": "orange", "Unreachable": "red"}

_INTERVAL_MS = 900_000  # 15 dakika


def _ring_color(pct: float) -> str:
    if pct < 60:
        return "teal"
    if pct < 80:
        return "yellow"
    return "red"


def _stat_boxes(data: list) -> dmc.SimpleGrid:
    total_clusters = sum(dc.get("cluster_count", 0) for dc in data)
    total_hosts    = sum(dc.get("host_count", 0)    for dc in data)
    total_vms      = sum(dc.get("vm_count", 0)      for dc in data)
    healthy        = sum(1 for dc in data if dc.get("status") == "Healthy")
    total          = len(data)
    health_color   = "green" if (healthy / total if total else 0) >= 0.8 else "orange"

    items = [
        ("mdi:lan",             "Toplam Cluster", str(total_clusters), "indigo"),
        ("mdi:server",          "Toplam Host",    str(total_hosts),    "blue"),
        ("mdi:desktop-classic", "Toplam VM",      str(total_vms),      "violet"),
        ("mdi:heart-pulse",     "Sistem Sağlığı", f"{healthy}/{total} Healthy", health_color),
    ]

    boxes = [
        dmc.Paper(
            dmc.Group(
                [
                    dmc.ThemeIcon(
                        DashIconify(icon=icon, width=22),
                        color=color,
                        variant="light",
                        size="xl",
                        radius="md",
                    ),
                    dmc.Stack(
                        [
                            dmc.Text(value, fw=800, size="xl"),
                            dmc.Text(label, c="dimmed", size="xs"),
                        ],
                        gap=2,
                    ),
                ],
                gap="md",
                align="center",
            ),
            className="stat-box",
            p="xl",
            radius="xl",
            withBorder=False,
        )
        for icon, label, value, color in items
    ]

    return dmc.SimpleGrid(
        boxes,
        cols={"base": 2, "sm": 4},
        spacing="md",
        mb="xl",
    )


def _card(dc: dict) -> dmc.Card:
    color = _STATUS_COLOR.get(dc.get("status", ""), "gray")
    stats = dc.get("stats", {})
    cpu   = float(stats.get("used_cpu_pct", 0))
    ram   = float(stats.get("used_ram_pct", 0))
    stor  = float(stats.get("used_storage_pct", 0))
    avg   = round((cpu + ram + stor) / 3) if any([cpu, ram, stor]) else 0
    rcolor = _ring_color(avg)

    return dmc.Card(
        [
            # ── Başlık ────────────────────────────────────────────
            dmc.Group(
                [
                    dmc.Stack(
                        [
                            dmc.Text(dc["id"], fw=800, size="lg"),
                            dmc.Text(dc.get("location", ""), c="dimmed", size="xs"),
                        ],
                        gap=2,
                    ),
                    dmc.Badge(dc.get("status", "—"), color=color, variant="light", size="sm"),
                ],
                justify="space-between",
                align="flex-start",
                mb="md",
            ),
            # ── Metrikler (sol) + Ring (sağ) ─────────────────────
            dmc.Group(
                [
                    dmc.Stack(
                        [
                            dmc.Group(
                                [
                                    DashIconify(icon="mdi:lan", width=15, color="#4c6ef5"),
                                    dmc.Text(f"Clusters: {dc['cluster_count']}", size="sm", c="#495057"),
                                ],
                                gap="xs",
                            ),
                            dmc.Group(
                                [
                                    DashIconify(icon="mdi:server", width=15, color="#4c6ef5"),
                                    dmc.Text(f"Hosts: {dc['host_count']}", size="sm", c="#495057"),
                                ],
                                gap="xs",
                            ),
                            dmc.Group(
                                [
                                    DashIconify(icon="mdi:desktop-classic", width=15, color="#4c6ef5"),
                                    dmc.Text(f"VMs: {dc['vm_count']}", size="sm", c="#495057"),
                                ],
                                gap="xs",
                            ),
                        ],
                        gap="sm",
                        style={"flex": "1"},
                    ),
                    dmc.Box(
                        dmc.RingProgress(
                            sections=[{"value": avg, "color": rcolor}],
                            label=dmc.Stack(
                                [
                                    dmc.Text(f"{avg}%", ta="center", fw=800, size="sm"),
                                    dmc.Text("avg", ta="center", c="dimmed", size="xs"),
                                ],
                                gap=0,
                                align="center",
                            ),
                            size=88,
                            thickness=7,
                            roundCaps=True,
                        ),
                        className="ring-progress",
                    ),
                ],
                align="center",
                gap="md",
                mb="md",
            ),
            # ── Ayırıcı + Detay butonu ────────────────────────────
            dmc.Divider(color="rgba(76,110,245,0.08)", mb="md"),
            dmc.Group(
                dmc.Anchor(
                    dmc.Button(
                        "Detaylar",
                        variant="light",
                        color="indigo",
                        size="sm",
                        radius="xl",
                        rightSection=DashIconify(icon="mdi:arrow-right", width=14),
                    ),
                    href=f"/datacenters/{dc['id']}",
                ),
                justify="flex-end",
            ),
        ],
        withBorder=False,
        shadow="sm",
        radius="xl",
        className="dc-card",
        p="xl",
    )


def _render_content(data: list) -> list:
    """Veri listesinden stat kutuları + kart grid'ini döndür."""
    return [
        _stat_boxes(data),
        dmc.SimpleGrid(
            [_card(dc) for dc in data],
            cols={"base": 1, "sm": 2, "lg": 3},
            spacing="md",
        ),
    ]


# ── Auto-Refresh Callback ───────────────────────────────────────────────────

@callback(
    Output("dc-list-content", "children"),
    Input("dc-list-interval", "n_intervals"),
    prevent_initial_call=True,
)
def _refresh_dc_list(n):
    """15 dakikada bir API'den taze veri çek, kartları sessizce güncelle."""
    try:
        data = get_summary()
        return _render_content(data)
    except Exception as exc:
        return [
            dmc.Alert(
                str(exc),
                title="Veri Yüklenemedi",
                color="red",
                icon=DashIconify(icon="mdi:alert-circle-outline"),
            )
        ]


# ── Page Layout ─────────────────────────────────────────────────────────────

def layout(**kwargs):
    try:
        data = get_summary()
        initial_content = _render_content(data)
    except Exception as exc:
        initial_content = [
            dmc.Alert(
                str(exc),
                title="Veri Yüklenemedi",
                color="red",
                icon=DashIconify(icon="mdi:alert-circle-outline"),
            )
        ]

    return dmc.Container(
        [
            dmc.Title("Veri Merkezleri", order=2, fw=800, mb="lg"),
            dcc.Interval(id="dc-list-interval", interval=_INTERVAL_MS, n_intervals=0),
            dmc.Box(id="dc-list-content", children=initial_content),
        ],
        pt="xl",
        fluid=True,
    )
