"""GUI → chatbot-api release note çağrısı — ağ mock'lanır."""

from __future__ import annotations

from unittest.mock import patch

import jwt
import pytest
import requests

from src.auth import api_jwt
from src.services import chatbot_client


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


def test_service_token_carries_subject_and_typ():
    token = api_jwt.create_service_token()
    claims = jwt.decode(token, api_jwt._API_SECRET, algorithms=["HS256"])
    assert claims["sub"] == "release-bot"
    assert claims["typ"] == "service"
    assert claims["exp"] > claims["iat"]


def test_generate_posts_to_release_notes_endpoint():
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen["url"] = url
        seen["json"] = json
        seen["headers"] = headers
        return _Resp({"status": "ok", "body": {"added": [], "fixed": [], "improved": []}})

    with patch.object(chatbot_client.requests, "post", fake_post):
        out = chatbot_client.generate_release_note({"version": "2026.08.1", "changes": []})

    assert seen["url"].endswith("/api/v1/release-notes/generate")
    assert seen["json"]["strict"] is False
    assert seen["headers"]["Authorization"].startswith("Bearer ")
    assert out["status"] == "ok"


def test_generate_forwards_strict_and_complaint():
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen.update(json)
        return _Resp({"status": "ok", "body": {}})

    with patch.object(chatbot_client.requests, "post", fake_post):
        chatbot_client.generate_release_note({"version": "v"}, strict=True, complaint="sha uydurdun")

    assert seen["strict"] is True
    assert seen["complaint"] == "sha uydurdun"


@pytest.mark.parametrize(
    "boom",
    [requests.ConnectionError("down"), requests.Timeout("slow")],
)
def test_generate_returns_failed_instead_of_raising(boom):
    def fake_post(*a, **k):
        raise boom

    with patch.object(chatbot_client.requests, "post", fake_post):
        out = chatbot_client.generate_release_note({"version": "v"})

    assert out == {"status": "failed", "detail": "transport"}


def test_generate_returns_failed_on_http_error():
    with patch.object(chatbot_client.requests, "post", lambda *a, **k: _Resp({}, status=502)):
        assert chatbot_client.generate_release_note({"version": "v"})["status"] == "failed"


def test_generate_returns_failed_on_non_dict_json():
    with patch.object(chatbot_client.requests, "post", lambda *a, **k: _Resp(["liste"])):
        assert chatbot_client.generate_release_note({"version": "v"})["status"] == "failed"
