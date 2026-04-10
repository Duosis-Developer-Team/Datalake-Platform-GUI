"""Login page (Dash layout + form posts to Flask /auth/login)."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import dcc, html
from dash_iconify import DashIconify


def build_login_layout(next_path: str = "/", error: bool = False) -> html.Div:
    action = "/auth/login"
    return html.Div(
        style={
            "minHeight": "100vh",
            "display": "flex",
            "alignItems": "center",
            "justifyContent": "center",
            "background": "linear-gradient(135deg, #F4F7FE 0%, #EEF2FF 100%)",
            "padding": "24px",
        },
        children=[
            dmc.Paper(
                w="100%",
                maw=420,
                p="xl",
                radius="lg",
                shadow="md",
                withBorder=True,
                children=[
                    dmc.Stack(
                        gap="lg",
                        children=[
                            dmc.Group(
                                gap="sm",
                                children=[
                                    DashIconify(icon="mdi:cloud", width=36, color="#4318FF"),
                                    dmc.Text("Bulutistan Dashboard", fw=800, size="lg", c="#2B3674"),
                                ],
                            ),
                            dmc.Text("Sign in to continue", size="sm", c="dimmed"),
                            html.Form(
                                method="POST",
                                action=action,
                                children=[
                                    dcc.Input(
                                        type="hidden",
                                        name="next",
                                        value=next_path or "/",
                                    ),
                                    dmc.Stack(
                                        gap="md",
                                        children=[
                                            html.Div(
                                                children=[
                                                    dmc.Text("Username", size="xs", fw=600, mb=6, c="dimmed"),
                                                    dcc.Input(
                                                        id="login-username",
                                                        name="username",
                                                        type="text",
                                                        required=True,
                                                        autoComplete="username",
                                                        style={
                                                            "width": "100%",
                                                            "padding": "10px 12px",
                                                            "borderRadius": "10px",
                                                            "border": "1px solid #E9ECEF",
                                                            "fontSize": "14px",
                                                        },
                                                    ),
                                                ]
                                            ),
                                            html.Div(
                                                children=[
                                                    dmc.Text("Password", size="xs", fw=600, mb=6, c="dimmed"),
                                                    dcc.Input(
                                                        id="login-password",
                                                        name="password",
                                                        type="password",
                                                        required=True,
                                                        autoComplete="current-password",
                                                        style={
                                                            "width": "100%",
                                                            "padding": "10px 12px",
                                                            "borderRadius": "10px",
                                                            "border": "1px solid #E9ECEF",
                                                            "fontSize": "14px",
                                                        },
                                                    ),
                                                ]
                                            ),
                                            html.Button(
                                                "Sign in",
                                                type="submit",
                                                style={
                                                    "width": "100%",
                                                    "padding": "10px 12px",
                                                    "borderRadius": "10px",
                                                    "border": "none",
                                                    "background": "#4318FF",
                                                    "color": "white",
                                                    "fontWeight": "700",
                                                    "cursor": "pointer",
                                                },
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            dmc.Alert(
                                "Invalid username or password.",
                                title="Authentication failed",
                                color="red",
                                variant="light",
                                style={"display": "block" if error else "none"},
                            ),
                            html.Div(
                                style={"fontSize": "11px", "color": "#98A2B3"},
                                children="Session cookies are used for authentication.",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


def parse_login_search(search: str | None) -> tuple[str, bool]:
    """Return (next_path, error_flag) from ?next=...&error=1."""
    if not search:
        return "/", False
    from urllib.parse import parse_qs

    q = parse_qs(search.lstrip("?"))
    nxt = (q.get("next") or ["/"])[0] or "/"
    err = (q.get("error") or ["0"])[0] == "1"
    return nxt, err
