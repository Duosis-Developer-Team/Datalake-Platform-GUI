"""Psychology-focused loading shell for Customer View (skeleton + reassurance copy).

Design standard: docs/LOADING_UX_DESIGN.md — use as reference for future loading screens.
"""
from __future__ import annotations

from dash import html, dcc
import dash_mantine_components as dmc
from dash_iconify import DashIconify

_LOADING_STAGES = (
    "Preparing customer dashboard…",
    "Loading billing assets…",
    "Fetching availability metrics…",
    "Loading backup and storage data…",
)


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
                        id="customer-loading-status",
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
            dcc.Interval(
                id="customer-loading-stage-interval",
                interval=2200,
                n_intervals=0,
            ),
        ],
    )


LOADING_STAGE_MESSAGES = _LOADING_STAGES
