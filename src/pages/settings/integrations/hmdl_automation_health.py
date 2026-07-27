"""Integrations — HMDL Automation Health (schedule / freshness monitoring).

Surfaces *when each HMDL automation last ran* and whether it is on schedule, so a
stalled schedule (collector sync, reachability checks, VM reconciliation) is visible
within hours instead of going unnoticed for weeks. Read-only; data from hmdl-api
`/collectors/automation-health`.
"""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import html
from dash_iconify import DashIconify

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
    # data_families is still served by hmdl-api for drill-down consumers; this page
    # now renders the per-flow rollup instead, so it does not read it.
    data_counts = data.get("data_counts") or {}
    data_status = data.get("data_status") or "computing"
    data_flows = data.get("data_flows") or []
    data_unmonitored = data.get("data_unmonitored") or []

    # Headline alert covers BOTH schedule (automations) and data freshness, so a
    # dead data flow (e.g. datastore stale) shows up even if the job ran.
    alert = int(counts.get("alert") or 0) + int(data_counts.get("alert") or 0)

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

    data_dead = int(data_counts.get("dead") or 0)
    data_stale = int(data_counts.get("stale") or 0)

    def _age_text(age_hours) -> str:
        if age_hours is None:
            return ""
        days = float(age_hours) / 24.0
        if days >= 1:
            return f"{days:.0f} gündür güncellenmiyor"
        return f"{float(age_hours):.0f} saattir güncellenmiyor"

    def _flow_row(flow: dict):
        """One collection flow. The headline names the DATA; the member tables sit
        behind a disclosure so internal users keep what they debug with."""
        status = flow.get("status") or "unknown"
        color = {"dead": "red", "stale": "orange", "unknown": "gray"}.get(status, "green")
        icon = "solar:danger-triangle-bold-duotone" if status in ("dead", "stale") \
            else "solar:check-circle-bold-duotone"
        sources = flow.get("sources") or []
        return dmc.Paper(
            p="md", withBorder=True, radius="md",
            children=[
                dmc.Group(gap="xs", align="center", children=[
                    DashIconify(icon=icon, width=20),
                    dmc.Text(flow.get("label") or flow.get("key") or "—", fw=700),
                    dmc.Text(_age_text(flow.get("age_hours")), size="sm", c=color),
                ]),
                dmc.Accordion(
                    variant="subtle", chevronPosition="left", mt=6,
                    children=[dmc.AccordionItem(value="detay", children=[
                        dmc.AccordionControl(
                            dmc.Text(f"{len(sources)} tablo", size="xs", c="dimmed")
                        ),
                        dmc.AccordionPanel(
                            dmc.Stack(gap=6, children=[_automation_card(s) for s in sources])
                        ),
                    ])],
                ),
            ],
        )

    alerting_flows = [f for f in data_flows if (f.get("status") in ("dead", "stale"))]

    if data_status == "computing":
        data_body = dmc.Text("Veri tazeliği hesaplanıyor… birazdan yenileyin.", size="sm", c="dimmed")
    elif not data_flows:
        data_body = dmc.Text("Veri kaynağı bilgisi yok (hmdl-api erişilemiyor).", size="sm", c="dimmed")
    elif not alerting_flows:
        data_body = dmc.Alert(
            "Tüm veri akışları güncel.", color="green", variant="light",
            icon=DashIconify(icon="solar:check-circle-bold-duotone", width=20),
        )
    else:
        data_body = dmc.Stack(gap="sm", children=[_flow_row(f) for f in alerting_flows])

    data_body = html.Div(id="hmdl-ah-flows", children=data_body)

    unmonitored_section = dmc.Accordion(
        id="hmdl-ah-unmonitored", variant="contained", chevronPosition="left", mt="md",
        children=[dmc.AccordionItem(value="unmonitored", children=[
            dmc.AccordionControl(
                dmc.Text(
                    f"İzlenmeyen tablolar ({len(data_unmonitored)}) — "
                    "hiçbir servis bu tabloları sorgulamıyor",
                    size="sm", c="dimmed",
                )
            ),
            dmc.AccordionPanel(
                dmc.Stack(gap=6, children=[_automation_card(s) for s in data_unmonitored])
            ),
        ])],
    ) if data_unmonitored else html.Div(id="hmdl-ah-unmonitored")

    data_sources_section = dmc.Paper(
        p="lg", withBorder=True, radius="md", mb="lg",
        children=[
            section_header(
                "Data Collection Freshness",
                "Toplanan verinin aile bazında tazeliği — 'iş çalıştı' değil, 'veri geldi mi'. "
                f"{data_dead} ölü · {data_stale} bayat.",
                icon="solar:database-bold-duotone",
            ),
            data_body,
            unmonitored_section,
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
                data_sources_section,
                proxy_section,
                gaps_section,
            ]
        )
    )
