"""crm-engine startup must not block HTTP on the initial sellable snapshot."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_sync_flag(monkeypatch):
    monkeypatch.delenv("CRM_ENGINE_SYNC_SNAPSHOT_ON_STARTUP", raising=False)


def test_start_scheduler_does_not_call_snapshot_all_before_start_by_default():
    from app.main import _start_scheduler

    sellable = MagicMock()
    with patch("app.main.BackgroundScheduler") as sched_cls:
        sched = MagicMock()
        sched_cls.return_value = sched
        _start_scheduler(sellable)

    sellable.snapshot_all.assert_not_called()
    sched.add_job.assert_called_once()
    assert sched.add_job.call_args.kwargs.get("next_run_time") is not None
    sched.start.assert_called_once()


def test_start_scheduler_sync_snapshot_when_flag_true(monkeypatch):
    monkeypatch.setattr("app.main._SYNC_SNAPSHOT_ON_STARTUP", True)
    from app.main import _start_scheduler

    sellable = MagicMock()
    with patch("app.main.BackgroundScheduler") as sched_cls:
        sched = MagicMock()
        sched_cls.return_value = sched
        _start_scheduler(sellable)

    sellable.snapshot_all.assert_called_once()
    assert sched.add_job.call_args.kwargs.get("next_run_time") is None
