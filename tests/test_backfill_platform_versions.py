"""Backfill parsing/bucketing is deterministic on a fixed git-log sample."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "backfill_platform_versions",
    Path(__file__).resolve().parents[1] / "scripts" / "backfill_platform_versions.py",
)
bf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bf)

# Format: <sha>\x1f<iso-date>\x1f<subject>
SAMPLE = "\n".join([
    "a1\x1f2026-02-19\x1fİlk commit: db",
    "a2\x1f2026-02-20\x1ffeat(gui): add overview",
    "a3\x1f2026-02-21\x1ffix: null guard",
    "b1\x1f2026-03-02\x1ffeat(crm): mapping",
    "b2\x1f2026-03-03\x1fchore: bump",
])


def test_calver_format():
    assert bf.calver(2026, 7, 3) == "2026.07.3"


def test_parse_commits_extracts_type_and_scope():
    commits = bf.parse_commits(SAMPLE)
    assert commits[1]["change_type"] == "feat"
    assert commits[1]["scope"] == "gui"
    assert commits[1]["summary"] == "add overview"
    assert commits[2]["change_type"] == "fix"


def test_bucket_weekly_groups_into_releases():
    commits = bf.parse_commits(SAMPLE)
    releases = bf.bucket_weekly(commits)
    # Feb 19-21 fall in one ISO week; Mar 2-3 in a later week → 2 releases.
    assert len(releases) == 2
    assert releases[0]["version"] == "2026.02.1"
    assert releases[1]["version"].startswith("2026.03.")
    # Each release carries its change list.
    assert any(c["change_type"] == "feat" for c in releases[0]["changes"])
