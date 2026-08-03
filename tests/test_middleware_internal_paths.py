"""The release-ingest routes must bypass the session gate, but nothing wider.

The ingest blueprint authenticates with a shared token, not a browser session.
Without an exemption the app-level `before_request` gate fires first and
redirects the machine caller to /login, so a correct token still fails.

The exemption is deliberately scoped to the release-ingest prefix rather than
all of /internal/: a blanket rule would silently make every future blueprint
mounted under /internal/ session-public.
"""

from __future__ import annotations

from src.auth.middleware import _is_public_path


def test_release_ingest_paths_bypass_the_session_gate():
    assert _is_public_path("/internal/platform/releases") is True
    assert _is_public_path("/internal/platform/releases/last-sha") is True
    assert _is_public_path("/internal/platform/releases/2026.08.1/note/confirm") is True


def test_the_exemption_does_not_cover_all_of_internal():
    assert _is_public_path("/internal/") is False
    assert _is_public_path("/internal/admin") is False
    assert _is_public_path("/internal/platform/other") is False


def test_gated_app_reaches_the_endpoint_instead_of_redirecting(monkeypatch):
    """End to end: middleware + blueprint on one app, no session cookie.

    A 302 here means the machine caller never reaches the token check.
    """
    from flask import Flask

    from src.auth import middleware as mw
    from src.routes.release_ingest import register_release_ingest_routes

    monkeypatch.setattr(mw, "AUTH_DISABLED", False)
    monkeypatch.delenv("RELEASE_INGEST_TOKEN", raising=False)

    app = Flask(__name__)
    app.secret_key = "test-secret"
    mw.register_middleware(app)
    register_release_ingest_routes(app)

    resp = app.test_client().get("/internal/platform/releases/last-sha")

    assert resp.status_code != 302, "session gate swallowed the request"
    assert resp.status_code == 503, "token unset must close the endpoint, not open it"
