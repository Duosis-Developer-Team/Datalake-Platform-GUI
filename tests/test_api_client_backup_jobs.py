"""Unit tests for backup-jobs api_client wrappers — HTTP is mocked."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _clear_cache():
    from src.services import cache_service as cs

    cs.clear()
    yield


FAKE_RESPONSE = {
    "vendor": "veeam",
    "granularity": "day",
    "range": {"start": "2026-04-01", "end": "2026-05-01"},
    "series": [
        {"period": "2026-04-01", "status": "success", "job_type": "Full", "policy_type": None, "count": 100},
        {"period": "2026-04-01", "status": "failed",  "job_type": "Full", "policy_type": None, "count": 5},
    ],
    "totals": {
        "total": 105, "success": 100, "failed": 5, "warning": 0, "other": 0,
        "success_rate": 95.24, "avg_per_period": 105.0, "period_count": 1,
    },
}


class TestBackupJobWrappers:
    def _mock_client(self, payload: dict) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = payload
        client = MagicMock()
        client.get.return_value = mock_resp
        return client

    def test_get_dc_veeam_jobs_returns_payload(self):
        client = self._mock_client(FAKE_RESPONSE)
        with patch("src.services.api_client._get_client_dc", return_value=client):
            from src.services.api_client import get_dc_veeam_jobs

            result = get_dc_veeam_jobs("DC13", {"preset": "30d"}, granularity="day")

        assert result["vendor"] == "veeam"
        assert result["totals"]["total"] == 105
        # Verify endpoint and params
        call = client.get.call_args
        assert "/api/v1/datacenters/DC13/backup/veeam/jobs" in call[0][0]
        assert call[1]["params"]["granularity"] == "day"
        assert call[1]["params"]["preset"] == "30d"

    def test_get_dc_zerto_jobs_with_custom_range(self):
        payload = {**FAKE_RESPONSE, "vendor": "zerto"}
        client = self._mock_client(payload)
        with patch("src.services.api_client._get_client_dc", return_value=client):
            from src.services.api_client import get_dc_zerto_jobs

            tr = {"start": "2026-03-01", "end": "2026-05-01", "preset": "custom"}
            result = get_dc_zerto_jobs("DC13", tr, granularity="week")

        assert result["vendor"] == "zerto"
        call_params = client.get.call_args[1]["params"]
        assert call_params["start"] == "2026-03-01"
        assert call_params["end"] == "2026-05-01"
        assert call_params["granularity"] == "week"

    def test_get_dc_netbackup_jobs_returns_payload(self):
        payload = {**FAKE_RESPONSE, "vendor": "netbackup"}
        client = self._mock_client(payload)
        with patch("src.services.api_client._get_client_dc", return_value=client):
            from src.services.api_client import get_dc_netbackup_jobs

            result = get_dc_netbackup_jobs("DC14", {"preset": "30d"}, granularity="month")

        assert result["vendor"] == "netbackup"
        assert "/api/v1/datacenters/DC14/backup/netbackup/jobs" in client.get.call_args[0][0]
        assert client.get.call_args[1]["params"]["granularity"] == "month"

    def test_wrapper_returns_empty_on_non_dict_response(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = "not-a-dict"
        client = MagicMock()
        client.get.return_value = mock_resp
        with patch("src.services.api_client._get_client_dc", return_value=client):
            from src.services.api_client import get_dc_veeam_jobs

            result = get_dc_veeam_jobs("DC13", None, granularity="day")

        assert result["vendor"] == "veeam"
        assert result["series"] == []
        assert result["totals"]["total"] == 0

    def test_cache_key_includes_granularity(self):
        """Aynı dc/tr için day vs week farklı cache key olmalı, iki ayrı HTTP çağrısı yapmalı."""
        client = self._mock_client(FAKE_RESPONSE)
        with patch("src.services.api_client._get_client_dc", return_value=client):
            from src.services.api_client import get_dc_veeam_jobs

            get_dc_veeam_jobs("DC13", {"preset": "30d"}, granularity="day")
            get_dc_veeam_jobs("DC13", {"preset": "30d"}, granularity="week")

        assert client.get.call_count == 2  # cache miss for both

    def test_refresh_dc_backup_jobs_cache_calls_backend_and_drops_local(self):
        from src.services import cache_service as cs
        from src.services.api_client import (
            get_dc_veeam_jobs,
            refresh_dc_backup_jobs_cache,
        )

        # 1) Prime local cache via a normal GET
        get_client = self._mock_client(FAKE_RESPONSE)
        with patch("src.services.api_client._get_client_dc", return_value=get_client):
            get_dc_veeam_jobs("DC13", {"preset": "30d"}, granularity="day")

        # 2) Call refresh — mock a POST returning ok
        post_resp = MagicMock()
        post_resp.status_code = 200
        post_resp.content = b'{"status":"ok"}'
        post_resp.json.return_value = {"status": "ok", "deleted": {"veeam": "invalidated"}}
        post_client = MagicMock()
        post_client.post.return_value = post_resp
        with patch("src.services.api_client._get_client_dc", return_value=post_client):
            result = refresh_dc_backup_jobs_cache("DC13", vendor="veeam")

        assert result.get("status") == "ok"
        # Backend was called with vendor query
        call = post_client.post.call_args
        assert "/api/v1/datacenters/DC13/backup/jobs/refresh" in call[0][0]
        assert call[1]["params"]["vendor"] == "veeam"

        # 3) Next get_dc_veeam_jobs must hit HTTP again (local cache was dropped)
        get_client.get.reset_mock()
        with patch("src.services.api_client._get_client_dc", return_value=get_client):
            get_dc_veeam_jobs("DC13", {"preset": "30d"}, granularity="day")
        assert get_client.get.call_count == 1

    def test_refresh_dc_backup_jobs_cache_handles_backend_error(self):
        from src.services.api_client import refresh_dc_backup_jobs_cache

        client = MagicMock()
        client.post.side_effect = RuntimeError("boom")
        with patch("src.services.api_client._get_client_dc", return_value=client):
            result = refresh_dc_backup_jobs_cache("DC13", vendor="veeam")

        assert result.get("status") == "error"
        assert "boom" in str(result.get("error", ""))

    def test_cache_namespace_isolation_from_repos(self):
        """dc_veeam_jobs cache key, dc_veeam (repos) cache key ile çakışmamalı."""
        from src.services import cache_service as cs
        from src.services.api_client import get_dc_veeam_jobs, get_dc_veeam_repos

        client = self._mock_client(FAKE_RESPONSE)
        with patch("src.services.api_client._get_client_dc", return_value=client):
            get_dc_veeam_jobs("DC13", {"preset": "30d"}, granularity="day")

        # cache_service is module-level; we verify jobs key exists but repos key doesn't.
        # Implementation detail: cache_service uses an internal dict; access through get().
        # We just confirm that calling repos still triggers an HTTP request.
        client.get.reset_mock()
        repos_resp = MagicMock()
        repos_resp.status_code = 200
        repos_resp.json.return_value = {"repos": ["r1"], "rows": []}
        client.get.return_value = repos_resp
        with patch("src.services.api_client._get_client_dc", return_value=client):
            result = get_dc_veeam_repos("DC13", {"preset": "30d"})

        assert client.get.call_count == 1
        assert result == {"repos": ["r1"], "rows": []}
