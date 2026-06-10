"""Unit tests for sync status and inclusion helpers."""

from app.services.inclusion import classify_target, inclusion_from_platform_status
from app.services.sync_status import dc_loki_sync_status, proxy_loki_sync_status


def test_proxy_synced_when_log_ok_and_majority_distributed():
    log = {"dry_run": False, "status": "completed"}
    assert proxy_loki_sync_status(log, total_targets=10, distributed_targets=8) == "loki_synced"


def test_proxy_not_synced_when_dry_run():
    log = {"dry_run": True, "status": "completed"}
    assert proxy_loki_sync_status(log, total_targets=10, distributed_targets=10) == "not_synced"


def test_proxy_not_synced_when_failed():
    log = {"dry_run": False, "status": "failed"}
    assert proxy_loki_sync_status(log, total_targets=10, distributed_targets=10) == "not_synced"


def test_dc_synced_when_all_proxies_synced():
    assert dc_loki_sync_status(["loki_synced", "loki_synced"]) == "loki_synced"


def test_dc_not_synced_when_any_proxy_not_synced():
    assert dc_loki_sync_status(["loki_synced", "not_synced"]) == "not_synced"


def test_inclusion_platform_status():
    assert inclusion_from_platform_status("not_monitored") == "not_monitored"
    assert inclusion_from_platform_status(None) == "monitored"


def test_classify_target_priority():
    assert (
        classify_target(
            extra={"platform_status": "monitored"},
            has_connectivity_fail=False,
            removed_in_last_run=True,
            pending_distribution=False,
        )
        == "missing_from_loki"
    )
    assert (
        classify_target(
            extra={"platform_status": "monitored"},
            has_connectivity_fail=True,
            removed_in_last_run=False,
            pending_distribution=False,
        )
        == "connectivity_issue"
    )
