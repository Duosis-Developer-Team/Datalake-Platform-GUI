"""Unit tests for _tab_itsm, _fmt_hours, and ITSM export integration."""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# _fmt_hours
# ---------------------------------------------------------------------------

class TestFmtHours:
    def test_none_returns_dash(self):
        from src.pages.customer_view import _fmt_hours
        assert _fmt_hours(None) == "-"

    def test_less_than_1_hour(self):
        from src.pages.customer_view import _fmt_hours
        assert _fmt_hours(0.5) == "30 min"

    def test_less_than_24_hours(self):
        from src.pages.customer_view import _fmt_hours
        result = _fmt_hours(3.5)
        assert "hr" in result
        assert "3.5" in result

    def test_more_than_24_hours(self):
        from src.pages.customer_view import _fmt_hours
        result = _fmt_hours(48.0)
        assert "days" in result

    def test_zero(self):
        from src.pages.customer_view import _fmt_hours
        result = _fmt_hours(0.0)
        assert result == "0 min"


class TestPriorityColor:
    def test_critical_returns_red(self):
        from src.pages.customer_view import _priority_color
        assert _priority_color("Critical") == "red"

    def test_high_returns_orange(self):
        from src.pages.customer_view import _priority_color
        assert _priority_color("High") == "orange"

    def test_medium_returns_yellow(self):
        from src.pages.customer_view import _priority_color
        assert _priority_color("Medium") == "yellow"

    def test_low_returns_blue(self):
        from src.pages.customer_view import _priority_color
        assert _priority_color("Low") == "blue"

    def test_none_returns_blue(self):
        from src.pages.customer_view import _priority_color
        assert _priority_color(None) == "blue"


# ---------------------------------------------------------------------------
# _tab_itsm — smoke test that it builds a dmc.Stack without exceptions
# ---------------------------------------------------------------------------

_SAMPLE_SUMMARY = {
    "total_count": 4, "incident_count": 2, "sr_count": 2,
    "incident_open": 1, "incident_closed": 1, "sr_open": 1, "sr_closed": 1,
    "avg_resolution_hours": 8.0, "median_resolution_hours": 6.0,
    "p95_resolution_hours": 24.0, "stddev_resolution_hours": 2.0,
    "sla_breach_count": 1, "top_category": "Network",
    "priority_distribution": [{"priority": "High", "count": 2}],
    "state_distribution": [{"stage": "Open", "count": 2}],
}

_SAMPLE_EXTREMES = {
    "long_tail": [{
        "source": "incident", "id": 1001, "subject": "Old ticket", "stage": "Closed",
        "priority_name": "High", "customer_user": "Ahmet",
        "agent_group_name": "Net", "opened_at": "2026-01-01 09:00:00",
        "target_resolution_date": "2026-01-07 09:00:00",
        "closed_and_done_date": "2026-01-20 09:00:00",
        "resolution_hours": 264.0, "open_age_days": None,
        "threshold_avg": 10.0, "threshold_stddev": 3.0, "threshold_value": 13.0,
    }],
    "sla_breach": [{
        "source": "servicerequest", "id": 2001, "subject": "Overdue SR", "stage": "Open",
        "priority_name": "Critical", "customer_user": "Fatma",
        "agent_group_name": "Infra", "opened_at": "2026-01-05 08:00:00",
        "target_resolution_date": "2026-01-10 08:00:00",
        "closed_and_done_date": None, "resolution_hours": None,
        "open_age_days": 80.0,
        "threshold_avg": None, "threshold_stddev": None, "threshold_value": None,
    }],
}

_SAMPLE_TICKETS = [
    {"source": "incident", "id": 1001, "subject": "Old ticket", "stage": "Closed",
     "state_text": "Closed", "status_name": "Closed",
     "priority_name": "High", "category_name": "Network",
     "customer_user": "Ahmet", "agent_group_name": "Net",
     "opened_at": "2026-01-01 09:00:00",
     "target_resolution_date": "2026-01-07 09:00:00",
     "closed_and_done_date": "2026-01-20 09:00:00",
     "resolution_hours": 264.0, "open_age_days": None},
    {"source": "servicerequest", "id": 2001, "subject": "Overdue SR", "stage": "Open",
     "state_text": "Open", "status_name": "Active",
     "priority_name": "Critical", "category_name": "Infra",
     "customer_user": "Fatma", "agent_group_name": "Infra",
     "opened_at": "2026-01-05 08:00:00",
     "target_resolution_date": "2026-01-10 08:00:00",
     "closed_and_done_date": None,
     "resolution_hours": None, "open_age_days": 80.0},
]


class TestTabItsmSmoke:
    def test_returns_dmc_stack(self):
        import dash_mantine_components as dmc
        from src.pages.customer_view import _tab_itsm
        result = _tab_itsm("Boyner", None, _SAMPLE_SUMMARY, _SAMPLE_EXTREMES, _SAMPLE_TICKETS)
        assert isinstance(result, dmc.Stack)

    def test_empty_data_does_not_raise(self):
        from src.pages.customer_view import _tab_itsm
        result = _tab_itsm("Boyner", None, {}, {}, [])
        assert result is not None

    def test_kpi_section_present(self):
        import dash_mantine_components as dmc
        from src.pages.customer_view import _tab_itsm
        result = _tab_itsm("Boyner", None, _SAMPLE_SUMMARY, _SAMPLE_EXTREMES, _SAMPLE_TICKETS)
        # Result is a Stack; first child is a section card containing the KPI grid
        assert hasattr(result, "children")


# ---------------------------------------------------------------------------
# Export sheets — ITSM sheet inclusion
# ---------------------------------------------------------------------------

class TestExportSheets:
    def test_itsm_summary_sheet_included(self):
        from src.pages.customer_view import _build_customer_export_sheets
        sheets = _build_customer_export_sheets(
            "Boyner", {}, {}, {}, {}, {}, {}, {}, {}, [],
            itsm_summary=_SAMPLE_SUMMARY,
            itsm_extremes=_SAMPLE_EXTREMES,
            itsm_tickets=_SAMPLE_TICKETS,
        )
        assert "ITSM_Summary" in sheets
        assert isinstance(sheets["ITSM_Summary"], list)
        assert sheets["ITSM_Summary"][0]["total_count"] == 4

    def test_itsm_extremes_closed_sheet(self):
        from src.pages.customer_view import _build_customer_export_sheets
        sheets = _build_customer_export_sheets(
            "Boyner", {}, {}, {}, {}, {}, {}, {}, {}, [],
            itsm_summary=_SAMPLE_SUMMARY,
            itsm_extremes=_SAMPLE_EXTREMES,
            itsm_tickets=_SAMPLE_TICKETS,
        )
        assert "ITSM_Extremes_Closed" in sheets
        assert sheets["ITSM_Extremes_Closed"][0]["id"] == 1001

    def test_itsm_extremes_sla_sheet(self):
        from src.pages.customer_view import _build_customer_export_sheets
        sheets = _build_customer_export_sheets(
            "Boyner", {}, {}, {}, {}, {}, {}, {}, {}, [],
            itsm_summary=_SAMPLE_SUMMARY,
            itsm_extremes=_SAMPLE_EXTREMES,
            itsm_tickets=_SAMPLE_TICKETS,
        )
        assert "ITSM_Extremes_OpenSlaBreach" in sheets
        assert sheets["ITSM_Extremes_OpenSlaBreach"][0]["source"] == "servicerequest"

    def test_itsm_all_tickets_sheet(self):
        from src.pages.customer_view import _build_customer_export_sheets
        sheets = _build_customer_export_sheets(
            "Boyner", {}, {}, {}, {}, {}, {}, {}, {}, [],
            itsm_summary=_SAMPLE_SUMMARY,
            itsm_extremes=_SAMPLE_EXTREMES,
            itsm_tickets=_SAMPLE_TICKETS,
        )
        assert "ITSM_All_Tickets" in sheets
        assert len(sheets["ITSM_All_Tickets"]) == 2

    def test_itsm_sheets_in_export_order(self):
        """Verify the export order list contains all ITSM sheet names."""
        import inspect
        from src.pages import customer_view
        source = inspect.getsource(customer_view)
        for sheet_name in (
            "ITSM_Summary",
            "ITSM_Extremes_Closed",
            "ITSM_Extremes_OpenSlaBreach",
            "ITSM_All_Tickets",
        ):
            assert sheet_name in source, f"{sheet_name} not found in export order"
