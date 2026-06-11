"""Sanity checks for docker-compose microservice layout (no PyYAML dependency)."""

from pathlib import Path


def _compose_text() -> str:
    root = Path(__file__).resolve().parents[1]
    return (root / "docker-compose.yml").read_text(encoding="utf-8")


def test_docker_compose_builds_three_apis_from_services_dirs() -> None:
    text = _compose_text()
    # datacenter-api and customer-api build from repo root so Dockerfiles can COPY shared/.
    assert "dockerfile: services/datacenter-api/Dockerfile" in text
    assert "dockerfile: services/customer-api/Dockerfile" in text
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


def test_docker_compose_no_hardcoded_db_host_for_apis() -> None:
    """APIs must use .env (external DB); Compose must not override DB_* with internal postgres."""
    text = _compose_text()
    assert "DB_HOST: db" not in text


def test_docker_compose_apis_use_env_file() -> None:
    text = _compose_text()
    assert text.count("env_file:") >= 4  # app + datacenter-api + customer-api + query-api


def test_docker_compose_db_service_not_on_microservice_profile() -> None:
    """Bundled Postgres is optional (with-db only); microservice stack uses external DB."""
    text = _compose_text()
    db_block = text.split("  db:")[1].split("  redis:")[0]
    assert "- microservice" not in db_block
    assert "- with-db" in db_block


def test_docker_compose_includes_chatbot_api() -> None:
    text = _compose_text()
    assert "context: ./services/chatbot-api" in text
    assert "container_name: bulutistan-chatbot-api" in text
    assert "CHATBOT_API_URL" in text
    assert "http://chatbot-api:8000" in text
    # chatbot-api is part of the microservice profile (same as the other APIs).
    # Split on the top-level "\nnetworks:" (column 0), not the service-level one.
    chatbot_block = text.split("  chatbot-api:")[1].split("\nnetworks:")[0]
    assert "- microservice" in chatbot_block


def test_docker_compose_has_no_hardcoded_llm_token() -> None:
    """The LLM secret must never be a literal token; it is sourced from the
    gitignored .env.local env_file, not written inline in this tracked file."""
    text = _compose_text()
    assert "sk-proj" not in text.lower()  # no literal token, any case
    assert ".env.local" in text  # key comes from the gitignored local secrets file
    # And it must not be injected via an inline interpolation line either.
    assert "BULUTISTAN_LLM_API_KEY:" not in text
