"""Repoda gerçek token bulunmadığını ve yapılandırmanın bağlandığını doğrular."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]
_REF = _ROOT / "k8s" / "frontend" / "secret-reference.yaml"
_DEPLOY = _ROOT / "k8s" / "frontend" / "deployment.yaml"
_COMPOSE = _ROOT / "docker-compose.yml"


def test_secret_reference_holds_only_a_placeholder():
    doc = yaml.safe_load(_REF.read_text(encoding="utf-8"))
    value = doc["stringData"]["RELEASE_INGEST_TOKEN"]
    assert value == "REPLACE_WITH_REAL_TOKEN_OUTSIDE_GIT"


def test_secret_reference_carries_the_do_not_commit_warning():
    text = _REF.read_text(encoding="utf-8")
    assert "REFERENCE ONLY" in text


def test_no_long_random_looking_secret_in_the_reference():
    text = _REF.read_text(encoding="utf-8")
    assert not re.search(r"[A-Za-z0-9+/]{32,}={0,2}", text.replace("REPLACE_WITH_REAL_TOKEN_OUTSIDE_GIT", ""))


def test_frontend_deployment_mounts_the_secret_optionally():
    for doc in yaml.safe_load_all(_DEPLOY.read_text(encoding="utf-8")):
        if not doc or doc.get("kind") != "Deployment":
            continue
        container = doc["spec"]["template"]["spec"]["containers"][0]
        refs = [e.get("secretRef", {}).get("name") for e in container.get("envFrom") or []]
        assert "release-ingest-secret" in refs
        entry = [e for e in container["envFrom"] if e.get("secretRef", {}).get("name") == "release-ingest-secret"][0]
        # Secret yoksa pod başlamalı; endpoint kendi kendini 503'e kapatır.
        assert entry["secretRef"].get("optional") is True
        return
    raise AssertionError("frontend Deployment bulunamadı")


def test_compose_passes_the_token_through():
    doc = yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))
    env = doc["services"]["app"]["environment"]
    if isinstance(env, dict):
        assert "RELEASE_INGEST_TOKEN" in env
    else:
        assert any(str(item).startswith("RELEASE_INGEST_TOKEN") for item in env)
