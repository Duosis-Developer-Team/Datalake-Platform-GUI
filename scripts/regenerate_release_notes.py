#!/usr/bin/env python3
"""Var olan release'lerin notunu yeniden üretir.

Kullanım:
    python scripts/regenerate_release_notes.py --version 2026.08.1
    python scripts/regenerate_release_notes.py --version 2026.08.1 --preview
    python scripts/regenerate_release_notes.py --all --yes

--preview yalnızca üretir ve gösterir; taslak sunucuda kalır, panel değişmez.
"""

from __future__ import annotations

import argparse
import os
import sys

import requests

_BUCKET_LABELS = (("added", "Yenilikler"), ("fixed", "Düzeltmeler"), ("improved", "İyileştirmeler"))


def _post(base_url: str, path: str, token: str, payload: dict | None = None) -> dict:
    resp = requests.post(
        f"{base_url}{path}", json=payload, headers={"X-Release-Token": token}, timeout=180
    )
    resp.raise_for_status()
    return resp.json()


def _list_versions(base_url: str, token: str) -> list[str]:
    resp = requests.get(
        f"{base_url}/internal/platform/releases/versions",
        headers={"X-Release-Token": token},
        timeout=30,
    )
    resp.raise_for_status()
    return [str(v) for v in (resp.json().get("versions") or []) if str(v).strip()]


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
        lines.append("(gösterilecek kullanıcıya dönük değişiklik yok)")
    return "\n".join(lines).rstrip()


def _ask(prompt: str) -> str:
    return input(prompt).strip().lower()


def _handle_one(base: str, version: str, token: str, *, preview: bool, auto_yes: bool) -> None:
    note = (_post(base, f"/internal/platform/releases/{version}/note/regenerate", token) or {}).get("note") or {}
    print(f"\n--- {version} ---")
    print(render_note(note))
    print()
    if preview:
        print("(önizleme: taslak onaylanmadı)")
        return
    if auto_yes:
        _post(base, f"/internal/platform/releases/{version}/note/confirm", token)
        print("Not yayına alındı.")
        return
    if not sys.stdin.isatty():
        print("TTY yok; taslak onaylanmadan bırakıldı.")
        return
    while True:
        answer = _ask("Yayınlayalım mı? [e = evet / h = hayır]: ")
        if answer == "e":
            _post(base, f"/internal/platform/releases/{version}/note/confirm", token)
            print("Not yayına alındı.")
            return
        if answer == "h":
            _post(base, f"/internal/platform/releases/{version}/note/reject", token)
            print("Taslak silindi.")
            return
        print("e veya h yazın.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Release note'ları yeniden üret.")
    ap.add_argument("--base-url", default=os.environ.get("GUI_BASE_URL", "http://localhost:8050"))
    ap.add_argument("--token", default=os.environ.get("RELEASE_INGEST_TOKEN", ""))
    ap.add_argument("--version", default=None)
    ap.add_argument("--all", action="store_true", help="kayıtlı her sürüm için çalıştır")
    ap.add_argument("--preview", action="store_true", help="üret ve göster, onaylama")
    ap.add_argument("--yes", action="store_true", help="soru sormadan onayla")
    args = ap.parse_args(argv)

    if not args.version and not args.all:
        print("--version veya --all gerekli.", file=sys.stderr)
        return 2
    if not args.token:
        print("RELEASE_INGEST_TOKEN tanımlı değil.", file=sys.stderr)
        return 2

    base = args.base_url.rstrip("/")
    versions = [args.version] if args.version else _list_versions(base, args.token)
    for version in versions:
        _handle_one(base, str(version).strip(), args.token, preview=args.preview, auto_yes=args.yes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
