from datetime import datetime, timezone

import dash_mantine_components as dmc
from dash_iconify import DashIconify
from dash import html, dcc

from src.services import api_client as api
from src.utils.time_range import default_time_range


def _format_last_observed(ts_str):
    if not ts_str:
        return "—"
    try:
        ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = now - ts
        if diff.days > 30:
            return f"{diff.days // 30}mo ago"
        if diff.days > 0:
            return f"{diff.days}d ago"
        hours = diff.seconds // 3600
        if hours > 0:
            return f"{hours}h ago"
        return "Just now"
    except Exception:
        return str(ts_str)[:16]


def _kpi_card(title, value, icon, color):
    return dmc.Paper(
        p="lg",
        radius="md",
        style={
            "background": "rgba(255,255,255,0.95)",
            "border": "1px solid rgba(67,24,255,0.06)",
            "boxShadow": "0 2px 8px rgba(67,24,255,0.04)",
        },
        children=[
            dmc.Group(justify="space-between", align="center", children=[
                dmc.Stack(gap=4, children=[
                    dmc.Text(title, size="xs", fw=600, c="#A3AED0"),
                    dmc.Text(value, size="xl", fw=800, c="#2B3674"),
                ]),
                dmc.ThemeIcon(
                    size="lg",
                    radius="md",
                    variant="light",
                    color=color,
                    children=DashIconify(icon=icon, width=20),
                ),
            ]),
        ],
    )


def _rack_card(rack):
    name = rack.get("name") or "Unknown"
    status = (rack.get("status") or "").lower()
    u_height = rack.get("u_height") or 0
    kabin_enerji = rack.get("kabin_enerji") or ""
    pdu_a = rack.get("pdu_a_ip") or ""
    pdu_b = rack.get("pdu_b_ip") or ""
    tenant = rack.get("tenant_name") or ""
    last_obs = rack.get("last_observed") or ""

    status_map = {
        "active": ("teal", "● Active"),
        "planned": ("blue", "○ Planned"),
        "reserved": ("orange", "◐ Reserved"),
    }
    s_color, s_label = status_map.get(status, ("gray", "— " + status.title() if status else "Unknown"))

    if pdu_a and pdu_b:
        pdu_text = f"A: {pdu_a} · B: {pdu_b}"
    elif pdu_a:
        pdu_text = f"A: {pdu_a}"
    elif pdu_b:
        pdu_text = f"B: {pdu_b}"
    else:
        pdu_text = "—"

    return dmc.Paper(
        p="lg",
        radius="md",
        className="rack-card",
        style={
            "background": "rgba(255,255,255,0.95)",
            "border": "1px solid rgba(67,24,255,0.08)",
            "boxShadow": "0 2px 12px rgba(67,24,255,0.06)",
        },
        children=[
            dmc.Group(justify="space-between", mb="sm", children=[
                dmc.Text(name, fw=700, size="md", c="#2B3674"),
                dmc.Badge(s_label, color=s_color, variant="light", size="sm"),
            ]),

            dmc.Group(gap="lg", mb="sm", children=[
                dmc.Group(gap="xs", children=[
                    DashIconify(icon="solar:ruler-bold-duotone", width=14, color="#A3AED0"),
                    dmc.Text(f"{u_height}U", size="sm", fw=600, c="#2B3674"),
                ]),
                dmc.Group(gap="xs", children=[
                    DashIconify(icon="solar:bolt-circle-bold-duotone", width=14, color="#A3AED0"),
                    dmc.Text(kabin_enerji or "—", size="sm", fw=500, c="#2B3674"),
                ]),
            ]),

            dmc.Divider(my="xs", color="rgba(67,24,255,0.06)"),

            dmc.Stack(gap=4, children=[
                dmc.Group(gap="xs", children=[
                    DashIconify(icon="solar:plug-circle-bold-duotone", width=12, color="#A3AED0"),
                    dmc.Text(f"PDU: {pdu_text}", size="xs", c="#A3AED0", truncate=True),
                ]),
                dmc.Group(gap="xs", children=[
                    DashIconify(icon="solar:user-bold-duotone", width=12, color="#A3AED0"),
                    dmc.Text(f"Tenant: {tenant or '—'}", size="xs", c="#A3AED0"),
                ]),
                dmc.Group(gap="xs", children=[
                    DashIconify(icon="solar:clock-circle-bold-duotone", width=12, color="#A3AED0"),
                    dmc.Text(f"Last seen: {_format_last_observed(last_obs)}", size="xs", c="#A3AED0"),
                ]),
            ]),
        ],
    )


def build_dc_detail(dc_id, time_range=None):
    tr = time_range or default_time_range()

    racks_data = api.get_dc_racks(dc_id)
    racks = racks_data.get("racks", [])
    _summary_raw = racks_data.get("summary") or {}
    summary = {
        "total_racks": _summary_raw.get("total_racks", 0),
        "active_racks": _summary_raw.get("active_racks", 0),
        "total_u_height": _summary_raw.get("total_u_height", 0),
        "racks_with_energy": _summary_raw.get("racks_with_energy", 0),
        "racks_with_pdu": _summary_raw.get("racks_with_pdu", 0),
    }

    dc_details = api.get_dc_details(dc_id, tr)
    dc_name = dc_details.get("meta", {}).get("name", dc_id)
    dc_location = dc_details.get("meta", {}).get("location", "")

    header = dmc.Paper(
        p="xl",
        radius="lg",
        style={
            "background": "rgba(255,255,255,0.90)",
            "backdropFilter": "blur(14px)",
            "boxShadow": "0 8px 32px rgba(67,24,255,0.10)",
            "border": "1px solid rgba(67,24,255,0.08)",
            "marginBottom": "24px",
        },
        children=[
            dmc.Group(
                justify="space-between",
                align="center",
                children=[
                    dmc.Group(gap="md", align="center", children=[
                        dcc.Link(
                            dmc.ActionIcon(
                                DashIconify(icon="solar:arrow-left-bold-duotone", width=20),
                                variant="light",
                                color="indigo",
                                radius="md",
                                size="lg",
                            ),
                            href="/global-view",
                            style={"textDecoration": "none"},
                        ),
                        dmc.ThemeIcon(
                            size="xl",
                            radius="md",
                            variant="light",
                            color="indigo",
                            children=DashIconify(icon="solar:server-square-bold-duotone", width=24),
                        ),
                        dmc.Stack(gap=0, children=[
                            dmc.Text(dc_name, fw=800, size="xl", c="#2B3674"),
                            dmc.Text(dc_location, size="sm", c="#A3AED0", fw=500),
                        ]),
                    ]),
                    dmc.Badge(
                        f"{summary['total_racks']} Cabinets",
                        variant="light",
                        color="indigo",
                        size="lg",
                    ),
                ],
            ),
        ],
    )

    kpi_row = dmc.SimpleGrid(
        cols=4,
        spacing="lg",
        style={"marginBottom": "24px"},
        children=[
            _kpi_card("Total Racks", str(summary["total_racks"]), "solar:server-square-bold-duotone", "indigo"),
            _kpi_card("Active Racks", str(summary["active_racks"]), "solar:check-circle-bold-duotone", "teal"),
            _kpi_card("Total U Height", f"{summary['total_u_height']}U", "solar:ruler-bold-duotone", "orange"),
            _kpi_card("PDU Connected", str(summary["racks_with_pdu"]), "solar:bolt-circle-bold-duotone", "grape"),
        ],
    )

    if racks:
        grouped = {}
        for r in racks:
            h = r.get("hall_name") or "Main Hall"
            grouped.setdefault(h, []).append(r)

        hall_sections = []
        for hall, hall_racks in grouped.items():
            hall_sections.append(
                html.Div(
                    style={"marginBottom": "32px"},
                    children=[
                        dmc.Group(gap="xs", mb="md", align="center", children=[
                            DashIconify(icon="solar:server-square-bold-duotone", width=18, color="#4318FF"),
                            dmc.Text(hall, fw=700, size="md", c="#2B3674"),
                            dmc.Badge(f"{len(hall_racks)}", variant="light", color="indigo", size="sm"),
                        ]),
                        dmc.SimpleGrid(
                            cols={"base": 1, "sm": 2, "lg": 3},
                            spacing="lg",
                            children=[_rack_card(r) for r in hall_racks],
                        ),
                    ],
                )
            )
        rack_grid = html.Div(hall_sections)
    else:
        rack_grid = dmc.Paper(
            p="xl",
            radius="lg",
            style={"textAlign": "center", "marginTop": "32px"},
            children=[
                DashIconify(icon="solar:server-square-bold-duotone", width=64, color="#A3AED0"),
                html.H3("No Cabinets Found", style={"color": "#2B3674", "marginTop": "16px"}),
                dmc.Text(
                    f"No rack data available for {dc_id}. The discovery collector may not have synced yet.",
                    c="#A3AED0",
                    size="sm",
                ),
                dcc.Link(
                    dmc.Button("Back to Global View", variant="light", color="indigo", radius="md", mt="lg"),
                    href="/global-view",
                    style={"textDecoration": "none"},
                ),
            ],
        )

    return html.Div(
        className="dc-detail-animate",
        style={"padding": "24px"},
        children=[header, kpi_row, rack_grid],
    )
