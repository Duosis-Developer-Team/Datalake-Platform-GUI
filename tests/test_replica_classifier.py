"""Unit tests for shared DR / replica VM name classification."""
from __future__ import annotations

from shared.backup.replica_classifier import (
    classify_vm_name,
    clear_replica_patterns_cache,
    filter_replica_names,
    load_replica_patterns,
    reconcile_vendor_counts,
)


def test_silinecek_takes_priority_over_replica_suffix():
    assert classify_vm_name("app01_DR_silinecek") == "silinecek"
    assert classify_vm_name("SILINECEK-vm") == "silinecek"


def test_replica_suffix_patterns():
    assert classify_vm_name("boyner-app-01_DR") == "replica"
    assert classify_vm_name("boyner-app-01_dr") == "replica"
    assert classify_vm_name("site_vm_DRC") == "replica"
    assert classify_vm_name("web_replica") == "replica"
    assert classify_vm_name("web_replika") == "replica"


def test_embedded_dr_and_contains_replica():
    assert classify_vm_name("cust-dr-db01") == "replica"
    assert classify_vm_name("cust_dr_db01") == "replica"
    assert classify_vm_name("my-replica-host") == "replica"
    assert classify_vm_name("replika-server") == "replica"


def test_billable_remainder():
    assert classify_vm_name("prod-web-01") == "billable"
    assert classify_vm_name("") == "billable"
    assert classify_vm_name(None) == "billable"


def test_filter_replica_names():
    names = [
        "a_DR",
        "silinecek-x",
        "prod-web",
        "b_replica",
        "",
        None,
    ]
    assert filter_replica_names(names) == ["a_DR", "b_replica"]


def test_reconcile_vendor_counts_ok_and_mismatch():
    ok = reconcile_vendor_counts(10, 6, 4)
    assert ok["gap"] == 0
    assert ok["vendor_total"] == 10
    assert ok["status"] == "ok"

    mismatch = reconcile_vendor_counts(12, 6, 4)
    assert mismatch["gap"] == 2
    assert mismatch["status"] == "mismatch"

    under = reconcile_vendor_counts(5, 6, 4)
    assert under["gap"] == -5
    assert under["status"] == "mismatch"


def test_reconcile_handles_none():
    result = reconcile_vendor_counts(None, None, None)
    assert result["replica_vm_count"] == 0
    assert result["gap"] == 0
    assert result["status"] == "ok"


def test_load_replica_patterns_seed():
    clear_replica_patterns_cache()
    cfg = load_replica_patterns()
    assert cfg.get("version") == 1
    assert any(
        str(r.get("value", "")).lower() == "silinecek"
        for r in (cfg.get("silinecek") or [])
    )
    suffixes = {
        str(r.get("value", "")).upper()
        for r in (cfg.get("replica_patterns") or [])
        if r.get("match") == "suffix"
    }
    assert "_DR" in suffixes
    assert "_DRC" in suffixes
