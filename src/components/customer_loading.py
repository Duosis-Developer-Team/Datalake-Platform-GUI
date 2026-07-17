"""Psychology-focused loading shell for Customer View (skeleton + reassurance copy).

Design standard: docs/LOADING_UX_DESIGN.md — use as reference for future loading screens.
"""
from __future__ import annotations

from dash import html, dcc
import dash_mantine_components as dmc
from dash_iconify import DashIconify

_LOADING_STAGES_SUMMARY = (
    "Preparing customer dashboard…",
    "Loading billing assets…",
    "Fetching availability metrics…",
    "Building executive overview…",
)

_LOADING_STAGES_VIRT = (
    "Loading virtualization metrics…",
    "Fetching cluster capacity…",
    "Building compute gauges…",
    "Preparing VM inventory…",
)

_LOADING_STAGES_AVAIL = (
    "Loading availability metrics…",
    "Fetching outage history…",
    "Building SLA overview…",
)

_LOADING_STAGES_BACKUP = (
    "Loading backup data…",
    "Fetching replication status…",
    "Building backup overview…",
)

_LOADING_STAGES_BILLING = (
    "Loading billing assets…",
    "Fetching active orders…",
    "Building CRM sections…",
)

_LOADING_STAGES_ITSM = (
    "Loading ITSM tickets…",
    "Fetching incident history…",
    "Building service request panels…",
)

_LOADING_STAGES_PHYS_INV = (
    "Loading physical inventory…",
    "Fetching asset records…",
    "Building inventory tables…",
)

_LOADING_STAGES_S3 = (
    "Loading S3 storage data…",
    "Fetching bucket metrics…",
    "Building storage overview…",
)

_LOADING_STAGES_GENERIC = (
    "Loading tab content…",
    "Fetching metrics…",
    "Building dashboard panels…",
)

_TAB_STAGE_MAP = {
    "summary": _LOADING_STAGES_SUMMARY,
    "virt": _LOADING_STAGES_VIRT,
    "avail": _LOADING_STAGES_AVAIL,
    "backup": _LOADING_STAGES_BACKUP,
    "billing": _LOADING_STAGES_BILLING,
    "itsm": _LOADING_STAGES_ITSM,
    "phys-inv": _LOADING_STAGES_PHYS_INV,
    "s3": _LOADING_STAGES_S3,
}

# Page-level rotation (initial full-page load) uses summary stages.
LOADING_STAGE_MESSAGES = _LOADING_STAGES_SUMMARY


def loading_stages_for_tab(tab: str | None) -> tuple[str, ...]:
    """Return rotating status messages for a customer tab key."""
    key = str(tab or "summary").strip().lower()
    return _TAB_STAGE_MAP.get(key, _LOADING_STAGES_GENERIC)


def _metric_skeleton() -> html.Div:
    return html.Div(
        className="customer-load-shimmer",
        style={
            "background": "#fff",
            "borderRadius": "16px",
            "padding": "20px",
            "border": "1px solid #eef1f4",
            "minHeight": "120px",
        },
        children=[
            dmc.Skeleton(height=14, width="45%", mb="sm", radius="sm"),
            dmc.Skeleton(height=28, width="60%", mb="xs", radius="sm"),
            dmc.Skeleton(height=10, width="80%", radius="sm"),
        ],
    )


def _kpi_skeleton() -> html.Div:
    return html.Div(
        className="customer-load-shimmer",
        style={
            "background": "#fff",
            "borderRadius": "16px",
            "padding": "18px",
            "border": "1px solid #eef1f4",
            "minHeight": "130px",
        },
        children=[
            dmc.Skeleton(height=12, width="50%", mb="sm", radius="sm"),
            dmc.Skeleton(height=24, width="70%", mb="xs", radius="sm"),
            dmc.Skeleton(height=10, width="85%", radius="sm"),
        ],
    )


def _gauge_skeleton() -> html.Div:
    return html.Div(
        className="customer-load-shimmer",
        style={
            "background": "#fff",
            "borderRadius": "16px",
            "padding": "20px",
            "border": "1px solid #eef1f4",
            "minHeight": "160px",
            "display": "flex",
            "flexDirection": "column",
            "alignItems": "center",
        },
        children=[
            dmc.Skeleton(height=100, width=100, radius="xl", mb="sm"),
            dmc.Skeleton(height=12, width="60%", radius="sm"),
        ],
    )


def _section_skeleton(height: int = 200) -> html.Div:
    return html.Div(
        className="customer-load-shimmer",
        style={
            "background": "#fff",
            "borderRadius": "16px",
            "padding": "24px",
            "border": "1px solid #eef1f4",
            "minHeight": f"{height}px",
        },
        children=[
            dmc.Skeleton(height=16, width="30%", mb="md", radius="sm"),
            dmc.Skeleton(height=12, width="100%", mb="sm", radius="sm"),
            dmc.Skeleton(height=12, width="92%", mb="sm", radius="sm"),
            dmc.Skeleton(height=12, width="88%", radius="sm"),
        ],
    )


def build_customer_tab_loading_shell(tab: str, customer_name: str) -> html.Div:
    """Per-tab loading skeleton shown while a lazy tab panel loads."""
    name = str(customer_name or "Customer").strip() or "Customer"
    stages = loading_stages_for_tab(tab)
    tab_key = str(tab or "summary").strip().lower()

    if tab_key == "virt":
        body = [
            dmc.Skeleton(height=40, width="100%", radius="xl", mb="lg"),
            dmc.SimpleGrid(
                cols={"base": 1, "md": 2},
                spacing="md",
                mb="lg",
                children=[_gauge_skeleton(), _gauge_skeleton()],
            ),
            _section_skeleton(200),
        ]
    elif tab_key == "summary":
        body = [
            dmc.SimpleGrid(
                cols={"base": 1, "sm": 2, "md": 5},
                spacing="lg",
                mb="lg",
                children=[_metric_skeleton() for _ in range(5)],
            ),
            _section_skeleton(180),
            html.Div(style={"height": "16px"}),
            _section_skeleton(220),
        ]
    else:
        body = [
            dmc.SimpleGrid(
                cols={"base": 1, "sm": 2, "lg": 3},
                spacing="md",
                mb="lg",
                children=[_kpi_skeleton() for _ in range(3)],
            ),
            _section_skeleton(220),
        ]

    return html.Div(
        className="customer-tab-loading-layer customer-loading-layer",
        style={"padding": "24px 0"},
        children=[
            html.Div(
                className="customer-loading-hero",
                style={"marginBottom": "20px"},
                children=[
                    DashIconify(
                        icon="solar:users-group-two-rounded-bold-duotone",
                        width=40,
                        color="#4318FF",
                    ),
                    dmc.Text(name, fw=600, size="md", c="#2B3674", ta="center", mt="xs"),
                    dmc.Text(
                        children=stages[0],
                        size="sm",
                        c="#A3AED0",
                        ta="center",
                    ),
                    html.Div(
                        className="building-reveal-dots",
                        children=[
                            html.Span(className="brd-dot"),
                            html.Span(className="brd-dot"),
                            html.Span(className="brd-dot"),
                        ],
                    ),
                ],
            ),
            html.Div(style={"padding": "0 30px"}, children=body),
            dmc.Text(
                "This usually takes a few seconds on first visit.",
                size="xs",
                c="dimmed",
                ta="center",
                mt="md",
            ),
        ],
    )


def build_customer_loading_shell(customer_name: str) -> html.Div:
    """Instant shell shown while Customer View data loads asynchronously."""
    name = str(customer_name or "Customer").strip() or "Customer"
    return html.Div(
        id="customer-loading-layer",
        className="customer-loading-layer",
        children=[
            html.Div(
                className="customer-loading-hero",
                children=[
                    DashIconify(
                        icon="solar:users-group-two-rounded-bold-duotone",
                        width=56,
                        color="#4318FF",
                        className="customer-loading-icon",
                    ),
                    dmc.Text(name, fw=700, size="xl", c="#2B3674", ta="center"),
                    dmc.Text(
                        children=_LOADING_STAGES_SUMMARY[0],
                        size="sm",
                        c="#A3AED0",
                        ta="center",
                    ),
                    html.Div(
                        className="building-reveal-dots",
                        children=[
                            html.Span(className="brd-dot"),
                            html.Span(className="brd-dot"),
                            html.Span(className="brd-dot"),
                        ],
                    ),
                ],
            ),
            dmc.SimpleGrid(
                cols={"base": 1, "sm": 2, "md": 5},
                spacing="lg",
                style={"padding": "0 30px", "marginBottom": "24px"},
                children=[_metric_skeleton() for _ in range(5)],
            ),
            html.Div(
                style={"padding": "0 30px"},
                children=[
                    _section_skeleton(180),
                    html.Div(style={"height": "16px"}),
                    _section_skeleton(220),
                ],
            ),
            dmc.Text(
                "This usually takes a few seconds on first visit.",
                size="xs",
                c="dimmed",
                ta="center",
                mt="lg",
            ),
        ],
    )
