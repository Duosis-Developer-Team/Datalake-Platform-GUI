import pathlib

import yaml


COMPOSE_PATH = pathlib.Path(__file__).parent.parent.parent / "docker-compose.yml"


def _load_compose():
    return yaml.safe_load(COMPOSE_PATH.read_text())


def test_backend_service_depends_on_redis_and_db():
    compose = _load_compose()
    depends_on = set(compose["services"]["backend"]["depends_on"])
    assert {"redis", "db"}.issubset(depends_on)


def test_backend_service_sets_redis_connection_environment():
    compose = _load_compose()
    environment = compose["services"]["backend"]["environment"]
    assert environment["REDIS_HOST"] == "redis"
    assert str(environment["REDIS_PORT"]) == "6379"


def test_db_service_is_available_in_microservice_profile():
    compose = _load_compose()
    profiles = set(compose["services"]["db"].get("profiles", []))
    assert "microservice" in profiles


def test_redis_service_has_healthcheck_and_persistent_volume():
    compose = _load_compose()
    redis_service = compose["services"]["redis"]
    assert redis_service["healthcheck"]["test"] == ["CMD", "redis-cli", "ping"]
    assert "redis_data:/data" in redis_service["volumes"]


def test_compose_declares_redis_data_volume():
    compose = _load_compose()
    assert "redis_data" in compose["volumes"]
