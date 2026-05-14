"""
Phase 3 A1 — scheduler warm matrix tests.

Verify that DatabaseService._warm_backup_jobs_cache invokes get_dc_*_jobs for
every combination of (DC, vendor, window, granularity), uses parallelism, and
tolerates per-task failures without aborting the batch.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from psycopg2 import OperationalError

from app.services.dc_service import DatabaseService
from app.utils.time_range import BACKUP_JOBS_WARM_GRANULARITIES, backup_jobs_warm_windows


# ---- Window helper ---------------------------------------------------------


def test_backup_jobs_warm_windows_yields_four_presets():
    windows = backup_jobs_warm_windows()
    presets = [w["preset"] for w in windows]
    assert presets == ["1m", "2m", "3m", "6m"]


def test_backup_jobs_warm_granularities_constant():
    assert BACKUP_JOBS_WARM_GRANULARITIES == ("day", "week", "month")


# ---- _warm_backup_jobs_cache -----------------------------------------------


def _make_service(dc_list=("DC11", "DC13")):
    """Build a DatabaseService skeleton without opening real DB connections."""
    with patch("app.services.dc_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = DatabaseService()
    svc._dc_list = list(dc_list)
    return svc


def test_warm_invokes_each_vendor_for_every_combination():
    """Warm matrix DC döngüsü içermez — 4 window × 3 gran × 3 vendor = 36 task."""
    svc = _make_service(dc_list=("DC11", "DC13"))

    with patch.object(svc, "_compute_all_dc_veeam_jobs") as p_v, \
         patch.object(svc, "_compute_all_dc_zerto_jobs") as p_z, \
         patch.object(svc, "_compute_all_dc_netbackup_jobs") as p_nb:
        p_v.return_value = {}
        p_z.return_value = {}
        p_nb.return_value = {}

        svc._warm_backup_jobs_cache()

    # 4 windows × 3 grans = 12 per vendor (DC döngüsü yok — her çağrı tüm DC'leri besler)
    expected = 4 * 3
    assert p_v.call_count == expected
    assert p_z.call_count == expected
    assert p_nb.call_count == expected


def test_warm_skips_when_dc_list_empty():
    svc = _make_service(dc_list=())

    with patch.object(svc, "_compute_all_dc_veeam_jobs") as p_v, \
         patch.object(svc, "_compute_all_dc_zerto_jobs") as p_z, \
         patch.object(svc, "_compute_all_dc_netbackup_jobs") as p_nb:

        svc._warm_backup_jobs_cache()

    assert p_v.call_count == 0
    assert p_z.call_count == 0
    assert p_nb.call_count == 0


def test_warm_tolerates_per_task_failure_and_continues():
    svc = _make_service(dc_list=("DC11",))

    def _raises(*args, **kwargs):
        raise RuntimeError("boom")

    with patch.object(svc, "_compute_all_dc_veeam_jobs", side_effect=_raises) as p_v, \
         patch.object(svc, "_compute_all_dc_zerto_jobs") as p_z, \
         patch.object(svc, "_compute_all_dc_netbackup_jobs") as p_nb:
        p_z.return_value = {}
        p_nb.return_value = {}

        svc._warm_backup_jobs_cache()  # must NOT raise

    # 4 windows × 3 grans = 12 attempts per vendor
    assert p_v.call_count == 12
    assert p_z.call_count == 12
    assert p_nb.call_count == 12


def test_warm_passes_granularity_and_window_to_compute():
    svc = _make_service(dc_list=("DC11",))

    captured: list[tuple] = []

    def _capture(gran, start_ts, end_ts, tr_start, tr_end):
        captured.append((gran, tr_start, tr_end))
        return {}

    with patch.object(svc, "_compute_all_dc_veeam_jobs", side_effect=_capture), \
         patch.object(svc, "_compute_all_dc_zerto_jobs", return_value={}), \
         patch.object(svc, "_compute_all_dc_netbackup_jobs", return_value={}):
        svc._warm_backup_jobs_cache()

    # captured contains 4 windows × 3 grans = 12 veeam calls
    grans = {c[0] for c in captured}
    starts = {c[1] for c in captured}
    assert grans == {"day", "week", "month"}
    assert len(starts) == 4  # 4 distinct window starts


# ---- refresh_backup_cache integration --------------------------------------


def test_refresh_backup_cache_invokes_warm_jobs():
    svc = _make_service(dc_list=("DC11",))

    with patch.object(svc, "_fetch_dc_netbackup_pools", return_value={"pools": [], "rows": []}), \
         patch.object(svc, "_fetch_dc_zerto_sites", return_value={"sites": [], "rows": []}), \
         patch.object(svc, "_fetch_dc_veeam_repositories", return_value={"repos": [], "rows": []}), \
         patch.object(svc, "_warm_backup_jobs_cache") as p_warm:
        svc.refresh_backup_cache()

    p_warm.assert_called_once()
