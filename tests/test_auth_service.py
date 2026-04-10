"""Auth service helpers (minimal, no live DB)."""

from unittest.mock import patch

from src.auth import service


def test_to_public_user():
    row = {
        "id": 1,
        "username": "u1",
        "display_name": "U One",
        "email": "a@b.c",
        "source": "local",
        "is_active": True,
    }
    u = service.to_public_user(row)
    assert u.username == "u1"
    assert u.id == 1


@patch("src.auth.service.db.fetch_one")
def test_get_session_user_expired(mock_fetch):
    mock_fetch.return_value = None
    assert service.get_session_user("x") is None
