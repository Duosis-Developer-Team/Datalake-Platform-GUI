"""Every service must own its Redis database.

datacenter-api shipped without REDIS_DB, so it defaulted to db 0 — the same
database the GUI writes its `dl:fecache:*` keys into — and its admin cache
refresh flushes with a bare `*`. One operator refresh therefore wiped the GUI's
entire cache (measured: 1390 keys -> 9). These tests pin the separation at the
two places it can regress: the service default and the compose wiring.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _compose_text() -> str:
    return (ROOT / "docker-compose.yml").read_text(encoding="utf-8")


def _service_block(name: str) -> str:
    text = _compose_text()
    block = text.split(f"\n  {name}:\n", 1)[1]
    # Next top-level service starts at column 2; stop there.
    match = re.search(r"\n  [a-z0-9-]+:\n", block)
    return block[: match.start()] if match else block


def _redis_db_of(service: str) -> str | None:
    match = re.search(r'^\s+REDIS_DB:\s*"?([0-9]+)"?', _service_block(service), re.MULTILINE)
    return match.group(1) if match else None


GUI_REDIS_DB = "0"


@pytest.mark.parametrize(
    "service,expected",
    [("customer-api", "1"), ("crm-engine", "2"), ("datacenter-api", "3")],
)
def test_each_api_declares_its_own_redis_db(service, expected):
    assert _redis_db_of(service) == expected


def test_no_api_shares_the_guis_redis_db():
    """db 0 belongs to the GUI (REDIS_URL=redis://redis:6379/0)."""
    for service in ("customer-api", "crm-engine", "datacenter-api"):
        assert _redis_db_of(service) != GUI_REDIS_DB, f"{service} would share the GUI's cache"


def test_gui_still_points_at_db_zero():
    assert "REDIS_URL: ${REDIS_URL:-redis://redis:6379/0}" in _compose_text()


def test_crm_engine_reads_datacenter_cache_from_datacenter_db():
    """crm-engine reads dc_details keys out of datacenter-api's database directly,
    so moving datacenter-api must move this pointer with it."""
    match = re.search(
        r'^\s+DATACENTER_REDIS_DB:\s*"?([0-9]+)"?', _service_block("crm-engine"), re.MULTILINE
    )
    assert match is not None, "crm-engine must declare DATACENTER_REDIS_DB"
    assert match.group(1) == _redis_db_of("datacenter-api")


def test_datacenter_api_default_redis_db_is_not_the_guis():
    """The default matters on its own: the k8s manifests do not set REDIS_DB."""
    text = (ROOT / "services/datacenter-api/app/config.py").read_text(encoding="utf-8")
    match = re.search(r"^\s+redis_db:\s*int\s*=\s*([0-9]+)", text, re.MULTILINE)
    assert match is not None
    assert match.group(1) != GUI_REDIS_DB


def test_k8s_configmaps_declare_the_same_split_as_compose():
    """Production reads the manifests, not docker-compose.yml.

    datacenter-api's configmap set REDIS_HOST and REDIS_PORT but no REDIS_DB,
    so prod silently inherited whatever app/config.py defaulted to — which is how
    it ended up sharing db 0 with the frontend. Pinning it here keeps the two
    descriptions of the same system from drifting apart again.
    """
    for service, expected in (("datacenter-api", "3"), ("customer-api", "1")):
        text = (ROOT / f"k8s/{service}/configmap.yaml").read_text(encoding="utf-8")
        match = re.search(r'^\s+REDIS_DB:\s*"?([0-9]+)"?', text, re.MULTILINE)
        assert match is not None, f"k8s/{service} must declare REDIS_DB explicitly"
        assert match.group(1) == expected
        assert match.group(1) == _redis_db_of(service), "k8s and compose disagree"


def test_k8s_frontend_keeps_db_zero():
    text = (ROOT / "k8s/frontend/configmap.yaml").read_text(encoding="utf-8")
    assert 'REDIS_URL: "redis://bulutistan-redis:6379/0"' in text


def test_crm_engine_default_datacenter_db_matches_datacenter_api_default():
    dc_text = (ROOT / "services/datacenter-api/app/config.py").read_text(encoding="utf-8")
    crm_text = (ROOT / "services/crm-engine/app/main.py").read_text(encoding="utf-8")

    dc_default = re.search(r"^\s+redis_db:\s*int\s*=\s*([0-9]+)", dc_text, re.MULTILINE).group(1)
    crm_default = re.search(
        r'_DATACENTER_REDIS_DB\s*=\s*int\(os\.getenv\("DATACENTER_REDIS_DB",\s*"([0-9]+)"\)\)',
        crm_text,
    ).group(1)

    assert crm_default == dc_default
