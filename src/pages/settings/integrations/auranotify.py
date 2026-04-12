"""AuraNotify SLA integration status (environment + live API sample)."""

from __future__ import annotations

import os
from datetime import date, datetime, timezone

import dash_mantine_components as dmc
from dash import html

from src.services import auranotify_client
from src.utils.ui_tokens import ON_SURFACE, section_header, settings_page_shell


def _mask(s: str | None, n: int = 6) -> str:
    if not s:
        return "—"
    if len(s) <= n:
        return "•" * len(s)
    return "•" * 12 + s[-n:]


def build_layout(search: str | None = None) -> html.Div:
    base = (os.environ.get("AURANOTIFY_BASE_URL") or "").strip() or auranotify_client.AURANOTIFY_BASE
    key = (os.environ.get("AURANOTIFY_API_KEY") or os.environ.get("ANOTIFY_API_KEY") or "").strip()

    configured = bool(base and key)
    banner = dmc.Alert(
        "AuraNotify base URL and API key are configured — live calls enabled."
        if configured
        else "Set AURANOTIFY_BASE_URL and AURANOTIFY_API_KEY (or ANOTIFY_API_KEY) to enable SLA API access.",
        color="green" if configured else "orange",
        variant="light",
        mb="md",
    )

    start = date.today().isoformat()
    rows = []
    error_msg = None
    if configured:
        try:
            items = auranotify_client.get_dc_services_availability(start)
        except Exception as exc:
            items = []
            error_msg = str(exc)
        if not items and not error_msg:
            error_msg = "Empty response from AuraNotify (check API key and service availability)."
        for it in (items or [])[:25]:
            gname = str(it.get("group_name") or it.get("name") or "—")
            sla = it.get("sla_percentage")
            if sla is None:
                sla = it.get("availability_percentage") or it.get("availability")
            status = str(it.get("status") or ("ok" if sla is not None else "—"))
            rows.append(
                html.Tr(
                    style={"borderBottom": "1px solid #eef1f4"},
                    children=[
                        html.Td(gname[:80], style={"fontSize": "13px"}),
                        html.Td(str(sla if sla is not None else "—")),
                        html.Td(status[:40]),
                    ],
                )
            )
    else:
        error_msg = "Configure environment variables to load live SLA data."

    err_alert = (
        dmc.Alert(error_msg, color="red", variant="light", mb="md") if error_msg and not rows else None
    )

    table = dmc.Paper(
        p=0,
        radius="md",
        withBorder=True,
        children=[
            html.Div(
                style={"padding": "16px 20px", "borderBottom": "1px solid #eef1f4"},
                children=[
                    dmc.Group(
                        justify="space-between",
                        children=[
                            dmc.Text("Datacenter services (sample)", fw=700, c=ON_SURFACE),
                            dmc.Text(f"start_date={start}", size="xs", c="dimmed"),
                        ],
                    )
                ],
            ),
            html.Div(
                style={"overflowX": "auto"},
                children=[
                    html.Table(
                        [
                            html.Tr(
                                [
                                    html.Th("Group / service", style=_th()),
                                    html.Th("SLA / metric", style=_th()),
                                    html.Th("Status", style=_th()),
                                ]
                            ),
                            *rows,
                        ],
                        style={"width": "100%", "fontSize": "13px", "padding": "0 16px 16px"},
                    )
                ],
            ),
        ],
    )

    config_card = dmc.Paper(
        p="lg",
        radius="md",
        withBorder=True,
        mb="md",
        children=[
            dmc.Text("Configuration (read-only)", fw=700, mb="sm", c=ON_SURFACE),
            dmc.Text(
                "Values are loaded from process environment at runtime (set in container / systemd / .env).",
                size="sm",
                c="dimmed",
                mb="md",
            ),
            dmc.Stack(
                gap="xs",
                children=[
                    dmc.Group(
                        children=[
                            dmc.Text("Base URL", size="sm", fw=600, w=140),
                            dmc.Code(base or "—", style={"fontSize": "12px"}),
                        ]
                    ),
                    dmc.Group(
                        children=[
                            dmc.Text("API key", size="sm", fw=600, w=140),
                            dmc.Code(_mask(key), style={"fontSize": "12px"}),
                        ]
                    ),
                    dmc.Group(
                        children=[
                            dmc.Text("Checked at", size="sm", fw=600, w=140),
                            dmc.Text(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"), size="sm"),
                        ]
                    ),
                ],
            ),
        ],
    )

    return html.Div(
        settings_page_shell(
            [
                section_header(
                    "AuraNotify",
                    "External SLA and availability APIs used by dashboards.",
                    icon="solar:graph-new-up-bold-duotone",
                ),
                banner,
                config_card,
                err_alert if err_alert else html.Div(),
                table,
                dmc.Text(
                    "Tip: refresh the page to re-fetch SLA snapshot.",
                    size="xs",
                    c="dimmed",
                    mt="sm",
                ),
            ]
        )
    )


def _th():
    return {"textAlign": "left", "padding": "8px 12px", "borderBottom": "1px solid #e9ecef", "color": "#2B3674", "fontSize": "11px", "textTransform": "uppercase"}
