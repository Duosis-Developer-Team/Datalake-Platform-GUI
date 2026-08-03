"""new_release.py — git ve HTTP mock'lanır."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "new_release.py"
_spec = importlib.util.spec_from_file_location("new_release", _PATH)
nr = importlib.util.module_from_spec(_spec)
sys.modules["new_release"] = nr
_spec.loader.exec_module(nr)


_LOG = "aaaaaaaaaaaa\x1f2026-08-03\x1ffeat(panel): yeni rozet\nbbbbbbbbbbbb\x1f2026-08-03\x1ffix: hiza"


def test_read_commits_parses_unit_separated_log():
    with patch.object(nr, "_git_log", lambda rng: _LOG):
        commits = nr.read_commits("cccccccccccc")
    assert commits[0] == {
        "sha": "aaaaaaaaaaaa",
        "date": "2026-08-03",
        "subject": "feat(panel): yeni rozet",
    }
    assert len(commits) == 2


def test_read_commits_range_starts_from_last_sha():
    seen = {}
    with patch.object(nr, "_git_log", lambda rng: seen.setdefault("rng", rng) or ""):
        nr.read_commits("cccccccccccc")
    assert seen["rng"] == "cccccccccccc..HEAD"


def test_read_commits_without_last_sha_reads_whole_history():
    seen = {}
    with patch.object(nr, "_git_log", lambda rng: seen.setdefault("rng", rng) or ""):
        nr.read_commits(None)
    assert seen["rng"] == "HEAD"


def test_read_commits_skips_malformed_lines():
    with patch.object(nr, "_git_log", lambda rng: "bozuk satır\n" + _LOG):
        assert len(nr.read_commits(None)) == 2


def test_render_note_lists_buckets_in_turkish():
    text = nr.render_note(
        {
            "status": "draft",
            "headline": "Panel yenilendi",
            "body": {
                "added": [{"text": "Yeni rozet", "shas": ["aaaaaaaaaaaa"]}],
                "fixed": [{"text": "Hiza düzeltildi", "shas": ["bbbbbbbbbbbb"]}],
                "improved": [],
            },
        }
    )
    assert "Panel yenilendi" in text
    assert "Yenilikler" in text
    assert "Düzeltmeler" in text
    assert "Yeni rozet" in text
    assert "İyileştirmeler" not in text     # boş kova hiç yazılmaz


def test_render_note_marks_the_automatic_fallback():
    text = nr.render_note({"status": "auto", "headline": None, "body": {"added": [], "fixed": [], "improved": []}})
    assert "otomatik özet" in text.lower()


def test_dry_run_posts_nothing(capsys):
    with patch.object(nr, "_get_last_sha", lambda base, token: None), \
         patch.object(nr, "_git_log", lambda rng: _LOG), \
         patch.object(nr, "_post", lambda *a, **k: pytest_fail_marker()):
        rc = nr.main(["--dry-run", "--base-url", "http://x", "--token", "t"])
    assert rc == 0
    assert "yeni rozet" in capsys.readouterr().out


def pytest_fail_marker():
    raise AssertionError("--dry-run modunda ağa çıkılmamalı")


def test_yes_flag_confirms_without_prompting():
    calls = []

    def fake_post(base, path, token, payload=None):
        calls.append(path)
        if path == "/internal/platform/releases":
            return {"version": "2026.08.1", "note": {"status": "draft", "headline": "H", "body": {}}}
        return {"confirmed": True}

    with patch.object(nr, "_get_last_sha", lambda base, token: None), \
         patch.object(nr, "_git_log", lambda rng: _LOG), \
         patch.object(nr, "_post", fake_post):
        rc = nr.main(["--yes", "--base-url", "http://x", "--token", "t"])

    assert rc == 0
    assert "/internal/platform/releases/2026.08.1/note/confirm" in calls


def test_no_tty_leaves_the_draft_unconfirmed():
    calls = []

    def fake_post(base, path, token, payload=None):
        calls.append(path)
        return {"version": "2026.08.1", "note": {"status": "draft", "headline": "H", "body": {}}}

    with patch.object(nr, "_get_last_sha", lambda base, token: None), \
         patch.object(nr, "_git_log", lambda rng: _LOG), \
         patch.object(nr, "_post", fake_post), \
         patch.object(nr.sys.stdin, "isatty", lambda: False):
        rc = nr.main(["--base-url", "http://x", "--token", "t"])

    assert rc == 0
    assert not any("confirm" in c for c in calls)


def test_regenerate_answer_calls_regenerate_then_confirms():
    calls = []
    answers = iter(["y", "e"])

    def fake_post(base, path, token, payload=None):
        calls.append(path)
        if path.endswith("/regenerate"):
            return {"note": {"status": "draft", "headline": "H2", "body": {}}}
        if path == "/internal/platform/releases":
            return {"version": "2026.08.1", "note": {"status": "draft", "headline": "H", "body": {}}}
        return {"confirmed": True}

    with patch.object(nr, "_get_last_sha", lambda base, token: None), \
         patch.object(nr, "_git_log", lambda rng: _LOG), \
         patch.object(nr, "_post", fake_post), \
         patch.object(nr.sys.stdin, "isatty", lambda: True), \
         patch.object(nr, "_ask", lambda prompt: next(answers)):
        rc = nr.main(["--base-url", "http://x", "--token", "t"])

    assert rc == 0
    assert calls.count("/internal/platform/releases/2026.08.1/note/regenerate") == 1
    assert calls[-1].endswith("/confirm")


def test_no_answer_rejects_the_draft():
    calls = []

    def fake_post(base, path, token, payload=None):
        calls.append(path)
        if path == "/internal/platform/releases":
            return {"version": "2026.08.1", "note": {"status": "draft", "headline": "H", "body": {}}}
        return {"rejected": True}

    with patch.object(nr, "_get_last_sha", lambda base, token: None), \
         patch.object(nr, "_git_log", lambda rng: _LOG), \
         patch.object(nr, "_post", fake_post), \
         patch.object(nr.sys.stdin, "isatty", lambda: True), \
         patch.object(nr, "_ask", lambda prompt: "h"):
        nr.main(["--base-url", "http://x", "--token", "t"])

    assert calls[-1].endswith("/reject")


def test_regenerate_is_capped_at_three_attempts():
    calls = []

    def fake_post(base, path, token, payload=None):
        calls.append(path)
        if path == "/internal/platform/releases":
            return {"version": "2026.08.1", "note": {"status": "draft", "headline": "H", "body": {}}}
        return {"note": {"status": "draft", "headline": "H", "body": {}}, "rejected": True}

    with patch.object(nr, "_get_last_sha", lambda base, token: None), \
         patch.object(nr, "_git_log", lambda rng: _LOG), \
         patch.object(nr, "_post", fake_post), \
         patch.object(nr.sys.stdin, "isatty", lambda: True), \
         patch.object(nr, "_ask", lambda prompt: "y"):
        nr.main(["--base-url", "http://x", "--token", "t"])

    assert calls.count("/internal/platform/releases/2026.08.1/note/regenerate") == 3


def test_no_new_commits_exits_cleanly(capsys):
    with patch.object(nr, "_get_last_sha", lambda base, token: "aaaaaaaaaaaa"), \
         patch.object(nr, "_git_log", lambda rng: ""):
        rc = nr.main(["--base-url", "http://x", "--token", "t"])
    assert rc == 0
    assert "yeni commit yok" in capsys.readouterr().out.lower()
