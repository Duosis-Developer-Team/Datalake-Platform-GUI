"""Load proxy_assignment.yml catalog for DC / proxy topology."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.config import settings


@lru_cache(maxsize=1)
def load_proxy_catalog() -> dict[str, dict[str, Any]]:
    """Return {dc_key: {dc_code, proxies: [{id, proxy_nifi_host, ...}]}}."""
    path = Path(settings.proxy_assignment_path)
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    catalog: dict[str, dict[str, Any]] = {}
    for key, block in raw.items():
        if not isinstance(block, dict):
            continue
        dc_code = str(block.get("dc_code") or key).upper()
        proxies = block.get("proxies") or []
        catalog[dc_code] = {
            "dc_code": dc_code,
            "catalog_key": str(key),
            "proxies": [
                {
                    "id": str(p.get("id", "")),
                    "proxy_nifi_host": str(p.get("proxy_nifi_host", "")),
                    "ssh_user": str(p.get("ssh_user", "")),
                    "conf_path": str(p.get("conf_path", "")),
                    "gitea_audit_path": str(p.get("gitea_audit_path", "")),
                }
                for p in proxies
                if isinstance(p, dict) and p.get("id")
            ],
        }
    return catalog


def list_dc_codes() -> list[str]:
    catalog = load_proxy_catalog()
    return sorted(catalog.keys())


def proxies_for_dc(dc_code: str) -> list[dict[str, Any]]:
    block = load_proxy_catalog().get(dc_code.upper(), {})
    return list(block.get("proxies") or [])


def all_proxy_ids() -> list[str]:
    ids: list[str] = []
    for block in load_proxy_catalog().values():
        for p in block.get("proxies") or []:
            pid = p.get("id")
            if pid:
                ids.append(str(pid))
    return ids
