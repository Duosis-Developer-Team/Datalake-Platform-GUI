#!/usr/bin/env python3
"""Yeni bir release açar ve notunu onaya sunar.

Kullanım:
    python scripts/new_release.py                 # etkileşimli
    python scripts/new_release.py --yes           # soru sormadan onayla
    python scripts/new_release.py --dry-run       # ağa çıkmadan commit'leri göster

Token `RELEASE_INGEST_TOKEN` ortam değişkeninden okunur; `--token` ile geçilebilir.
TTY yoksa taslak ONAYLANMADAN bırakılır — sessiz onay, insan onayı kuralını delerdi.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

import requests

_SEP = "\x1f"
_MAX_REGENERATE = 3
_BUCKET_LABELS = (("added", "Yenilikler"), ("fixed", "Düzeltmeler"), ("improved", "İyileştirmeler"))


def _git_log(rev_range: str) -> str:
    out = subprocess.run(
        ["git", "log", rev_range, "--reverse", "--no-merges", "--date=short",
         f"--pretty=format:%h{_SEP}%ad{_SEP}%s"],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout or ""


def read_commits(last_sha: str | None) -> list[dict]:
    rev_range = f"{last_sha}..HEAD" if last_sha else "HEAD"
    commits = []
    for line in _git_log(rev_range).splitlines():
        parts = line.split(_SEP)
        if len(parts) != 3:
            continue
        sha, day, subject = (p.strip() for p in parts)
        if not sha or not subject:
            continue
        commits.append({"sha": sha[:12], "date": day, "subject": subject})
    return commits


def _get_last_sha(base_url: str, token: str) -> str | None:
    resp = requests.get(
        f"{base_url}/internal/platform/releases/last-sha",
        headers={"X-Release-Token": token},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("last_sha")


def _post(base_url: str, path: str, token: str, payload: dict | None = None) -> dict:
    resp = requests.post(
        f"{base_url}{path}",
        json=payload,
        headers={"X-Release-Token": token},
        timeout=180,
    )
    resp.raise_for_status()
    return resp.json()


def render_note(note: dict) -> str:
    lines: list[str] = []
    headline = note.get("headline")
    if headline:
        lines.append(str(headline))
        lines.append("")
    body = note.get("body") or {}
    for key, label in _BUCKET_LABELS:
        items = body.get(key) or []
        if not items:
            continue
        lines.append(label)
        for item in items:
            shas = ", ".join(item.get("shas") or [])
            lines.append(f"  • {item.get('text', '')}  [{shas}]")
        lines.append("")
    if note.get("status") == "auto":
        lines.append("(model not üretemedi — bu bir otomatik özet)")
    if not lines:
        lines.append("(bu release için gösterilecek kullanıcıya dönük değişiklik yok)")
    return "\n".join(lines).rstrip()


def _ask(prompt: str) -> str:
    return input(prompt).strip().lower()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Yeni release aç ve notunu onayla.")
    ap.add_argument("--base-url", default=os.environ.get("GUI_BASE_URL", "http://localhost:8050"))
    ap.add_argument("--token", default=os.environ.get("RELEASE_INGEST_TOKEN", ""))
    ap.add_argument("--version", default=None, help="CalVer'i elle ver (varsayılan: otomatik)")
    ap.add_argument("--yes", action="store_true", help="soru sormadan onayla")
    ap.add_argument("--dry-run", action="store_true", help="ağa çıkma, commit'leri göster")
    args = ap.parse_args(argv)

    base = args.base_url.rstrip("/")

    if args.dry_run:
        commits = read_commits(None)
        print(f"{len(commits)} commit bulundu:")
        for c in commits:
            print(f"  {c['sha']}  {c['date']}  {c['subject']}")
        return 0

    if not args.token:
        print("RELEASE_INGEST_TOKEN tanımlı değil.", file=sys.stderr)
        return 2

    last_sha = _get_last_sha(base, args.token)
    commits = read_commits(last_sha)
    if not commits:
        print("Yeni commit yok; yapacak bir şey yok.")
        return 0

    payload: dict = {"commits": commits}
    if args.version:
        payload["version"] = args.version
    result = _post(base, "/internal/platform/releases", args.token, payload)
    version = result.get("version")
    note = result.get("note") or {}

    print(f"\nRelease {version} açıldı — {len(commits)} commit.\n")
    print(render_note(note))
    print()

    confirm_path = f"/internal/platform/releases/{version}/note/confirm"
    reject_path = f"/internal/platform/releases/{version}/note/reject"
    regenerate_path = f"/internal/platform/releases/{version}/note/regenerate"

    if args.yes:
        _post(base, confirm_path, args.token)
        print("Not yayına alındı.")
        return 0

    if not sys.stdin.isatty():
        print("TTY yok; taslak onaylanmadan bırakıldı. Panelde otomatik özet görünüyor.")
        return 0

    regenerated = 0
    while True:
        answer = _ask("Bu notu yayınlayalım mı? [e = evet / h = hayır / y = yeniden üret]: ")
        if answer == "e":
            _post(base, confirm_path, args.token)
            print("Not yayına alındı.")
            return 0
        if answer == "h":
            _post(base, reject_path, args.token)
            print("Taslak silindi; panelde otomatik özet kalıyor.")
            return 0
        if answer == "y":
            if regenerated >= _MAX_REGENERATE:
                _post(base, reject_path, args.token)
                print("Yeniden üretme hakkı bitti; taslak silindi.")
                return 0
            regenerated += 1
            note = (_post(base, regenerate_path, args.token) or {}).get("note") or {}
            print()
            print(render_note(note))
            print()
            continue
        print("e, h veya y yazın.")


if __name__ == "__main__":
    raise SystemExit(main())
