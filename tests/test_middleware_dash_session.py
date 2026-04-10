"""Session hydration for /_dash routes (see src.auth.middleware)."""

from __future__ import annotations

from unittest.mock import patch


def test_hydrate_g_from_session_sets_user():
    from flask import Flask, g, session

    from src.auth.config import SESSION_COOKIE_NAME
    from src.auth.middleware import _hydrate_g_from_session

    app = Flask(__name__)
    app.secret_key = "test-secret"

    fake_row = {"id": 42, "username": "admin", "source": "local"}

    with app.test_request_context("/_dash-update-component", method="POST"):
        session[SESSION_COOKIE_NAME] = "valid-token"
        g.auth_user = None
        g.auth_user_id = None

        with patch(
            "src.auth.middleware.service.get_session_user",
            return_value=fake_row,
        ):
            _hydrate_g_from_session()

        assert g.auth_user_id == 42
        assert g.auth_user["username"] == "admin"


def test_hydrate_g_from_session_noop_without_valid_session():
    from flask import Flask, g, session

    from src.auth.config import SESSION_COOKIE_NAME
    from src.auth.middleware import _hydrate_g_from_session

    app = Flask(__name__)
    app.secret_key = "test-secret"

    with app.test_request_context("/_dash-update-component", method="POST"):
        session[SESSION_COOKIE_NAME] = "bad"
        g.auth_user = None
        g.auth_user_id = None

        with patch("src.auth.middleware.service.get_session_user", return_value=None):
            _hydrate_g_from_session()

        assert g.auth_user is None
        assert g.auth_user_id is None
