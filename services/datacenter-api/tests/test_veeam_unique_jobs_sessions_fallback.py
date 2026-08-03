"""Veeam unique-jobs sessions fallback when jobs_states is empty for a DC."""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from psycopg2 import OperationalError

from app.db.queries import backup as bq
from app.services.dc_service import DatabaseService


def _make_service(dc_list=("DC13", "DC14")) -> DatabaseService:
    with patch("app.services.dc_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = DatabaseService()
    svc._dc_list = list(dc_list)

    @contextmanager
    def _fake_conn():
        yield MagicMock()

    svc._get_connection = _fake_conn
    return svc


def test_veeam_unique_jobs_falls_back_to_sessions_when_jobs_states_empty_for_dc():
    svc = _make_service()
    seed = [("10.34.2.104", "Dc13-VeemConsule.blt.vc")]
    session_row = (
        "2026-08-01T00:00:00Z",
        "job-1",
        "Cust_Replica_Job",
        "ReplicaJob",
        "Success",
        "Success",
        "2026-08-01T01:00:00Z",
        None,
        "sess-1",
        "VMware",
        "10.34.2.104",
    )

    def _run_rows(_cur, sql, params=None):
        if sql is bq.VEEAM_UNIQUE_JOBS_LATEST:
            return []
        if sql is bq.VEEAM_IP_TO_DC_SEED:
            return seed
        if sql is bq.VEEAM_UNIQUE_JOBS_FROM_SESSIONS_LATEST:
            return [session_row]
        return []

    svc._run_rows = _run_rows
    out = svc._fetch_dc_unique_jobs("DC13", "veeam", "2026-07-27", "2026-08-03")
    assert len(out["rows"]) == 1
    assert out["rows"][0]["name"] == "Cust_Replica_Job"
    assert out["rows"][0]["type"] == "ReplicaJob"
    assert out["totals"]["total_jobs"] == 1


def test_veeam_unique_jobs_skips_sessions_fallback_when_jobs_states_has_rows():
    svc = _make_service()
    seed = [("10.34.2.104", "Dc13-VeemConsule.blt.vc")]
    jobs_row = (
        "2026-08-01T00:00:00Z",
        "j1",
        "FromStates",
        "VSphereReplica",
        "Success",
        "Success",
        "2026-08-01T00:00:00Z",
        1,
        "s1",
        "vm",
        "10.34.2.104",
    )
    called = {"sessions": 0}

    def _run_rows(_cur, sql, params=None):
        if sql is bq.VEEAM_UNIQUE_JOBS_LATEST:
            return [jobs_row]
        if sql is bq.VEEAM_IP_TO_DC_SEED:
            return seed
        if sql is bq.VEEAM_UNIQUE_JOBS_FROM_SESSIONS_LATEST:
            called["sessions"] += 1
            return []
        return []

    svc._run_rows = _run_rows
    out = svc._fetch_dc_unique_jobs("DC13", "veeam", "2026-07-27", "2026-08-03")
    assert called["sessions"] == 0
    assert out["rows"][0]["name"] == "FromStates"


def test_sessions_fallback_sql_constant_exists():
    assert "raw_veeam_sessions" in bq.VEEAM_UNIQUE_JOBS_FROM_SESSIONS_LATEST
    assert "DISTINCT ON" in bq.VEEAM_UNIQUE_JOBS_FROM_SESSIONS_LATEST
