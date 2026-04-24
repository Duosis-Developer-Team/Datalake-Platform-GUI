"""Unit tests for ITSMService — connection pool is fully mocked."""
from __future__ import annotations

import json
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from app.services.itsm_service import ITSMService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service(rows: list[dict]):
    """Build ITSMService with a fake connection that returns *rows*."""
    cols = list(rows[0].keys()) if rows else []

    cursor = MagicMock()
    cursor.__enter__ = lambda s: s
    cursor.__exit__ = MagicMock(return_value=False)
    cursor.description = [(c,) for c in cols]
    cursor.fetchall.return_value = [tuple(r.values()) for r in rows]

    conn = MagicMock()
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cursor

    @contextmanager
    def get_connection():
        yield conn

    return ITSMService(get_connection=get_connection, run_row=None, run_rows=None)


_TR = {"start": "2026-01-01T00:00:00", "end": "2026-04-01T00:00:00"}

_SUMMARY_ROW = {
    "total_count": 5, "incident_count": 3, "sr_count": 2,
    "incident_open": 1, "incident_closed": 2, "sr_open": 1, "sr_closed": 1,
    "avg_resolution_hours": 12.5, "median_resolution_hours": 10.0,
    "p95_resolution_hours": 40.0, "stddev_resolution_hours": 5.0,
    "sla_breach_count": 1, "top_category": "Network",
    "priority_distribution": json.dumps([{"priority": "High", "count": 3}]),
    "state_distribution": json.dumps([{"stage": "Open", "count": 2}]),
}


class TestITSMServiceSummary:
    def test_summary_returns_correct_counts(self):
        svc = _make_service([_SUMMARY_ROW])
        result = svc.get_summary("Boyner", _TR)
        assert result["total_count"] == 5
        assert result["incident_count"] == 3
        assert result["sr_count"] == 2

    def test_summary_float_coercion(self):
        svc = _make_service([_SUMMARY_ROW])
        result = svc.get_summary("Boyner", _TR)
        assert isinstance(result["avg_resolution_hours"], float)
        assert result["avg_resolution_hours"] == pytest.approx(12.5)

    def test_summary_json_cols_parsed(self):
        svc = _make_service([_SUMMARY_ROW])
        result = svc.get_summary("Boyner", _TR)
        assert isinstance(result["priority_distribution"], list)
        assert result["priority_distribution"][0]["priority"] == "High"

    def test_summary_empty_result(self):
        svc = _make_service([])
        result = svc.get_summary("NoOne", _TR)
        assert result["total_count"] == 0
        assert result["priority_distribution"] == []


class TestITSMServiceExtremes:
    _LT_ROW = {
        "extreme_type": "long_tail", "source": "incident", "id": 1001,
        "subject": "Slow ticket", "stage": "Closed",
        "priority_name": "High", "customer_user": "Ahmet Yılmaz",
        "agent_group_name": "Network", "opened_at": "2026-01-10 09:00:00",
        "target_resolution_date": "2026-01-15 09:00:00",
        "closed_and_done_date": "2026-01-25 09:00:00",
        "resolution_hours": 360.0, "open_age_days": None,
        "threshold_avg": 10.0, "threshold_stddev": 5.0, "threshold_value": 15.0,
    }
    _SLA_ROW = {
        "extreme_type": "sla_breach", "source": "servicerequest", "id": 2002,
        "subject": "Overdue SR", "stage": "Open",
        "priority_name": "Critical", "customer_user": "Fatma Şahin",
        "agent_group_name": "Infra", "opened_at": "2026-01-01 08:00:00",
        "target_resolution_date": "2026-01-05 08:00:00",
        "closed_and_done_date": None, "resolution_hours": None,
        "open_age_days": 90.0, "threshold_avg": None, "threshold_stddev": None,
        "threshold_value": None,
    }

    def test_extremes_split_into_lists(self):
        svc = _make_service([self._LT_ROW, self._SLA_ROW])
        result = svc.get_extremes("Boyner", _TR)
        assert len(result["long_tail"]) == 1
        assert len(result["sla_breach"]) == 1

    def test_long_tail_resolution_hours(self):
        svc = _make_service([self._LT_ROW])
        result = svc.get_extremes("Boyner", _TR)
        ticket = result["long_tail"][0]
        assert ticket["resolution_hours"] == pytest.approx(360.0)
        assert ticket["threshold_value"] == pytest.approx(15.0)

    def test_sla_breach_open_age(self):
        svc = _make_service([self._SLA_ROW])
        result = svc.get_extremes("Boyner", _TR)
        ticket = result["sla_breach"][0]
        assert ticket["open_age_days"] == pytest.approx(90.0)
        assert ticket["resolution_hours"] is None


class TestITSMServiceTickets:
    _TICKET = {
        "source": "incident", "id": 999,
        "subject": "Test incident", "stage": "Open",
        "state_text": "Open", "status_name": "Active",
        "priority_name": "Medium", "category_name": "Hardware",
        "customer_user": "Ali Veli", "agent_group_name": "Support",
        "opened_at": "2026-02-01 10:00:00",
        "target_resolution_date": "2026-02-08 10:00:00",
        "closed_and_done_date": None,
        "resolution_hours": None, "open_age_days": 10.0,
    }

    def test_tickets_returns_list(self):
        svc = _make_service([self._TICKET])
        result = svc.get_tickets("Boyner", _TR)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_ticket_fields_present(self):
        svc = _make_service([self._TICKET])
        ticket = svc.get_tickets("Boyner", _TR)[0]
        assert ticket["source"] == "incident"
        assert ticket["id"] == 999
        assert ticket["priority_name"] == "Medium"
        assert ticket["open_age_days"] == pytest.approx(10.0)


class TestBaseParams:
    def test_needle_in_params(self):
        from app.utils.customer_needle import customer_to_email_needle
        needle = customer_to_email_needle("Boyner")
        assert "boyner" in needle
        assert needle.startswith("%@%")
        assert needle.endswith("%")
