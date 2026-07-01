"""Guard the k8s wiring that makes the shared cache actually shared (item 1.4).

If REDIS_URL is dropped from the frontend ConfigMap, cache_service silently
falls back to the per-pod in-process backend and the whole shared-cache fix
reverts with no error. This test fails loudly if that wiring regresses.
"""
import pathlib

import pytest

yaml = pytest.importorskip("yaml")

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(path):
    with open(ROOT / path) as fh:
        return yaml.safe_load(fh)


def test_frontend_configmap_sets_redis_url_to_redis_service():
    cm = _load("k8s/frontend/configmap.yaml")
    redis_url = cm["data"].get("REDIS_URL", "")
    assert "bulutistan-redis" in redis_url
    assert "6379" in redis_url
    assert redis_url.startswith("redis://")


def test_frontend_deployment_injects_the_configmap():
    dep = _load("k8s/frontend/deployment.yaml")
    container = dep["spec"]["template"]["spec"]["containers"][0]
    env_from_configmaps = {
        ref["configMapRef"]["name"]
        for ref in container.get("envFrom", [])
        if "configMapRef" in ref
    }
    assert "bulutistan-frontend-config" in env_from_configmaps
