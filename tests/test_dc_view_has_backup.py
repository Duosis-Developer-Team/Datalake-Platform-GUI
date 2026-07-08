"""Unit tests for dc_view.compute_has_backup — api_client mocked."""
from __future__ import annotations

from unittest.mock import patch

import pytest


def _empty():
    return {"pools": [], "sites": [], "repos": [], "rows": []}


@pytest.fixture(autouse=True)
def _clear_cache():
    from src.services import cache_service as cs

    cs.clear()
    yield


def _patch_api(nb=None, zerto=None, veeam=None, nx=None):
    """api_client'ın backup wrapper'larını test için patch'le."""
    return (
        patch("src.services.api_client.get_dc_netbackup_pools", return_value=nb or _empty()),
        patch("src.services.api_client.get_dc_zerto_sites", return_value=zerto or _empty()),
        patch("src.services.api_client.get_dc_veeam_repos", return_value=veeam or _empty()),
        patch("src.services.api_client.get_dc_nutanix_snapshots", return_value=nx or _empty()),
    )


def _call(nb=None, zerto=None, veeam=None, nx=None, dc_id="DC13"):
    p_nb, p_z, p_v, p_nx = _patch_api(nb=nb, zerto=zerto, veeam=veeam, nx=nx)
    with p_nb, p_z, p_v, p_nx:
        from src.pages.dc_view import compute_has_backup
        return compute_has_backup(dc_id, {"start": "x", "end": "y", "preset": "7d"})


def test_returns_false_when_all_empty():
    assert _call() is False


def test_returns_true_when_only_netbackup_has_data():
    assert _call(nb={"pools": ["p1"], "rows": []}) is True


def test_returns_true_when_only_zerto_has_data():
    assert _call(zerto={"sites": ["s1"], "rows": []}) is True


def test_returns_true_when_only_veeam_has_data():
    assert _call(veeam={"repos": ["r1"], "rows": []}) is True


def test_returns_true_when_only_nutanix_has_data():
    assert _call(nx={"rows": [{"snapshot_id": "s1"}], "totals": {"total_snapshots": 1}}) is True


def test_returns_false_for_empty_dc_id():
    from src.pages.dc_view import compute_has_backup

    assert compute_has_backup("", None) is False
    assert compute_has_backup(None, None) is False


def test_returns_false_when_api_raises():
    with patch("src.services.api_client.get_dc_netbackup_pools", side_effect=RuntimeError("boom")):
        from src.pages.dc_view import compute_has_backup

        assert compute_has_backup("DC13", None) is False
