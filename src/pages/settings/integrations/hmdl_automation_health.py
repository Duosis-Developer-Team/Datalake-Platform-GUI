"""Integrations — HMDL Automation Health (schedule / freshness monitoring).

Surfaces *when each HMDL automation last ran* and whether it is on schedule, so a
stalled schedule (collector sync, reachability checks, VM reconciliation) is visible
within hours instead of going unnoticed for weeks. Read-only; data from hmdl-api
`/collectors/automation-health`.
"""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import html

from src.services import api_client as api
from src.utils.hmdl_sync_ui import automation_status_badge, relative_age
from src.utils.ui_tokens import kpi_card, section_header, settings_page_shell


def _fmt_ts(value) -> str:
    if not value:
        return "—"
    s = str(value)
    return s.replace("T", " ")[:16]


def _automation_card(a: dict) -> dmc.Paper:
    status = str(a.get("status") or "unknown")
    extra = a.get("extra") or {}
    meta_lines = [
        dmc.Text(f"Son çalışma: {_fmt_ts(a.get('last_run_at'))}", size="xs", c="dimmed"),
        dmc.Text(f"Beklenen: {a.get('cadence') or '—'}", size="xs", c="dimmed"),
    ]
    if extra.get("proxy_coverage"):
        covered = int(extra.get("last_run_proxies") or 0)
        total = int(extra.get("total_proxies") or 0)
        low = total and covered < total
        meta_lines.append(
            dmc.Text(
                f"Proxy kapsamı: {extra['proxy_coverage']}",
                size="xs",
                c="red" if low else "dimmed",
                fw=700 if low else 400,
            )
        )
    return dmc.Paper(
        p="md",
        withBorder=True,
        radius="md",
        children=[
            dmc.Group(
                justify="space-between",
                align="flex-start",
                mb="xs",
                children=[
                    dmc.Text(a.get("label") or a.get("key") or "—", fw=700, size="sm"),
                    automation_status_badge(status),
                ],
            ),
            dmc.Text(relative_age(a.get("age_hours")), fw=900, size="lg"),
            dmc.Stack(gap=2, mt="xs", children=meta_lines),
        ],
    )


# Match the Turkish labels used on the freshness cards (Taze/Bayat/Ölü), so the
# proxy table doesn't show raw English statuses alongside them.
_STATUS_TR = {"fresh": "Taze", "stale": "Bayat", "dead": "Ölü", "unknown": "Bilinmiyor"}


def _proxy_row(p: dict) -> html.Tr:
    status = str(p.get("status") or "unknown")
    color = {"fresh": "green", "stale": "orange", "dead": "red"}.get(status, "gray")
    return html.Tr(
        children=[
            html.Td(str(p.get("proxy_id") or "")),
            html.Td(str(p.get("dc_code") or "—")),
            html.Td(str(p.get("proxy_nifi_host") or "—")),
            html.Td(relative_age(p.get("age_hours"))),
            html.Td(dmc.Badge(_STATUS_TR.get(status, status.title()), color=color, variant="light", size="xs")),
        ]
    )


def build_layout(search: str | None = None) -> html.Div:
    data = api.get_hmdl_automation_health()
    automations = data.get("automations") or []
    counts = data.get("counts") or {}
    proxies = data.get("proxies") or []
    psum = data.get("proxy_summary") or {}
    gaps = data.get("data_gaps") or {}

    alert = int(counts.get("alert") or 0)

    kpis = dmc.SimpleGrid(
        cols={"base": 2, "md": 4},
        spacing="md",
        mb="lg",
        children=[
            kpi_card("Uyarı (bayat+ölü)", str(alert), icon="solar:bell-bing-bold-duotone",
                     color="red" if alert else "green"),
            kpi_card("Taze", str(counts.get("fresh") or 0), icon="solar:check-circle-bold-duotone", color="green"),
            kpi_card("Bayat", str(counts.get("stale") or 0), icon="solar:clock-circle-bold-duotone",
                     color="orange" if counts.get("stale") else "gray"),
            kpi_card("Ölü", str(counts.get("dead") or 0), icon="solar:danger-triangle-bold-duotone",
                     color="red" if counts.get("dead") else "gray"),
        ],
    )

    automations_section = dmc.Paper(
        p="lg", withBorder=True, radius="md", mb="lg",
        children=[
            section_header(
                "Otomasyonlar",
                "Her HMDL otomasyonunun son çalışması ve schedule tazeliği.",
                icon="solar:refresh-circle-bold-duotone",
            ),
            dmc.SimpleGrid(
                cols={"base": 1, "md": 2, "lg": 4},
                spacing="md",
                children=[_automation_card(a) for a in automations]
                or [dmc.Text("Otomasyon verisi yok (hmdl-api erişilemiyor).", size="sm", c="dimmed")],
            ),
        ],
    )

    total_px = int(psum.get("total") or 0)
    fresh_px = int(psum.get("fresh") or 0)
    proxy_section = dmc.Paper(
        p="lg", withBorder=True, radius="md", mb="lg",
        children=[
            section_header(
                "Proxy kapsamı (NiFi)",
                f"Son collector sync'te görülen proxy'ler — {fresh_px}/{total_px} taze.",
                icon="solar:server-path-bold-duotone",
            ),
            html.Div(
                style={"overflowX": "auto"},
                children=[
                    html.Table(
                        [
                            html.Tr([
                                html.Th("Proxy"), html.Th("DC"), html.Th("Host"),
                                html.Th("Son görülme"), html.Th("Durum"),
                            ]),
                            *[_proxy_row(p) for p in proxies],
                        ],
                        style={"width": "100%", "fontSize": "13px", "borderCollapse": "collapse"},
                    )
                    if proxies
                    else dmc.Text("Proxy verisi yok.", size="sm", c="dimmed"),
                ],
            ),
        ],
    )

    by_source = gaps.get("by_source") or {}
    gaps_section = dmc.Paper(
        p="lg", withBorder=True, radius="md",
        children=[
            section_header(
                "Kalıcı veri boşlukları",
                "Beklenen ama toplanmayan cluster/host (coverage).",
                icon="solar:checklist-minimalistic-bold-duotone",
            ),
            dmc.Group(
                gap="lg",
                children=[
                    kpi_card("Cluster eksik", str(gaps.get("cluster_missing") or 0),
                             icon="solar:server-path-bold-duotone",
                             color="orange" if gaps.get("cluster_missing") else "gray"),
                    kpi_card("IBM host eksik", str(gaps.get("ibm_missing") or 0),
                             icon="solar:server-path-bold-duotone",
                             color="orange" if gaps.get("ibm_missing") else "gray"),
                    *[
                        kpi_card(f"{src} eksik", str(cnt),
                                 icon="solar:server-path-bold-duotone",
                                 color="orange" if cnt else "gray")
                        for src, cnt in sorted(by_source.items())
                    ],
                ],
            ),
        ],
    )

    return html.Div(
        settings_page_shell(
            [
                dmc.Group(
                    mb="md",
                    children=[
                        dmc.Title("HMDL Automation Health", order=3),
                        dmc.Text(
                            "Otomasyonların schedule tazeliği ve veri kapsamı — read-only.",
                            size="sm", c="dimmed",
                        ),
                    ],
                ),
                kpis,
                automations_section,
                proxy_section,
                gaps_section,
            ]
        )
    )
