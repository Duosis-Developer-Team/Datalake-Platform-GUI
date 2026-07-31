"""Integrations — HMDL Ingest Health (per-collector-IP freshness / TASK-M1)."""

from __future__ import annotations

from urllib.parse import parse_qs

import dash_mantine_components as dmc
from dash import html

from src.services import api_client as api
from src.utils.hmdl_sync_ui import INGEST_VERDICT_LABELS, build_ingest_health_section
from src.utils.ui_tokens import section_header, settings_page_shell

_COLLECTOR_TYPES = [
    "",
    "VmWare",
    "Nutanix",
    "IBM-HMC",
    "Veeam",
    "Netbackup",
    "Zerto",
]


def _parse_q(search: str | None, key: str) -> str:
    params = parse_qs((search or "").lstrip("?"))
    return (params.get(key, [""])[0] or "").strip()


def _dc_options(locations: list[dict]) -> list[dict[str, str]]:
    options: list[dict[str, str]] = [{"label": "All locations", "value": ""}]
    for loc in locations:
        dc_code = str(loc.get("dc_code") or "").strip().upper()
        if dc_code:
            options.append({"label": dc_code, "value": dc_code})
    return options


def build_layout(search: str | None = None) -> html.Div:
    locations_data = api.get_hmdl_locations()
    locations = locations_data.get("items") or []
    selected_dc = _parse_q(search, "dc").upper()
    selected_type = _parse_q(search, "type")
    selected_verdict = _parse_q(search, "verdict")

    data = api.get_hmdl_ingest_health(
        selected_dc or None,
        collector_type=selected_type or None,
        verdict=selected_verdict or None,
    )

    return html.Div(
        settings_page_shell(
            [
                dmc.Group(
                    mb="md",
                    children=[
                        dmc.Title("Ingest Health", order=3),
                        dmc.Text(
                            "Collector IP başına datalake ingest tazeliği — erişim var ama veri geliyor mu?",
                            size="sm",
                            c="dimmed",
                        ),
                    ],
                ),
                dmc.Paper(
                    p="lg",
                    withBorder=True,
                    radius="md",
                    children=[
                        section_header(
                            "Endpoint ingest report",
                            "Verdict: healthy / no_network / network_ok_no_data / stale / unmatched "
                            "(A-04 stale windows from collector_ingest_map).",
                            icon="solar:graph-up-bold-duotone",
                        ),
                        dmc.Grid(
                            gutter="md",
                            mb="md",
                            children=[
                                dmc.GridCol(
                                    span={"base": 12, "md": 4},
                                    children=dmc.Select(
                                        id="hmdl-ingest-dc",
                                        label="Location",
                                        data=_dc_options(locations),
                                        value=selected_dc,
                                        clearable=True,
                                        searchable=True,
                                        size="sm",
                                    ),
                                ),
                                dmc.GridCol(
                                    span={"base": 12, "md": 4},
                                    children=dmc.Select(
                                        id="hmdl-ingest-type",
                                        label="Collector type",
                                        data=[
                                            {"label": "All", "value": ""},
                                            *[{"label": t, "value": t} for t in _COLLECTOR_TYPES if t],
                                        ],
                                        value=selected_type,
                                        clearable=True,
                                        size="sm",
                                    ),
                                ),
                                dmc.GridCol(
                                    span={"base": 12, "md": 4},
                                    children=dmc.Select(
                                        id="hmdl-ingest-verdict",
                                        label="Verdict",
                                        data=[
                                            {"label": "All", "value": ""},
                                            *[
                                                {"label": INGEST_VERDICT_LABELS.get(v, v), "value": v}
                                                for v in (
                                                    "healthy",
                                                    "no_network",
                                                    "network_ok_no_data",
                                                    "stale",
                                                    "unmatched",
                                                )
                                            ],
                                        ],
                                        value=selected_verdict,
                                        clearable=True,
                                        size="sm",
                                    ),
                                ),
                            ],
                        ),
                        html.Div(
                            id="hmdl-ingest-content",
                            children=build_ingest_health_section(data),
                        ),
                    ],
                ),
            ]
        )
    )
