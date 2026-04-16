"""Unit tests for scheduler_service customer warm/refresh helpers."""

from unittest.mock import MagicMock, patch

from src.services.scheduler_service import (
    refresh_warmed_customer_availability_bundles,
    warm_warmed_customer_caches,
)


def test_warm_warmed_customer_caches_iterates_ranges_and_customers():
    db = MagicMock()
    fake_ranges = [
        {"start": "a1", "end": "b1", "preset": "7d"},
        {"start": "a2", "end": "b2", "preset": "30d"},
    ]
    with patch("src.services.scheduler_service.cache_time_ranges", return_value=fake_ranges), patch(
        "src.services.scheduler_service.WARMED_CUSTOMERS", ("Boyner", "OtherCo")
    ), patch("src.services.scheduler_service.api.get_customer_resources") as api_get:
        warm_warmed_customer_caches(db)

    assert api_get.call_count == 4
    api_get.assert_any_call("Boyner", fake_ranges[0])
    api_get.assert_any_call("Boyner", fake_ranges[1])
    api_get.assert_any_call("OtherCo", fake_ranges[0])
    api_get.assert_any_call("OtherCo", fake_ranges[1])

    assert db.get_customer_resources.call_count == 4
    db.get_customer_resources.assert_any_call("Boyner", fake_ranges[0])
    db.get_customer_resources.assert_any_call("Boyner", fake_ranges[1])
    db.get_customer_resources.assert_any_call("OtherCo", fake_ranges[0])
    db.get_customer_resources.assert_any_call("OtherCo", fake_ranges[1])


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
