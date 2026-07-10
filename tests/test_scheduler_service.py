"""Unit tests for scheduler_service customer warm/refresh helpers."""

from unittest.mock import patch

from src.services.scheduler_service import (
    refresh_warmed_customer_availability_bundles,
)


def test_refresh_warmed_customer_availability_bundles_force_refresh_all_combos():
    fake_ranges = [
        {"start": "s1", "end": "e1", "preset": "7d"},
        {"start": "s2", "end": "e2", "preset": "30d"},
    ]
    with patch("src.services.scheduler_service.cache_time_ranges", return_value=fake_ranges), patch(
        "src.services.scheduler_service.WARMED_CUSTOMERS", ("Boyner",)
    ), patch("src.services.scheduler_service.api.get_customer_availability_bundle") as mock_get:
        refresh_warmed_customer_availability_bundles()

    assert mock_get.call_count == 2
    mock_get.assert_any_call("Boyner", fake_ranges[0], force_refresh=True)
    mock_get.assert_any_call("Boyner", fake_ranges[1], force_refresh=True)
