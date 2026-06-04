from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "chatbot-api"


def test_ready_does_not_leak_secrets():
    r = client.get("/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert "checks" in body
    # llm_configured is a boolean flag, never the key value.
    assert isinstance(body["checks"]["llm_configured"], bool)
    text = r.text.lower()
    assert "sk-" not in text
    assert "bearer " not in text
    assert "password" not in text
