"""One-time backfill: reconstruct platform version history from git log.

Buckets commits into weekly CalVer releases (YYYY.MM.N) and writes them to
platform_releases / release_changes with source='backfill'. Idempotent on version.

Usage (from repo root, with auth DB env configured):
    python scripts/backfill_platform_versions.py           # write to DB
    python scripts/backfill_platform_versions.py --dry-run # print only
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date

_PREFIX_RE = re.compile(r"^(feat|fix|perf|chore|docs|refactor|test|style|build|ci)(\(([^)]+)\))?!?:\s*(.*)$")
_KNOWN = {"feat", "fix", "perf", "chore", "docs", "refactor"}


def calver(year: int, month: int, seq: int) -> str:
    return f"{year}.{month:02d}.{seq}"


def parse_commits(log_text: str) -> list[dict]:
    commits = []
    for line in log_text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\x1f")
        if len(parts) != 3:
            continue
        sha, iso, subject = parts
        m = _PREFIX_RE.match(subject.strip())
        if m:
            ctype = m.group(1)
            scope = m.group(3)
            summary = m.group(4).strip()
            if ctype not in _KNOWN:
                ctype = "other"
        else:
            ctype, scope, summary = "other", None, subject.strip()
        y, mo, d = (int(x) for x in iso.split("-"))
        commits.append({
            "sha": sha.strip()[:40],
            "date": date(y, mo, d),
            "change_type": ctype,
            "scope": scope,
            "summary": summary,
        })
    return commits


def bucket_weekly(commits: list[dict]) -> list[dict]:
    by_week: dict[tuple[int, int], list[dict]] = {}
    for c in commits:
        iso = c["date"].isocalendar()
        by_week.setdefault((iso[0], iso[1]), []).append(c)
    releases = []
    month_seq: dict[tuple[int, int], int] = {}
    for key in sorted(by_week):
        group = by_week[key]
        rep = min(c["date"] for c in group)  # first day of activity in the week
        ym = (rep.year, rep.month)
        month_seq[ym] = month_seq.get(ym, 0) + 1
        releases.append({
            "version": calver(rep.year, rep.month, month_seq[ym]),
            "released_at": rep.isoformat(),
            "changes": [
                {"change_type": c["change_type"], "summary": c["summary"],
                 "commit_sha": c["sha"][:12], "scope": c["scope"]}
                for c in group
            ],
        })
    return releases


def read_git_log() -> str:
    return subprocess.check_output(
        ["git", "log", "--reverse", "--date=short", "--pretty=format:%h\x1f%ad\x1f%s"],
        text=True,
    )


def write_releases(releases: list[dict]) -> None:
    from src.auth import db
    for r in releases:
        db.execute(
            """
            INSERT INTO platform_releases (version, released_at, source)
            VALUES (%s, %s, 'backfill')
            ON CONFLICT (version) DO NOTHING
            """,
            (r["version"], r["released_at"]),
        )
        row = db.fetch_one("SELECT id FROM platform_releases WHERE version = %s", (r["version"],))
        if not row:
            continue
        rid = row["id"]
        # Avoid duplicate change rows on re-run.
        existing = db.fetch_one("SELECT COUNT(*) AS n FROM release_changes WHERE release_id = %s", (rid,))
        if existing and int(existing["n"]) > 0:
            continue
        for c in r["changes"]:
            db.execute(
                """
                INSERT INTO release_changes (release_id, change_type, summary, commit_sha, scope)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (rid, c["change_type"], c["summary"], c["commit_sha"], c["scope"]),
            )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    releases = bucket_weekly(parse_commits(read_git_log()))
    if args.dry_run:
        for r in releases:
            print(f"{r['version']}  {r['released_at']}  ({len(r['changes'])} changes)")
        print(f"\nTotal: {len(releases)} releases")
        return 0
    write_releases(releases)
    print(f"Backfilled {len(releases)} releases.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
