"""Sanity checks for docker-compose microservice layout (no PyYAML dependency)."""

from pathlib import Path


def _compose_text() -> str:
    root = Path(__file__).resolve().parents[1]
    return (root / "docker-compose.yml").read_text(encoding="utf-8")


def test_docker_compose_builds_three_apis_from_services_dirs() -> None:
    text = _compose_text()
    assert "context: ./services/datacenter-api" in text
    assert "context: ./services/customer-api" in text
    assert "context: ./services/query-api" in text


def test_docker_compose_does_not_reference_missing_backend_folder() -> None:
    text = _compose_text()
    assert "build: ./backend" not in text
    assert "./backend" not in text


def test_docker_compose_defines_datalake_network_and_app_api_urls() -> None:
    text = _compose_text()
    assert "datalake:" in text
    assert "DATACENTER_API_URL" in text
    assert "http://datacenter-api:8000" in text
    assert "microservice" in text
