"""Tests for root location SQL query module."""

from unittest.mock import patch

from app.db.queries import loki_locations as lq


@patch("app.db.queries.loki_locations.pool.fetch_all")
def test_fetch_root_locations_only_parent_null(mock_fetch):
    mock_fetch.return_value = [
        {"id": 1, "name": "DC13", "description": "", "site_name": "IST", "status_value": "active"},
    ]
    rows = lq.fetch_root_locations()
    assert len(rows) == 1
    sql = mock_fetch.call_args[0][0]
    assert "parent_id IS NULL" in sql
    assert "status_value = 'active'" in sql
    assert "DISTINCT ON (name)" in sql
