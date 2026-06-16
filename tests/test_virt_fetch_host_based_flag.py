"""Virt merged fetch respects SELLABLE_HOST_BASED_ENABLED flag."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from shared.sellable.config import host_based_sellable_enabled


@pytest.fixture(autouse=True)
def _clear_host_based_env(monkeypatch):
    monkeypatch.delenv("SELLABLE_HOST_BASED_ENABLED", raising=False)


def test_fetch_virt_compute_merged_skips_host_rows_when_disabled(monkeypatch):
    monkeypatch.setenv("SELLABLE_HOST_BASED_ENABLED", "false")
    import app as app_module

    metrics = {"cpu_cap": 100.0, "cpu_alloc_ghz_sales": 40.0}
    with patch.object(app_module, "_virt_metrics_from_cache", return_value=metrics) as metrics_fn, patch.object(
        app_module.api, "get_classic_host_rows"
    ) as host_fn, patch.object(app_module, "parallel_execute") as parallel_fn:
        out = app_module._fetch_virt_compute_merged("DC13", None, {"preset": "7d"}, classic=True)

    assert out["merged"] == metrics
    assert out["hosts"] == {}
    metrics_fn.assert_called_once()
    host_fn.assert_not_called()
    parallel_fn.assert_not_called()


def test_fetch_virt_compute_merged_fetches_hosts_when_enabled(monkeypatch):
    monkeypatch.setenv("SELLABLE_HOST_BASED_ENABLED", "true")
    import app as app_module

    metrics = {"cpu_cap": 100.0}
    hosts = {"hosts": [{"host": "hv1"}], "host_count": 1}
    merged = {"cpu_cap": 200.0}

    with patch.object(app_module, "_virt_metrics_from_cache", return_value=metrics), patch.object(
        app_module.api, "get_classic_host_rows", return_value=hosts
    ) as host_fn, patch.object(
        app_module, "parallel_execute", side_effect=lambda tasks: {k: fn() for k, fn in tasks.items()}
    ), patch.object(app_module, "merge_host_summary_into_compute", return_value=merged) as merge_fn:
        out = app_module._fetch_virt_compute_merged("DC13", ["KM-1"], {"preset": "7d"}, classic=True)

    host_fn.assert_called_once()
    merge_fn.assert_called_once_with(metrics, hosts)
    assert out["merged"] == merged
    assert out["hosts"] == hosts


def test_host_based_flag_default_is_false():
    assert host_based_sellable_enabled() is False
