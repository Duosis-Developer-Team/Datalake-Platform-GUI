"""Veeam session_type YAML mapping + Backup category tab values."""
from __future__ import annotations

from shared.backup.replica_classifier import (
    classify_veeam_session_or_job_type,
    clear_veeam_session_mapping_cache,
    load_veeam_session_mapping,
)


BACKUP_CATEGORY_TABS = ("image", "application", "veeam", "zerto")
VEEAM_MODE_TABS = ("replication", "backup")


def test_load_veeam_session_mapping_seed():
    clear_veeam_session_mapping_cache()
    cfg = load_veeam_session_mapping()
    assert int(cfg.get("version") or 0) >= 1
    rep = {str(t) for t in (cfg.get("veeam_replication_session_types") or [])}
    bak = {str(t) for t in (cfg.get("veeam_backup_session_types") or [])}
    assert "ReplicaJob" in rep
    assert "VSphereReplica" in rep
    assert "BackupJob" in bak
    assert "Backup" in bak


def test_classify_uses_yaml_override_lists():
    mapping = {
        "veeam_replication_session_types": ["CustomReplicaType"],
        "veeam_backup_session_types": ["CustomBackupType"],
    }
    assert classify_veeam_session_or_job_type("CustomReplicaType", mapping) == "replica"
    assert classify_veeam_session_or_job_type("CustomBackupType", mapping) == "backup"
    # Unlisted still uses contains heuristics
    assert classify_veeam_session_or_job_type("SomethingReplica", mapping) == "replica"
    assert classify_veeam_session_or_job_type("SomethingBackup", mapping) == "backup"


def test_backup_category_and_veeam_mode_tab_values():
    assert "veeam" in BACKUP_CATEGORY_TABS
    assert "zerto" in BACKUP_CATEGORY_TABS
    assert "replication" not in BACKUP_CATEGORY_TABS
    assert set(VEEAM_MODE_TABS) == {"replication", "backup"}
