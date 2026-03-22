import dash
from dash import html, dcc
import dash_mantine_components as dmc
from dash_iconify import DashIconify
from src.services import api_client as api
from src.services import sla_service
from src.utils.time_range import default_time_range


def _dc_vault_card(dc, sla_entry=None):
    """Elite DC Vault kart─▒ ÔÇö 2 s├╝tunlu, Power Dial + Metrik Sat─▒rlar─▒."""
    # ÔöÇÔöÇ G├╝├ğ verisi ÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇ
    ibm_kw   = float(dc["stats"].get("ibm_kw", 0.0) or 0.0)
    total_kw = float(dc["stats"].get("total_energy_kw", 0.0) or 0.0)
    power_ratio = round((ibm_kw / total_kw * 100) if total_kw > 0 else 0.0, 1)
    remaining   = max(0.0, 100.0 - power_ratio)

    # ÔöÇÔöÇ Renk-ikon Metrik Tan─▒mlar─▒ ÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇ
    metrics = [
        {
            "icon": "solar:layers-minimalistic-bold-duotone",
            "color": "blue",
            "label": "Platforms",
            "value": dc.get("platform_count", 0),
        },
        {
            "icon": "solar:box-bold-duotone",
            "color": "grape",
            "label": "Clusters",
            "value": dc.get("cluster_count", 0),
        },
        {
            "icon": "solar:server-bold-duotone",
            "color": "orange",
            "label": "Hosts",
            "value": f"{dc.get('host_count', 0):,}",
        },
        {
            "icon": "solar:laptop-bold-duotone",
            "color": "teal",
            "label": "VMs",
            "value": f"{dc.get('vm_count', 0):,}",
        },
    ]

    metric_rows = [
        dmc.Group(
            justify="space-between",
            align="center",
            children=[
                dmc.Group(
                    gap="xs",
                    align="center",
                    children=[
                        dmc.ThemeIcon(
                            size="sm",
                            variant="light",
                            color=m["color"],
                            radius="md",
                            children=DashIconify(icon=m["icon"], width=14),
                        ),
                        dmc.Text(m["label"], size="sm", c="#A3AED0"),
                    ],
                ),
                dmc.Text(
                    str(m["value"]),
                    fw=700,
                    size="sm",
                    c="#2B3674",
                    style={"fontVariantNumeric": "tabular-nums"},
                ),
            ],
        )
        for m in metrics
    ]

    # ÔöÇÔöÇ Power Dial (dmc.RingProgress) ÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇ
    power_dial = dmc.Stack(
        gap=6,
        align="center",
        children=[
            dmc.RingProgress(
                size=110,
                thickness=10,
                roundCaps=True,
                sections=[
                    {"value": power_ratio, "color": "orange"},
                    {"value": remaining,   "color": "#4318FF"},
                ],
                label=html.Div(
                    style={"textAlign": "center"},
                    children=[
                        dmc.Text(
                            f"{power_ratio:.0f}%",
                            fw=900,
                            size="lg",
                            c="#2B3674",
                            style={"lineHeight": 1},
                        ),
                        dmc.Text(
                            "IBM",
                            size="xs",
                            c="dimmed",
                            style={"lineHeight": 1, "marginTop": "2px"},
                        ),
                    ],
                ),
            ),
            dmc.Text("Power", size="xs", fw=600, c="#A3AED0"),
            dmc.Text(
                f"{total_kw:.1f} kW total",
                size="xs",
                c="dimmed",
                style={"fontVariantNumeric": "tabular-nums"},
            ),
        ],
    )

    # ÔöÇÔöÇ Dikey Frosted Divider (Sol/Sa─ş aras─▒nda) ÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇ
    frosty_divider = html.Div(
        style={
            "width": "1px",
            "height": "80%",
            "background": "linear-gradient(to bottom, transparent, rgba(67,24,255,0.12), transparent)",
            "alignSelf": "center",
        }
    )

    return dmc.Paper(
        className="dc-vault-card",
        p="lg",
        radius="lg",
        style={
            "background": "rgba(255, 255, 255, 0.82)",
            "backdropFilter": "blur(12px)",
            "WebkitBackdropFilter": "blur(12px)",
            "boxShadow": "0 2px 16px rgba(67, 24, 255, 0.06), 0 1px 4px rgba(0,0,0,0.04)",
            "border": "1px solid rgba(255, 255, 255, 0.7)",
            "height": "100%",
            "display": "flex",
            "flexDirection": "column",
            "gap": "14px",
        },
        children=[
            # ÔöÇÔöÇ Kart Ba┼şl─▒─ş─▒: ─░sim + Pulse Dot + Details Badge ÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇ
            dmc.Group(
                justify="space-between",
                align="flex-start",
                children=[
                    dmc.Group(
                        gap="xs",
                        align="center",
                        children=[
                            # Live Pulse Dot
                            dmc.Tooltip(
                                label=sla_service.format_availability_tooltip(sla_entry),
                                position="top",
                                withArrow=True,
                                children=html.Div(className="dc-pulse-dot"),
                            ),
                            dmc.Stack(
                                gap=0,
                                children=[
                                    dmc.Text(dc["name"], fw=700, size="md", c="#2B3674"),
                                    dmc.Text(
                                        dc.get("location", "ÔÇö"),
                                        size="xs",
                                        c="#A3AED0",
                                        fw=500,
                                    ),
                                ],
                            ),
                        ],
                    ),
                    dcc.Link(
                        dmc.Badge(
                            "Details ÔåÆ",
                            variant="light",
                            color="indigo",
                            size="sm",
                            radius="xl",
                            style={"cursor": "pointer", "textDecoration": "none"},
                        ),
                        href=f"/datacenter/{dc['id']}",
                        style={"textDecoration": "none"},
                    ),
                ],
            ),

            # ÔöÇÔöÇ Ana 2-S├╝tunlu ─░├ğerik ÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇ
            html.Div(
                style={
                    "display": "flex",
                    "flexDirection": "row",
                    "alignItems": "stretch",
                    "gap": "16px",
                    "flex": 1,
                },
                children=[
                    # Sol: Metrik sat─▒rlar─▒
                    dmc.Stack(
                        gap="xs",
                        style={"flex": 1},
                        children=metric_rows,
                    ),
                    # Ortada: Frosted Divider
                    frosty_divider,
                    # Sa─ş: Power Dial
                    html.Div(
                        style={"display": "flex", "alignItems": "center", "justifyContent": "center"},
                        children=[power_dial],
                    ),
                ],
            ),
        ],
    )


def build_datacenters(time_range=None):
    """Build Data Centers page content for the given time range."""
    tr = time_range or default_time_range()
    datacenters = api.get_all_datacenters_summary(tr)
    sla_by_dc = api.get_sla_by_dc(tr)
    return html.Div([
        # Header
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
                        # ---- SOL TARAF: Ba┼şl─▒k + Tarih Rozeti ----
                        dmc.Stack(
                            gap=10,
                            children=[
                                # Ba┼şl─▒k sat─▒r─▒: ─░kon + Gradyan H2
                                dmc.Group(
                                    gap="sm",
                                    align="center",
                                    children=[
                                        DashIconify(
                                            icon="solar:server-square-bold-duotone",
                                            width=28,
                                            color="#4318FF",
                                        ),
                                        html.H2(
                                            "Data Centers",
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
                                # Tarih rozeti ÔÇö Overview ile ayn─▒ pattern
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
                                                f"{tr.get('start', '')} ÔÇô {tr.get('end', '')}",
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
                        # ---- SA─Ş TARAF: Aktif DC Sayac─▒ Badge ----
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
                                        f"{len(datacenters)} Active DCs",
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

        # Elite DC Vault Grid
        dmc.SimpleGrid(
            cols=3,
            spacing="lg",
            style={"padding": "0 32px"},
            children=[
                _dc_vault_card(dc, sla_by_dc.get(dc.get("id"))) for dc in datacenters
            ],
        ),
    ])


def layout():
    return build_datacenters(default_time_range())
