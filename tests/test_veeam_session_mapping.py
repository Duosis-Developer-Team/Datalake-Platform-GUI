"""Veeam session_type YAML mapping + Backup category tab values."""
from __future__ import annotations

from shared.backup.replica_classifier import (
    classify_veeam_session_or_job_type,
    clear_veeam_session_mapping_cache,
    load_veeam_session_mapping,
    veeam_session_backup_category,
)


BACKUP_CATEGORY_TABS = ("image", "application", "replication")
VEEAM_MODE_TABS = ("replication", "backup")


def test_load_veeam_session_mapping_seed():
    clear_veeam_session_mapping_cache()
    cfg = load_veeam_session_mapping()
    assert int(cfg.get("version") or 0) >= 1
    rep = {str(t) for t in (cfg.get("veeam_replication_session_types") or [])}
    img = {str(t) for t in (cfg.get("veeam_image_backup_session_types") or [])}
    app = {str(t) for t in (cfg.get("veeam_application_backup_session_types") or [])}
    assert "ReplicaJob" in rep
    assert "VSphereReplica" in rep
    assert "BackupJob" in img
    assert "Backup" in img
    assert "SqlBackup" in app


def test_classify_uses_yaml_override_lists():
    mapping = {
        "veeam_replication_session_types": ["CustomReplicaType"],
        "veeam_image_backup_session_types": ["CustomImageBackup"],
        "veeam_application_backup_session_types": ["CustomAppBackup"],
        "veeam_backup_session_types": ["LegacyBackupType"],
    }
    assert classify_veeam_session_or_job_type("CustomReplicaType", mapping) == "replica"
    assert classify_veeam_session_or_job_type("CustomImageBackup", mapping) == "image_backup"
    assert classify_veeam_session_or_job_type("CustomAppBackup", mapping) == "application_backup"
    assert classify_veeam_session_or_job_type("LegacyBackupType", mapping) == "backup"
    assert classify_veeam_session_or_job_type("SomethingReplica", mapping) == "replica"
    assert classify_veeam_session_or_job_type("SomethingBackup", mapping) == "image_backup"
    assert classify_veeam_session_or_job_type("OracleSomething", mapping) == "application_backup"


def test_veeam_session_backup_category():
    assert veeam_session_backup_category("ReplicaJob") == "replication"
    assert veeam_session_backup_category("BackupJob") == "image"
    assert veeam_session_backup_category("SqlBackup") == "application"


def test_backup_category_and_veeam_mode_tab_values():
    assert set(BACKUP_CATEGORY_TABS) == {"image", "application", "replication"}
    assert "veeam" not in BACKUP_CATEGORY_TABS
    assert "zerto" not in BACKUP_CATEGORY_TABS
    assert set(VEEAM_MODE_TABS) == {"replication", "backup"}
