"""
Shared detail page header component.

Kullanım:
    from src.components.header import create_detail_header

    header = create_detail_header(
        title="DC11",
        back_href="/datacenters",
        back_label="Data Centers",
        subtitle_badge="📍 Istanbul",
        subtitle_color="indigo",
        time_range=tr,
        tabs=dmc.TabsList(...),   # opsiyonel — None bırakılabilir
    )
"""
from dash import html, dcc
import dash_mantine_components as dmc
from dash_iconify import DashIconify


def create_detail_header(
    title,
    back_href,
    back_label="Back",
    subtitle_badge=None,
    subtitle_color="indigo",
    time_range=None,
    icon="solar:server-square-bold-duotone",
    tabs=None,
    right_extra=None,
):
    """
    Evrensel Executive Detail Header — glassmorphism + sticky + sekmeler.

    Args:
        title:          Sayfa başlığı (örn: "DC11", "Cluster: C01", "Customer View")
        back_href:      Back butonu linki (örn: "/datacenters")
        back_label:     Back butonu tooltip metni
        subtitle_badge: Region/lokasyon/bağlam badge metni (örn: "📍 Istanbul")
                        None ise badge gösterilmez.
        subtitle_color: Badge rengi (Mantine renk adı — varsayılan "indigo")
        time_range:     {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"} veya None
        icon:           Başlık solundaki ikon (DashIconify icon adı)
        tabs:           dmc.TabsList veya dmc.Tabs bileşeni — varsa header içine entegre edilir.
                        None ise sekme alanı gösterilmez.

    Returns:
        dmc.Paper: Glassmorphism + sticky konteynır
    """
    tr = time_range or {}
    start = tr.get("start", "")
    end   = tr.get("end", "")

    # ── Back Butonu ─────────────────────────────────────────────────────
    back_button = dcc.Link(
        dmc.Tooltip(
            label=f"Back to {back_label}",
            children=dmc.ActionIcon(
                DashIconify(icon="solar:arrow-left-linear", width=20),
                variant="light",
                color="indigo",
                size="lg",
                radius="md",
            ),
        ),
        href=back_href,
        style={"textDecoration": "none"},
    )

    # ── Başlık Satırı (İkon + Gradyan H2 + Region Badge) ────────────────
    title_children = [
        DashIconify(icon=icon, width=22, color="#4318FF"),
        html.H2(
            title,
            style={
                "margin": 0,
                "fontWeight": 900,
                "letterSpacing": "-0.02em",
                "lineHeight": 1.2,
                "fontSize": "1.6rem",
                "background": "linear-gradient(90deg, #1a1b41 0%, #4318FF 100%)",
                "WebkitBackgroundClip": "text",
                "WebkitTextFillColor": "transparent",
                "backgroundClip": "text",
            },
        ),
    ]

    # Region/Bağlam Badge (opsiyonel)
    if subtitle_badge:
        title_children.append(
            dmc.Badge(
                subtitle_badge,
                variant="light",
                color=subtitle_color,
                radius="xl",
                size="sm",
                style={
                    "textTransform": "none",
                    "fontWeight": 500,
                    "letterSpacing": 0,
                    "alignSelf": "center",
                },
            )
        )

    # ── Tarih Rozeti (sağ taraf) ─────────────────────────────────────────
    date_badge_children = []
    if start and end:
        date_badge_children = [
            dmc.Badge(
                children=dmc.Group(
                    gap=6,
                    align="center",
                    children=[
                        DashIconify(icon="solar:calendar-mark-bold-duotone", width=13),
                        f"{start} – {end}",
                    ],
                ),
                variant="light",
                color="indigo",
                radius="xl",
                size="md",
                style={"textTransform": "none", "fontWeight": 500, "letterSpacing": 0},
            )
        ]

    date_row = dmc.Group(gap="sm", justify="flex-end", children=list(date_badge_children))
    if right_extra:
        right_block = dmc.Stack(
            gap=6,
            align="flex-end",
            children=[date_row, *list(right_extra)],
        )
    else:
        right_block = date_row

    # ── Üst Katman: Back | İkon+Başlık+Badge | Tarih(+extras) ───────────
    top_layer = dmc.Group(
        justify="space-between",
        align="center",
        mb="md" if tabs is not None else 0,
        children=[
            # SOL: Back butonu + Başlık grubu
            dmc.Group(
                gap="md",
                align="center",
                children=[
                    back_button,
                    dmc.Group(
                        gap="sm",
                        align="center",
                        children=title_children,
                    ),
                ],
            ),
            # SAĞ: Tarih rozeti (üst) + opsiyonel ekstra satırlar
            right_block,
        ],
    )

    # ── Ortak dmc.Paper kapsayıcı (Sticky) ──────────────────────────────
    paper_children = [top_layer]
    if tabs is not None:
        paper_children.append(tabs)

    return dmc.Paper(
        px="xl",
        py="md",
        radius=0,
        style={
            "background": "rgba(255, 255, 255, 0.88)",
            "backdropFilter": "blur(14px)",
            "WebkitBackdropFilter": "blur(14px)",
            "boxShadow": "0 4px 24px rgba(67, 24, 255, 0.08), 0 1px 6px rgba(0, 0, 0, 0.05)",
            "borderBottom": "1px solid rgba(67, 24, 255, 0.08)",
            "position": "sticky",
            "top": 0,
            "zIndex": 1000,
            "marginBottom": "24px",
        },
        children=paper_children,
    )
