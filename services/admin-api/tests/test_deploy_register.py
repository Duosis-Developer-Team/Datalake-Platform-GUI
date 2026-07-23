"""Deploy self-registration helper is best-effort and posts the expected body."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app import deploy_register


def test_register_via_http_posts_expected_body(monkeypatch):
    monkeypatch.setenv("ADMIN_API_URL", "http://admin-api:8000")
    monkeypatch.setenv("APP_VERSION", "2026.07.3")
    monkeypatch.setenv("GIT_SHA", "abc1234")
    monkeypatch.setenv("DEPLOY_ENV", "production")
    fake_httpx = MagicMock()
    with patch.dict("sys.modules", {"httpx": fake_httpx}):
        deploy_register.register_this_service("query-api")
    assert fake_httpx.post.called
    _, kwargs = fake_httpx.post.call_args
    assert kwargs["json"]["service"] == "query-api"
    assert kwargs["json"]["version"] == "2026.07.3"
    assert kwargs["json"]["git_sha"] == "abc1234"


def test_register_swallows_http_errors(monkeypatch):
    monkeypatch.setenv("ADMIN_API_URL", "http://admin-api:8000")
    fake_httpx = MagicMock()
    fake_httpx.post.side_effect = RuntimeError("connection refused")
    with patch.dict("sys.modules", {"httpx": fake_httpx}):
        deploy_register.register_this_service("query-api")  # must not raise


def test_register_direct_db_when_no_admin_url(monkeypatch):
    monkeypatch.delenv("ADMIN_API_URL", raising=False)
    monkeypatch.setenv("APP_VERSION", "2026.07.3")
    with patch.object(deploy_register, "_direct_db_insert") as ins:
        deploy_register.register_this_service("admin-api")
    assert ins.called
    args = ins.call_args[0]
    assert args[0] == "admin-api"
    assert args[1] == "2026.07.3"


def test_register_direct_db_swallows_errors(monkeypatch):
    monkeypatch.delenv("ADMIN_API_URL", raising=False)
    with patch.object(deploy_register, "_direct_db_insert", side_effect=RuntimeError("db down")):
        deploy_register.register_this_service("admin-api")  # must not raise


def test_non_admin_service_without_url_skips_direct_db(monkeypatch):
    monkeypatch.delenv("ADMIN_API_URL", raising=False)
    with patch.object(deploy_register, "_direct_db_insert") as ins:
        deploy_register.register_this_service("customer-api")
    assert not ins.called  # only admin-api writes directly to the auth DB
