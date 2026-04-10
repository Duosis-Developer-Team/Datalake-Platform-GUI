"""JWT helpers for microservice calls."""

from src.auth.api_jwt import create_api_token, decode_api_token


def test_api_jwt_roundtrip():
    t = create_api_token(42)
    payload = decode_api_token(t)
    assert payload is not None
    assert payload.get("sub") == "42"
