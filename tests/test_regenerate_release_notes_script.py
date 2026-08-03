"""regenerate_release_notes.py — HTTP mock'lanır."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "regenerate_release_notes.py"
_spec = importlib.util.spec_from_file_location("regenerate_release_notes", _PATH)
rr = importlib.util.module_from_spec(_spec)
sys.modules["regenerate_release_notes"] = rr
_spec.loader.exec_module(rr)

_NOTE = {"status": "draft", "headline": "Panel yenilendi", "body": {"added": [], "fixed": [], "improved": []}}


def test_version_flag_regenerates_and_confirms_with_yes():
    calls = []

    def fake_post(base, path, token, payload=None):
        calls.append(path)
        return {"note": _NOTE, "confirmed": True}

    with patch.object(rr, "_post", fake_post):
        rc = rr.main(["--version", "2026.08.1", "--yes", "--base-url", "http://x", "--token", "t"])

    assert rc == 0
    assert calls == [
        "/internal/platform/releases/2026.08.1/note/regenerate",
        "/internal/platform/releases/2026.08.1/note/confirm",
    ]


def test_preview_never_confirms():
    calls = []

    def fake_post(base, path, token, payload=None):
        calls.append(path)
        return {"note": _NOTE}

    with patch.object(rr, "_post", fake_post):
        rc = rr.main(["--version", "2026.08.1", "--preview", "--base-url", "http://x", "--token", "t"])

    assert rc == 0
    assert calls == ["/internal/platform/releases/2026.08.1/note/regenerate"]


def test_preview_prints_the_note(capsys):
    with patch.object(rr, "_post", lambda base, path, token, payload=None: {"note": _NOTE}):
        rr.main(["--version", "2026.08.1", "--preview", "--base-url", "http://x", "--token", "t"])
    assert "Panel yenilendi" in capsys.readouterr().out


def test_all_flag_walks_every_release():
    calls = []

    def fake_post(base, path, token, payload=None):
        calls.append(path)
        return {"note": _NOTE, "confirmed": True}

    with patch.object(rr, "_list_versions", lambda base, token: ["2026.08.1", "2026.07.1"]), \
         patch.object(rr, "_post", fake_post):
        rc = rr.main(["--all", "--yes", "--base-url", "http://x", "--token", "t"])

    assert rc == 0
    assert calls.count("/internal/platform/releases/2026.08.1/note/regenerate") == 1
    assert calls.count("/internal/platform/releases/2026.07.1/note/regenerate") == 1


def test_requires_version_or_all():
    assert rr.main(["--base-url", "http://x", "--token", "t"]) == 2


def test_requires_a_token():
    assert rr.main(["--version", "2026.08.1", "--base-url", "http://x", "--token", ""]) == 2


def test_interactive_no_answer_rejects():
    calls = []

    def fake_post(base, path, token, payload=None):
        calls.append(path)
        return {"note": _NOTE, "rejected": True}

    with patch.object(rr, "_post", fake_post), \
         patch.object(rr.sys.stdin, "isatty", lambda: True), \
         patch.object(rr, "_ask", lambda prompt: "h"):
        rr.main(["--version", "2026.08.1", "--base-url", "http://x", "--token", "t"])

    assert calls[-1].endswith("/reject")


def test_no_tty_without_yes_leaves_the_draft():
    calls = []

    with patch.object(rr, "_post", lambda base, path, token, payload=None: calls.append(path) or {"note": _NOTE}), \
         patch.object(rr.sys.stdin, "isatty", lambda: False):
        rr.main(["--version", "2026.08.1", "--base-url", "http://x", "--token", "t"])

    assert not any("confirm" in c for c in calls)
