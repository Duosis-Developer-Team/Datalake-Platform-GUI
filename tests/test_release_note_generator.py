"""Üretim merdiveni — DB ve chatbot-api mock'lanır."""

from __future__ import annotations

from unittest.mock import patch

from src.services import release_note_generator as gen

SHA_A = "aaaaaaaaaaaa"
SHA_B = "bbbbbbbbbbbb"

_RELEASE = {
    "id": 7,
    "version": "2026.08.1",
    "released_at": "2026-08-03",
    "changes": [
        {"change_type": "feat", "summary": "yeni panel", "commit_sha": SHA_A, "scope": "panel"},
        {"change_type": "fix", "summary": "rozet düzeltildi", "commit_sha": SHA_B, "scope": None},
    ],
}


class _Recorder:
    def __init__(self, existing_note=None):
        self.upserts: list[dict] = []
        self.drafts: list[dict] = []
        self.existing_note = existing_note

    def get_release(self, release_id):
        return dict(_RELEASE) if release_id == 7 else None

    def get_release_note(self, release_id):
        return self.existing_note

    def upsert_note(self, release_id, **kw):
        self.upserts.append(kw)

    def set_draft_note(self, release_id, **kw):
        self.drafts.append(kw)


def _install(rec, responses):
    calls = {"n": 0, "sent": []}

    def fake_generate(payload, *, strict=False, complaint=None, model=None):
        calls["sent"].append({"strict": strict, "complaint": complaint})
        i = min(calls["n"], len(responses) - 1)
        calls["n"] += 1
        return responses[i]

    ctx = patch.multiple(
        gen.versions_crud,
        get_release=rec.get_release,
        get_release_note=rec.get_release_note,
        upsert_note=rec.upsert_note,
        set_draft_note=rec.set_draft_note,
    )
    ctx2 = patch.object(gen.chatbot_client, "generate_release_note", fake_generate)
    return ctx, ctx2, calls


def _ok(added_text="Yeni panel eklendi", sha=SHA_A, headline="Panel yenilendi"):
    return {
        "status": "ok",
        "headline": headline,
        "model": "gpt-oss-120b",
        "body": {"added": [{"text": added_text, "shas": [sha]}], "fixed": [], "improved": []},
    }


def test_body_is_written_before_any_llm_call():
    rec = _Recorder()
    ctx, ctx2, _ = _install(rec, [{"status": "failed", "detail": "upstream"}])
    with ctx, ctx2:
        out = gen.generate_for_release(7)
    assert rec.upserts[0]["source"] == "auto"
    assert rec.upserts[0]["body"]["added"][0]["text"] == "Yeni panel"
    assert out["status"] == "auto"
    assert out["body"]["fixed"][0]["text"] == "Rozet düzeltildi"


def test_deterministic_body_is_persisted_before_the_first_llm_call():
    """Sıra kritik: LLM çağrısı patlasa bile panelde hazır bir not durmalı."""
    rec = _Recorder()
    order: list[str] = []
    ctx, ctx2, _ = _install(rec, [_ok()])
    with ctx, ctx2:
        with patch.object(
            gen.versions_crud, "upsert_note", lambda rid, **kw: order.append("upsert")
        ), patch.object(
            gen.chatbot_client,
            "generate_release_note",
            lambda payload, **kw: order.append("llm") or _ok(),
        ):
            gen.generate_for_release(7)
    assert order[0] == "upsert"
    assert "llm" in order


def test_successful_first_attempt_writes_draft_only():
    rec = _Recorder()
    ctx, ctx2, calls = _install(rec, [_ok()])
    with ctx, ctx2:
        out = gen.generate_for_release(7)
    assert calls["n"] == 1
    assert out["status"] == "draft"
    assert rec.drafts[0]["draft_body"]["added"][0]["text"] == "Yeni panel eklendi"
    assert rec.drafts[0]["model"] == "gpt-oss-120b"
    # Yayındaki body hâlâ deterministik nottur; taslak onaylanana kadar değişmez.
    assert len(rec.upserts) == 1


def test_hallucinated_sha_triggers_repair_round_with_complaint():
    rec = _Recorder()
    bad = {
        "status": "ok",
        "headline": "X",
        "model": "m",
        "body": {
            "added": [{"text": "uydurma", "shas": ["cccccccccccc"]}],
            "fixed": [],
            "improved": [],
        },
    }
    ctx, ctx2, calls = _install(rec, [bad, _ok()])
    with ctx, ctx2:
        out = gen.generate_for_release(7)
    assert calls["n"] == 2
    assert "cccccccccccc" in calls["sent"][1]["complaint"]
    assert out["status"] == "draft"


def test_third_attempt_runs_in_strict_mode():
    rec = _Recorder()
    bad = {
        "status": "ok",
        "headline": None,
        "model": "m",
        "body": {"added": [], "fixed": [], "improved": []},
    }
    ctx, ctx2, calls = _install(rec, [bad, bad, _ok()])
    with ctx, ctx2:
        gen.generate_for_release(7)
    assert calls["sent"][2]["strict"] is True


def test_all_attempts_failing_falls_back_to_deterministic_note():
    rec = _Recorder()
    dud = {"status": "failed", "detail": "upstream"}
    ctx, ctx2, calls = _install(rec, [dud, dud, dud])
    with ctx, ctx2:
        out = gen.generate_for_release(7)
    assert calls["n"] == 3
    assert rec.drafts == []
    assert out["status"] == "auto"
    assert out["body"]["added"][0]["text"] == "Yeni panel"


def test_confirmed_note_is_never_overwritten():
    rec = _Recorder(existing_note={"release_id": 7, "source": "model", "body": {"added": []}})
    ctx, ctx2, _ = _install(rec, [_ok()])
    with ctx, ctx2:
        gen.generate_for_release(7)
    assert rec.upserts == []  # yayındaki insan onaylı nota dokunulmadı
    assert len(rec.drafts) == 1  # yalnızca taslak yazıldı


def test_auto_note_is_refreshed_when_new_commits_arrive():
    rec = _Recorder(existing_note={"release_id": 7, "source": "auto", "body": {"added": []}})
    ctx, ctx2, _ = _install(rec, [{"status": "failed", "detail": "upstream"}])
    with ctx, ctx2:
        gen.generate_for_release(7)
    assert len(rec.upserts) == 1
    assert len(rec.upserts[0]["body"]["added"]) == 1


def test_unknown_release_raises():
    rec = _Recorder()
    ctx, ctx2, _ = _install(rec, [_ok()])
    with ctx, ctx2:
        try:
            gen.generate_for_release(999)
        except ValueError as exc:
            assert "999" in str(exc)
        else:
            raise AssertionError("ValueError bekleniyordu")
