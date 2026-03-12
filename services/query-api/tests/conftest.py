import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app

FAKE_QUERY_VALUE = {"result_type": "value", "value": 42}


@pytest.fixture
def mock_query_service():
    mock_svc = MagicMock()
    mock_svc._pool = MagicMock()
    mock_svc.execute_registered_query.return_value = FAKE_QUERY_VALUE
    with patch("app.main.QueryService", return_value=mock_svc):
        with TestClient(app) as client:
            yield client, mock_svc
