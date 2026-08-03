"""Authorization gate on Dash's callback transport (/_dash-update-component).

The endpoint dispatches every page callback in the app, so an unauthenticated
caller must not be able to reach page callbacks — but the app shell (including
the login layout, which is itself rendered by a callback) must still boot.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from dash import dcc, html
from flask import Flask, g, jsonify, session

from src.auth import dash_gate
from src.auth.config import SESSION_COOKIE_NAME


# --------------------------------------------------------------------------
# collect_component_ids: what counts as "shell"
# --------------------------------------------------------------------------


def test_collect_component_ids_walks_nested_children():
    layout = html.Div(
        [
            dcc.Location(id="url"),
            dcc.Store(id="app-time-range"),
            html.Div(
                id="main-shell",
                children=[html.Div(id="main-content", children=[])],
            ),
        ]
    )

    ids = dash_gate.collect_component_ids(layout)

    assert {"url", "app-time-range", "main-shell", "main-content"} <= ids


def test_collect_component_ids_skips_non_string_ids():
    layout = html.Div([html.Div(id={"type": "nav", "index": 1}), html.Div(id="sidebar-nav")])

    ids = dash_gate.collect_component_ids(layout)

    assert ids == {"sidebar-nav"}


def test_collect_component_ids_finds_components_outside_children():
    """dcc.Loading-style wrappers keep components in non-`children` props too."""
    layout = html.Div(
        children=dcc.Loading(
            id="main-content-loading",
            children=html.Div(id="main-content"),
        )
    )

    ids = dash_gate.collect_component_ids(layout)

    assert {"main-content-loading", "main-content"} <= ids


# --------------------------------------------------------------------------
# output parsing
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "output,expected",
    [
        ("main-content.children", {"main-content"}),
        ("url.pathname@20362a91ef71d0", {"url"}),
        (
            "..sidebar-shell.style...main-shell.style..",
            {"sidebar-shell", "main-shell"},
        ),
        (
            "..auth-user-store.data...auth-permissions-store.data..",
            {"auth-user-store", "auth-permissions-store"},
        ),
        # Pattern-matching ids come back verbatim so they fail the shell check.
        (
            '{"section":["ALL"],"type":"customer-section-cards"}.children',
            {'{"section":["ALL"],"type":"customer-section-cards"}'},
        ),
        ("", set()),
        (None, set()),
    ],
)
def test_output_component_ids(output, expected):
    assert dash_gate.output_component_ids(output) == expected


def test_pattern_matching_output_is_never_shell():
    shell = {"main-content", "url"}
    out = '..{"type":"compute-gauge-util"}.style...{"type":"compute-gauge-alloc"}.style..'

    assert dash_gate.is_shell_only(out, shell) is False


def test_mixed_shell_and_page_output_is_denied():
    """One page target poisons the whole request — the callback runs as a unit."""
    shell = {"main-content", "url"}

    assert dash_gate.is_shell_only("..main-content.children...overview-page-root.children..", shell) is False


def test_unparseable_output_is_denied():
    assert dash_gate.is_shell_only("garbage-without-a-property", {"main-content"}) is False


def test_empty_output_is_denied():
    assert dash_gate.is_shell_only("", {"main-content"}) is False


# --------------------------------------------------------------------------
# the middleware gate itself
# --------------------------------------------------------------------------


SHELL_IDS = {
    "main-content",
    "sidebar-nav",
    "sidebar-shell",
    "main-shell",
    "auth-user-store",
    "auth-permissions-store",
    "url",
}


def _make_app(shell_ids=SHELL_IDS):
    from src.auth.middleware import register_middleware

    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.config["TESTING"] = True

    @app.route("/_dash-update-component", methods=["POST"])
    def _update():
        return jsonify({"response": {"secret": "real inventory rows"}})

    @app.route("/_dash-layout")
    def _layout():
        return jsonify({"shell": True})

    @app.route("/_dash-dependencies")
    def _deps():
        return jsonify([])

    @app.route("/")
    def _home():
        return "home"

    register_middleware(app)
    dash_gate.set_shell_component_ids(shell_ids)
    return app


def _post(client, output, **kwargs):
    return client.post(
        "/_dash-update-component",
        data=json.dumps({"output": output, "outputs": {}, "inputs": [], "changedPropIds": []}),
        content_type="application/json",
        **kwargs,
    )


@pytest.fixture()
def _restore_shell_ids():
    """Importing app.py registers the real shell set once per session — put it
    back, or every later test that relies on it sees an unregistered gate."""
    previous = dash_gate.get_shell_component_ids()
    yield
    dash_gate.set_shell_component_ids(previous)


@pytest.fixture()
def gated_app(_restore_shell_ids):
    app = _make_app()
    with patch("src.auth.middleware.AUTH_DISABLED", False):
        yield app


def test_page_callback_without_session_is_401(gated_app):
    with patch("src.auth.middleware.service.get_session_user", return_value=None):
        resp = _post(gated_app.test_client(), "overview-page-root.children")

    assert resp.status_code == 401
    assert resp.get_json()["error"] == "session_expired"
    assert b"real inventory rows" not in resp.data


def test_shell_callback_without_session_is_allowed(gated_app):
    """The login form is rendered by main-content.children — it must still run."""
    with patch("src.auth.middleware.service.get_session_user", return_value=None):
        resp = _post(gated_app.test_client(), "main-content.children")

    assert resp.status_code == 200


def test_multi_output_shell_callback_without_session_is_allowed(gated_app):
    with patch("src.auth.middleware.service.get_session_user", return_value=None):
        resp = _post(gated_app.test_client(), "..sidebar-shell.style...main-shell.style..")

    assert resp.status_code == 200


def test_page_callback_with_session_is_allowed(gated_app):
    row = {"id": 7, "username": "admin", "source": "local"}
    client = gated_app.test_client()
    with client.session_transaction() as sess:
        sess[SESSION_COOKIE_NAME] = "valid-token"

    with patch("src.auth.middleware.service.get_session_user", return_value=row):
        resp = _post(client, "overview-page-root.children")

    assert resp.status_code == 200
    assert b"real inventory rows" in resp.data


def test_session_still_hydrates_g_for_page_callbacks(gated_app):
    row = {"id": 7, "username": "admin", "source": "local"}
    seen = {}

    @gated_app.route("/_dash-probe", methods=["POST"])
    def _probe():
        seen["uid"] = getattr(g, "auth_user_id", None)
        return "ok"

    client = gated_app.test_client()
    with client.session_transaction() as sess:
        sess[SESSION_COOKIE_NAME] = "valid-token"

    with patch("src.auth.middleware.service.get_session_user", return_value=row):
        client.post("/_dash-probe")

    assert seen["uid"] == 7


def test_shell_boot_endpoints_are_never_gated(gated_app):
    with patch("src.auth.middleware.service.get_session_user", return_value=None):
        client = gated_app.test_client()
        assert client.get("/_dash-layout").status_code == 200
        assert client.get("/_dash-dependencies").status_code == 200


def test_auth_disabled_lets_page_callbacks_through(_restore_shell_ids):
    app = _make_app()
    row = {"id": 1, "username": "admin", "source": "local"}
    with patch("src.auth.middleware.AUTH_DISABLED", True), patch(
        "src.auth.middleware.service.get_user_by_username", return_value=row
    ):
        resp = _post(app.test_client(), "overview-page-root.children")
    assert resp.status_code == 200


def test_gate_is_inert_until_shell_ids_are_registered(_restore_shell_ids):
    """A misconfigured boot must not lock every callback out of the app."""
    app = _make_app(shell_ids=None)
    with patch("src.auth.middleware.AUTH_DISABLED", False), patch(
        "src.auth.middleware.service.get_session_user", return_value=None
    ):
        resp = _post(app.test_client(), "overview-page-root.children")
    assert resp.status_code == 200


def test_real_app_layout_yields_shell_but_not_page_ids():
    """Pins the derivation against the real layout, not a toy tree.

    `main-content` must be in (the login form is rendered into it) and
    `overview-page-root` must be out (it only exists once a page has been
    injected, which already required an authorized main-content.children).
    """
    import app as app_module

    ids = dash_gate.collect_component_ids(app_module.app.layout)

    assert {
        "url",
        "main-content",
        "sidebar-nav",
        "sidebar-shell",
        "main-shell",
        "auth-user-store",
        "auth-permissions-store",
        "app-time-range",
    } <= ids
    assert "overview-page-root" not in ids
    assert "dc-view-page-root" not in ids
    assert "customer-view-page-root" not in ids
    assert "crm-inventory-page-root" not in ids


def test_app_registers_its_shell_ids_at_import():
    import app  # noqa: F401  (import registers the shell set)

    registered = dash_gate.get_shell_component_ids()
    assert registered is not None
    assert "main-content" in registered
    assert "overview-page-root" not in registered


def test_unreadable_body_is_denied(gated_app):
    with patch("src.auth.middleware.service.get_session_user", return_value=None):
        resp = gated_app.test_client().post(
            "/_dash-update-component",
            data=b"not json",
            content_type="application/json",
        )

    assert resp.status_code == 401
