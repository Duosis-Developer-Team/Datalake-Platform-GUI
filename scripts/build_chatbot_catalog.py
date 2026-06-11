#!/usr/bin/env python3
"""Optional helper to regenerate a lightweight chatbot catalog.

This script is intentionally conservative and should never scan `.env`, `.env.local`,
secret files, or print secrets. It can be extended by developers to inspect API
routes, api_client functions and query registry keys at build time.
"""
from __future__ import annotations

from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "services/chatbot-api/app/catalog/generated_catalog.json"

EXCLUDED = {".env", ".env.local"}


def find_fastapi_routes() -> list[str]:
    routes: list[str] = []
    for p in (ROOT / "services").glob("*/app/routers/*.py"):
        txt = p.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r"@router\.(get|post|put|delete)\(\s*['\"]([^'\"]+)", txt):
            routes.append(f"{p.relative_to(ROOT)}:{m.group(1).upper()} {m.group(2)}")
    return sorted(routes)


def main() -> None:
    data = {
        "generated_by": "scripts/build_chatbot_catalog.py",
        "fastapi_routes_sample": find_fastapi_routes(),
        "note": "Extend manually with curated MetricDefinition entries. Do not include secrets.",
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT}")

if __name__ == "__main__":
    main()
