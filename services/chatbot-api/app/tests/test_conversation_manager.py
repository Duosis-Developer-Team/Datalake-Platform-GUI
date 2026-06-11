from app.models.schemas import ChatMessage
from app.services.conversation_manager import prepare_conversation, _truncate_fallback


def test_prepare_conversation_keeps_recent_when_short():
    conv = [
        ChatMessage(role="user", content="DC13 VM cpu"),
        ChatMessage(role="assistant", content="liste..."),
    ]
    recent, summary = prepare_conversation(conv, "follow-up?", fixed_overhead_chars=5000)
    assert summary is None
    assert len(recent) == 2


def test_prepare_conversation_summarizes_older_when_long(monkeypatch):
    from app.services import conversation_manager as cm

    monkeypatch.setattr(cm.settings, "chatbot_conversation_keep_recent", 2)
    monkeypatch.setattr(cm.settings, "max_context_chars", 500)
    monkeypatch.setattr(cm.settings, "max_history_chars", 200)
    monkeypatch.setattr(cm, "_summarize_older_turns", lambda older: "ozet: DC13 konusuldu")

    conv = [
        ChatMessage(role="user", content="A" * 100),
        ChatMessage(role="assistant", content="B" * 100),
        ChatMessage(role="user", content="C" * 100),
        ChatMessage(role="assistant", content="D" * 100),
        ChatMessage(role="user", content="E" * 100),
        ChatMessage(role="assistant", content="F" * 100),
    ]
    recent, summary = prepare_conversation(conv, "yeni soru", fixed_overhead_chars=300)
    assert summary == "ozet: DC13 konusuldu"
    assert len(recent) <= 4


def test_truncate_fallback():
    msgs = [ChatMessage(role="user", content="x" * 500)]
    out = _truncate_fallback(msgs, max_chars=100)
    assert len(out) <= 100
