"""Psychology-focused loading shell for DC View (skeleton + reassurance copy).

Design standard: docs/LOADING_UX_DESIGN.md
"""
from __future__ import annotations

from dash import dcc, html
import dash_mantine_components as dmc
from dash_iconify import DashIconify

_LOADING_STAGES = (
    "Preparing data center dashboard…",
    "Loading capacity metrics…",
    "Fetching sellable potential summary…",
    "Building executive overview…",
)


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


def build_dc_loading_shell(dc_id: str) -> html.Div:
    """Instant shell shown while DC View data loads asynchronously."""
    label = str(dc_id or "Data Center").strip() or "Data Center"
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
                        children=_LOADING_STAGES[0],
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
                "First visit may take a few seconds while caches warm in the background.",
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


LOADING_STAGE_MESSAGES = _LOADING_STAGES
