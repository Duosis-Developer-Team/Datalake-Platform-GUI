from unittest.mock import MagicMock, patch

import pytest

from app.services.scheduler_service import start_scheduler, _stop


def _make_mock_db():
    db = MagicMock()
    db.warm_cache.return_value = None
    db.refresh_all_data.return_value = None
    db.warm_additional_ranges.return_value = None
    db.get_customer_resources.return_value = {"totals": {}, "assets": {}}
    return db


def test_start_scheduler_returns_running_scheduler():
    db = _make_mock_db()
    scheduler = start_scheduler(db)
    assert scheduler.running
    scheduler.shutdown(wait=False)


def test_start_scheduler_calls_warm_cache_on_db():
    db = _make_mock_db()
    scheduler = start_scheduler(db)
    db.warm_cache.assert_called_once()
    scheduler.shutdown(wait=False)


def test_start_scheduler_adds_cache_refresh_job():
    db = _make_mock_db()
    scheduler = start_scheduler(db)
    job_ids = [j.id for j in scheduler.get_jobs()]
    assert "cache_refresh" in job_ids
    scheduler.shutdown(wait=False)


def test_start_scheduler_adds_boyner_refresh_job():
    db = _make_mock_db()
    scheduler = start_scheduler(db)
    job_ids = [j.id for j in scheduler.get_jobs()]
    assert "customer_boyner_refresh" in job_ids
    scheduler.shutdown(wait=False)


def test_stop_shuts_down_running_scheduler():
    db = _make_mock_db()
    scheduler = start_scheduler(db)
    assert scheduler.running
    _stop(scheduler)
    assert not scheduler.running


def test_stop_does_not_raise_for_already_stopped_scheduler():
    db = _make_mock_db()
    scheduler = start_scheduler(db)
    scheduler.shutdown(wait=False)
    _stop(scheduler)
