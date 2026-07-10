"""RBAC background warm service tests."""
from unittest.mock import MagicMock, patch


def test_trigger_rbac_warm_starts_daemon_thread():
    from src.services import app_background_warm as warm

    with patch.object(warm.threading, "Thread") as mock_thread:
        mock_thread.return_value.start = MagicMock()
        warm.trigger_rbac_warm(42, {"preset": "7d"})
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()


def test_warm_rbac_scope_respects_can_view():
    from src.services import app_background_warm as warm

    with patch("src.auth.permission_service.can_view", return_value=False):
        stats = warm.warm_rbac_scope(1, {"preset": "7d"})
    assert stats["sellable_dcs"] == 0
    assert stats.get("host_rows_dcs", 0) == 0
    assert stats["home"] is False


def test_trigger_customer_view_warm_starts_daemon_thread():
    from src.services import app_background_warm as warm

    warm._cust_last_warm.clear()
    with patch.object(warm.threading, "Thread") as mock_thread:
        mock_thread.return_value.start = MagicMock()
        warm.trigger_customer_view_warm("Acme", {"preset": "7d"})
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()


def test_trigger_customer_view_warm_throttled_per_customer():
    from src.services import app_background_warm as warm

    warm._cust_last_warm.clear()
    with patch.object(warm.threading, "Thread") as mock_thread:
        mock_thread.return_value.start = MagicMock()
        warm.trigger_customer_view_warm("Acme", {"preset": "7d"})
        warm.trigger_customer_view_warm("Acme", {"preset": "7d"})  # within interval -> suppressed
        assert mock_thread.call_count == 1


def test_trigger_customer_view_warm_ignores_blank_name():
    from src.services import app_background_warm as warm

    warm._cust_last_warm.clear()
    with patch.object(warm.threading, "Thread") as mock_thread:
        warm.trigger_customer_view_warm("  ", {"preset": "7d"})
        mock_thread.assert_not_called()
