"""release-notes router sözleşmesi — LLM mock'lanır."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import app
from app.routers import release_notes as router_mod
from app.services.llm_client import LLMError, LLMResult

client = TestClient(app)

_REQ = {
    "version": "2026.08.1",
    "released_at": "2026-08-03",
    "changes": [
        {"change_type": "feat", "summary": "yeni panel", "sha": "aaaaaaaaaaaa", "scope": "panel"},
    ],
}


def _mock_llm(monkeypatch, answer=None, error=None):
    class _FakeLLM:
        def __init__(self):
            self.seen = []
            self.kwargs = {}

        def complete(self, messages, model=None, **kwargs):
            self.seen.append(messages)
            self.kwargs = kwargs
            if error is not None:
                raise error
            return LLMResult(answer=answer, model="gpt-oss-120b", usage={})

    fake = _FakeLLM()
    monkeypatch.setattr(router_mod, "get_llm_client", lambda: fake)
    return fake


def test_generate_returns_parsed_body(monkeypatch):
    _mock_llm(
        monkeypatch,
        answer=json.dumps(
            {
                "headline": "Panel yenilendi",
                "added": [{"text": "Yeni panel eklendi", "shas": ["aaaaaaaaaaaa"]}],
                "fixed": [],
                "improved": [],
            },
            ensure_ascii=False,
        ),
    )
    r = client.post("/api/v1/release-notes/generate", json=_REQ)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["headline"] == "Panel yenilendi"
    assert data["body"]["added"][0]["shas"] == ["aaaaaaaaaaaa"]
    assert data["model"] == "gpt-oss-120b"


def test_generate_strips_code_fence(monkeypatch):
    _mock_llm(
        monkeypatch,
        answer='```json\n{"headline": "X", "added": [], "fixed": [], "improved": []}\n```',
    )
    data = client.post("/api/v1/release-notes/generate", json=_REQ).json()
    assert data["status"] == "ok"
    assert data["body"] == {"added": [], "fixed": [], "improved": []}


def test_generate_reports_failed_on_unparsable_answer(monkeypatch):
    _mock_llm(monkeypatch, answer="Tabii, işte release note'unuz!")
    r = client.post("/api/v1/release-notes/generate", json=_REQ)
    assert r.status_code == 200
    assert r.json()["status"] == "failed"
    assert r.json()["detail"] == "unparsable"


def test_generate_asks_for_enough_tokens_to_finish_the_json(monkeypatch):
    """Kesilen çıktı `unparsable` diye görünür, `truncated` diye değil.

    192 commit'lik bir sürümde 1200 token yetmiyor ve JSON yarım kalıyordu; üç
    denemenin üçü de aynı sebeple düşüyordu. Sınırı burada sabitliyoruz ki bir
    daha sessizce daraltılmasın.
    """
    fake = _mock_llm(monkeypatch, answer='{"added": [], "fixed": [], "improved": []}')
    client.post("/api/v1/release-notes/generate", json=_REQ)
    assert fake.kwargs["max_tokens"] >= 4000


def test_system_prompt_caps_bullets_so_output_cannot_grow_with_commit_count(monkeypatch):
    """Token sınırını yükseltmek tek başına yetmez: 192 maddelik bir not zaten
    kullanıcıya bir şey anlatmaz. Asıl tavan kova başına madde sayısında."""
    fake = _mock_llm(monkeypatch, answer='{"added": [], "fixed": [], "improved": []}')
    client.post("/api/v1/release-notes/generate", json=_REQ)
    system = fake.seen[0][0]["content"]
    assert "en fazla 8 madde" in system


def test_unparsable_answer_is_logged_with_its_tail(monkeypatch, caplog):
    """Kuyruk loglanmazsa kesilme ile saçmalama ayırt edilemiyor.

    Sunucuda `unparsable` gördüğümüzde elimizde sebebi gösterecek hiçbir şey yoktu.
    """
    truncated = '{"headline": "X", "added": [{"text": "yarım kalan madde'
    _mock_llm(monkeypatch, answer=truncated)
    with caplog.at_level("WARNING"):
        data = client.post("/api/v1/release-notes/generate", json=_REQ).json()
    assert data["detail"] == "unparsable"
    assert "yarım kalan madde" in caplog.text
    assert "chars=" in caplog.text


def test_generate_reports_failed_on_llm_error(monkeypatch):
    _mock_llm(monkeypatch, error=LLMError("upstream", "servis yanıt vermedi", "502"))
    r = client.post("/api/v1/release-notes/generate", json=_REQ)
    assert r.status_code == 200
    assert r.json()["status"] == "failed"
    assert r.json()["detail"] == "upstream"


def test_strict_mode_changes_the_system_prompt(monkeypatch):
    fake = _mock_llm(monkeypatch, answer='{"added": [], "fixed": [], "improved": []}')
    client.post("/api/v1/release-notes/generate", json={**_REQ, "strict": True})
    system = fake.seen[0][0]["content"]
    assert "KATI MOD" in system


def test_complaint_is_appended_to_the_user_message(monkeypatch):
    fake = _mock_llm(monkeypatch, answer='{"added": [], "fixed": [], "improved": []}')
    client.post(
        "/api/v1/release-notes/generate",
        json={**_REQ, "complaint": "Listede olmayan sha kullandın: zzz."},
    )
    user = fake.seen[0][1]["content"]
    assert "Listede olmayan sha kullandın" in user


def test_missing_buckets_are_filled_with_empty_lists(monkeypatch):
    _mock_llm(monkeypatch, answer='{"headline": "X", "added": [{"text": "a", "shas": []}]}')
    body = client.post("/api/v1/release-notes/generate", json=_REQ).json()["body"]
    assert body["fixed"] == []
    assert body["improved"] == []
