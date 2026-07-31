"""Unit tests for shared DR / replica VM name classification."""
from __future__ import annotations

from shared.backup.replica_classifier import (
    classify_veeam_session_or_job_type,
    classify_vm_name,
    clear_replica_patterns_cache,
    filter_replica_names,
    is_replica_like,
    load_replica_patterns,
    reconcile_vendor_counts,
)


def test_silinecek_takes_priority_over_dr_suffix():
    assert classify_vm_name("app01_DR_silinecek") == "silinecek"
    assert classify_vm_name("SILINECEK-vm") == "silinecek"


def test_veeam_dr_suffix_and_embedded():
    assert classify_vm_name("boyner-app-01_DR") == "veeam_dr"
    assert classify_vm_name("boyner-app-01_dr") == "veeam_dr"
    assert classify_vm_name("site_vm_DRC") == "veeam_dr"
    assert classify_vm_name("cust-dr-db01") == "veeam_dr"
    assert classify_vm_name("cust_dr_db01") == "veeam_dr"


def test_altra_replica_patterns():
    assert classify_vm_name("web_replica") == "altra_replica"
    assert classify_vm_name("web_replika") == "altra_replica"
    assert classify_vm_name("my-replica-host") == "altra_replica"
    assert classify_vm_name("replika-server") == "altra_replica"


def test_custom_pattern_from_override():
    patterns = {
        "silinecek": [],
        "veeam_dr_patterns": [],
        "altra_replica_patterns": [],
        "custom_patterns": [
            {
                "id": "alt_tra_der",
                "match": "contains",
                "value": "ALT-TRA-DER",
                "case_insensitive": True,
            }
        ],
    }
    assert classify_vm_name("cust-ALT-TRA-DER-01", patterns) == "custom"
    assert classify_vm_name("prod-web-01", patterns) == "billable"


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
    assert filter_replica_names(names, buckets=("veeam_dr",)) == ["a_DR"]
    assert filter_replica_names(names, buckets=("altra_replica",)) == ["b_replica"]


def test_is_replica_like():
    assert is_replica_like("veeam_dr")
    assert is_replica_like("altra_replica")
    assert is_replica_like("custom")
    assert not is_replica_like("billable")
    assert not is_replica_like("silinecek")


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

    split = reconcile_vendor_counts(
        veeam_objects=6,
        zerto_vms=4,
        veeam_dr_count=6,
        altra_count=2,
    )
    assert split["replica_vm_count"] == 8
    assert split["gap"] == -2
    assert split["altra_count"] == 2


def test_reconcile_handles_none():
    result = reconcile_vendor_counts(None, None, None)
    assert result["replica_vm_count"] == 0
    assert result["gap"] == 0
    assert result["status"] == "ok"


def test_classify_veeam_session_or_job_type():
    assert classify_veeam_session_or_job_type("ReplicaJob") == "replica"
    assert classify_veeam_session_or_job_type("VSphereReplica") == "replica"
    assert classify_veeam_session_or_job_type("BackupJob") == "backup"
    assert classify_veeam_session_or_job_type("Backup") == "backup"
    assert classify_veeam_session_or_job_type("Unknown") == "other"
    assert classify_veeam_session_or_job_type(None) == "other"


def test_load_replica_patterns_seed_v2():
    clear_replica_patterns_cache()
    cfg = load_replica_patterns()
    assert int(cfg.get("version") or 0) >= 2
    assert any(
        str(r.get("value", "")).lower() == "silinecek"
        for r in (cfg.get("silinecek") or [])
    )
    suffixes = {
        str(r.get("value", "")).upper()
        for r in (cfg.get("veeam_dr_patterns") or [])
        if r.get("match") == "suffix"
    }
    assert "_DR" in suffixes
    assert "_DRC" in suffixes
    altra = {
        str(r.get("value", "")).lower()
        for r in (cfg.get("altra_replica_patterns") or [])
    }
    assert "_replica" in altra or any("replica" in v for v in altra)
    assert isinstance(cfg.get("custom_patterns"), list)
