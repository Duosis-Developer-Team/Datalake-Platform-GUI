"""Psychology-focused loading shell for DC View (skeleton + reassurance copy).

Design standard: docs/LOADING_UX_DESIGN.md
"""
from __future__ import annotations

from dash import dcc, html
import dash_mantine_components as dmc
from dash_iconify import DashIconify

_LOADING_STAGES_SUMMARY = (
    "Preparing data center dashboard…",
    "Loading capacity metrics…",
    "Fetching sellable potential summary…",
    "Building executive overview…",
)

_LOADING_STAGES_VIRT = (
    "Loading virtualization metrics…",
    "Fetching cluster capacity…",
    "Building compute gauges…",
    "Preparing sellable potential cards…",
)

_LOADING_STAGES_STORAGE = (
    "Loading storage metrics…",
    "Fetching capacity pools…",
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
    "storage": _LOADING_STAGES_STORAGE,
}

LOADING_STAGE_MESSAGES = _LOADING_STAGES_SUMMARY


def loading_stages_for_tab(tab: str | None) -> tuple[str, ...]:
    """Return rotating status messages for a tab key."""
    key = str(tab or "summary").strip().lower()
    return _TAB_STAGE_MAP.get(key, _LOADING_STAGES_GENERIC)


def _kpi_skeleton() -> html.Div:
    return html.Div(
        className="dc-load-shimmer customer-load-shimmer",
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
        className="dc-load-shimmer customer-load-shimmer",
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
        className="dc-load-shimmer customer-load-shimmer",
        style={
            "background": "#fff",
            "borderRadius": "16px",
            "padding": "24px",
            "border": "1px solid #eef1f4",
            "minHeight": f"{height}px",
        },
        children=[
            dmc.Skeleton(height=16, width="35%", mb="md", radius="sm"),
            dmc.Skeleton(height=12, width="100%", mb="sm", radius="sm"),
            dmc.Skeleton(height=12, width="94%", mb="sm", radius="sm"),
            dmc.Skeleton(height=12, width="88%", radius="sm"),
        ],
    )


def build_dc_loading_shell(dc_display: str, *, tab: str = "summary") -> html.Div:
    """Instant shell shown while DC View data loads asynchronously."""
    label = str(dc_display or "Data Center").strip() or "Data Center"
    stages = loading_stages_for_tab(tab)
    return html.Div(
        id="dc-loading-layer",
        className="dc-loading-layer customer-loading-layer",
        children=[
            html.Div(
                className="dc-loading-hero customer-loading-hero",
                children=[
                    DashIconify(
                        icon="solar:server-square-bold-duotone",
                        width=56,
                        color="#4318FF",
                        className="dc-loading-icon customer-loading-icon",
                    ),
                    dmc.Text(label, fw=700, size="xl", c="#2B3674", ta="center"),
                    dmc.Text(
                        id="dc-loading-status",
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
            dmc.SimpleGrid(
                cols={"base": 1, "sm": 2, "lg": 4},
                spacing="md",
                style={"padding": "0 30px", "marginBottom": "24px"},
                children=[_kpi_skeleton() for _ in range(4)],
            ),
            html.Div(
                style={"padding": "0 30px"},
                children=[
                    _section_skeleton(180),
                    html.Div(style={"height": "16px"}),
                    _section_skeleton(220),
                    html.Div(style={"height": "16px"}),
                    _section_skeleton(160),
                ],
            ),
            dmc.Text(
                "This usually takes a few seconds on first visit.",
                size="xs",
                c="dimmed",
                ta="center",
                mt="lg",
            ),
            dcc.Interval(
                id="dc-loading-stage-interval",
                interval=2200,
                n_intervals=0,
            ),
        ],
    )


def build_dc_tab_loading_shell(tab: str, dc_display: str) -> html.Div:
    """Per-tab loading skeleton shown while a lazy tab panel loads."""
    label = str(dc_display or "Data Center").strip() or "Data Center"
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
        className="dc-tab-loading-layer customer-loading-layer",
        style={"padding": "24px 0"},
        children=[
            html.Div(
                className="dc-loading-hero customer-loading-hero",
                style={"marginBottom": "20px"},
                children=[
                    DashIconify(
                        icon="solar:server-square-bold-duotone",
                        width=40,
                        color="#4318FF",
                    ),
                    dmc.Text(label, fw=600, size="md", c="#2B3674", ta="center", mt="xs"),
                    dmc.Text(
                        id=f"dc-tab-loading-status-{tab_key}",
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
