"""Tests for Virt compute cache refresh scheduling helpers."""
from __future__ import annotations

from unittest.mock import MagicMock, call

from app.services.dc_service import DatabaseService


def test_refresh_virt_compute_cache_warms_hosts_and_cluster_lists():
    svc = DatabaseService.__new__(DatabaseService)
    svc._dc_list = ["DC11", "DC13"]
    svc.get_classic_cluster_list = MagicMock(return_value=["KM1"])
    svc.get_hyperconv_cluster_list = MagicMock(return_value=["HC1"])
    svc.get_classic_host_rows = MagicMock(return_value={"hosts": [], "host_count": 0})
    svc.get_hyperconv_host_rows = MagicMock(return_value={"hosts": [], "host_count": 0})

    svc.refresh_virt_compute_cache()

    assert svc.get_classic_cluster_list.call_count == 4
    assert svc.get_hyperconv_cluster_list.call_count == 4
    assert svc.get_classic_host_rows.call_count == 4
    assert svc.get_hyperconv_host_rows.call_count == 4
