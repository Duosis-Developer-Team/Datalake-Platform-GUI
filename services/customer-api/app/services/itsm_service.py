"""
ITSM (ServiceCore) data service.

Resolves customer → ServiceCore users (via email domain) → incidents + service-requests.
All methods return plain dicts/lists; Pydantic validation happens in the router layer.

Resolution chain (no DDL changes to datalake tables):
    customer_name → customer_to_email_needle() → discovery_servicecore_users.user_id
    → discovery_servicecore_incidents.org_user_id   (BIGINT, indexed)
    → discovery_servicecore_servicerequests.requester_id (BIGINT, indexed)
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from app.db.queries import itsm as iq
from app.utils.customer_needle import customer_to_email_needle

logger = logging.getLogger(__name__)


class ITSMService:
    """Wraps ITSM queries using the shared CustomerService connection pool infrastructure."""

    def __init__(self, get_connection, run_row, run_rows, resolve_needles: Callable[[str], list[str]] | None = None):
        self._get_connection = get_connection
        self._run_row = run_row
        self._run_rows = run_rows
        self._resolve_needles = resolve_needles

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_query(self, sql: str, params: dict) -> List[Dict[str, Any]]:
        """Execute a SELECT with named params dict and return list of column-name dicts."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                t0 = time.perf_counter()
                cur.execute(sql, params)
                cols = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                elapsed = (time.perf_counter() - t0) * 1000
                logger.info("ITSM SQL (%.0fms): %s rows", elapsed, len(rows))
                return [dict(zip(cols, row)) for row in rows]

    def _run_one(self, sql: str, params: dict) -> Optional[Dict[str, Any]]:
        rows = self._run_query(sql, params)
        return rows[0] if rows else None

    def _needles_for_customer(self, customer_name: str) -> list[str]:
        if self._resolve_needles:
            needles = [n for n in (self._resolve_needles(customer_name) or []) if n]
            if needles:
                return needles
        return [customer_to_email_needle(customer_name)]

    def _base_params(self, customer_name: str, time_range: dict, *, needle: str | None = None) -> dict:
        """Build named-param dict shared by all three queries."""
        start = time_range.get("start")
        end = time_range.get("end")
        resolved_needle = needle or self._needles_for_customer(customer_name)[0]
        return {"needle": resolved_needle, "start_ts": start, "end_ts": end}

    @staticmethod
    def _coerce_float(v) -> Optional[float]:
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_json_col(v):
        """JSON columns come back as str from psycopg2 without extras."""
        if v is None:
            return []
        if isinstance(v, (list, dict)):
            return v
        try:
            return json.loads(v)
        except Exception:
            return []

    # ------------------------------------------------------------------
    # /customers/{name}/itsm/summary
    # ------------------------------------------------------------------

    def get_summary(self, customer_name: str, time_range: dict) -> Dict[str, Any]:
        needles = self._needles_for_customer(customer_name)
        if len(needles) == 1:
            params = self._base_params(customer_name, time_range, needle=needles[0])
            row = self._run_one(iq.ITSM_SUMMARY, params)
            if not row:
                return self._empty_summary()
            return self._summary_from_row(row)

        merged = self._empty_summary()
        for needle in needles:
            params = self._base_params(customer_name, time_range, needle=needle)
            row = self._run_one(iq.ITSM_SUMMARY, params)
            if not row:
                continue
            part = self._summary_from_row(row)
            merged["total_count"] += part["total_count"]
            merged["incident_count"] += part["incident_count"]
            merged["sr_count"] += part["sr_count"]
            merged["incident_open"] += part["incident_open"]
            merged["incident_closed"] += part["incident_closed"]
            merged["sr_open"] += part["sr_open"]
            merged["sr_closed"] += part["sr_closed"]
            merged["sla_breach_count"] += part["sla_breach_count"]
        return merged

    def _summary_from_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        if not row:
            return self._empty_summary()
        return {
            "total_count":              int(row.get("total_count") or 0),
            "incident_count":           int(row.get("incident_count") or 0),
            "sr_count":                 int(row.get("sr_count") or 0),
            "incident_open":            int(row.get("incident_open") or 0),
            "incident_closed":          int(row.get("incident_closed") or 0),
            "sr_open":                  int(row.get("sr_open") or 0),
            "sr_closed":                int(row.get("sr_closed") or 0),
            "avg_resolution_hours":     self._coerce_float(row.get("avg_resolution_hours")),
            "median_resolution_hours":  self._coerce_float(row.get("median_resolution_hours")),
            "p95_resolution_hours":     self._coerce_float(row.get("p95_resolution_hours")),
            "stddev_resolution_hours":  self._coerce_float(row.get("stddev_resolution_hours")),
            "sla_breach_count":         int(row.get("sla_breach_count") or 0),
            "top_category":             row.get("top_category"),
            "priority_distribution":    self._parse_json_col(row.get("priority_distribution")),
            "state_distribution":       self._parse_json_col(row.get("state_distribution")),
        }

    @staticmethod
    def _empty_summary() -> Dict[str, Any]:
        return {
            "total_count": 0, "incident_count": 0, "sr_count": 0,
            "incident_open": 0, "incident_closed": 0, "sr_open": 0, "sr_closed": 0,
            "avg_resolution_hours": None, "median_resolution_hours": None,
            "p95_resolution_hours": None, "stddev_resolution_hours": None,
            "sla_breach_count": 0, "top_category": None,
            "priority_distribution": [], "state_distribution": [],
        }

    # ------------------------------------------------------------------
    # /customers/{name}/itsm/extremes
    # ------------------------------------------------------------------

    def get_extremes(self, customer_name: str, time_range: dict) -> Dict[str, Any]:
        needles = self._needles_for_customer(customer_name)
        long_tail: List[Dict[str, Any]] = []
        sla_breach: List[Dict[str, Any]] = []
        seen: set[str] = set()

        for needle in needles:
            params = self._base_params(customer_name, time_range, needle=needle)
            rows = self._run_query(iq.ITSM_EXTREMES, params)
            for r in rows:
                ticket_key = f"{r.get('source')}:{r.get('id')}"
                if ticket_key in seen:
                    continue
                seen.add(ticket_key)
                ticket = {
                    "source":               r.get("source"),
                    "id":                   r.get("id"),
                    "subject":              r.get("subject"),
                    "stage":                r.get("stage"),
                    "priority_name":        r.get("priority_name"),
                    "customer_user":        r.get("customer_user"),
                    "agent_group_name":     r.get("agent_group_name"),
                    "opened_at":            str(r["opened_at"]) if r.get("opened_at") else None,
                    "target_resolution_date": str(r["target_resolution_date"]) if r.get("target_resolution_date") else None,
                    "closed_and_done_date": str(r["closed_and_done_date"]) if r.get("closed_and_done_date") else None,
                    "resolution_hours":     self._coerce_float(r.get("resolution_hours")),
                    "open_age_days":        self._coerce_float(r.get("open_age_days")),
                    "threshold_avg":        self._coerce_float(r.get("threshold_avg")),
                    "threshold_stddev":     self._coerce_float(r.get("threshold_stddev")),
                    "threshold_value":      self._coerce_float(r.get("threshold_value")),
                }
                if r.get("extreme_type") == "long_tail":
                    long_tail.append(ticket)
                else:
                    sla_breach.append(ticket)

        return {"long_tail": long_tail, "sla_breach": sla_breach}

    # ------------------------------------------------------------------
    # /customers/{name}/itsm/tickets
    # ------------------------------------------------------------------

    def get_tickets(self, customer_name: str, time_range: dict) -> List[Dict[str, Any]]:
        needles = self._needles_for_customer(customer_name)
        out: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for needle in needles:
            params = self._base_params(customer_name, time_range, needle=needle)
            rows = self._run_query(iq.ITSM_TICKETS, params)
            for r in rows:
                ticket_key = f"{r.get('source')}:{r.get('id')}"
                if ticket_key in seen:
                    continue
                seen.add(ticket_key)
                out.append({
                "source":               r.get("source"),
                "id":                   r.get("id"),
                "subject":              r.get("subject"),
                "stage":                r.get("stage"),
                "state_text":           r.get("state_text"),
                "status_name":          r.get("status_name"),
                "priority_name":        r.get("priority_name"),
                "category_name":        r.get("category_name"),
                "customer_user":        r.get("customer_user"),
                "agent_group_name":     r.get("agent_group_name"),
                "opened_at":            str(r["opened_at"]) if r.get("opened_at") else None,
                "target_resolution_date": str(r["target_resolution_date"]) if r.get("target_resolution_date") else None,
                "closed_and_done_date": str(r["closed_and_done_date"]) if r.get("closed_and_done_date") else None,
                "resolution_hours":     self._coerce_float(r.get("resolution_hours")),
                "open_age_days":        self._coerce_float(r.get("open_age_days")),
            })
        return out
