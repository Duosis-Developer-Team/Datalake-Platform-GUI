"""Unit tests for VMware datastore name classification (Veeam / NetBackup)."""
from __future__ import annotations

from shared.backup.datastore_classifier import classify_datastore_name


def test_classify_veeam_datastore():
    assert classify_datastore_name("DC13-veeam-repo01") == "veeam"
    assert classify_datastore_name("VeeamBackup_DS") == "veeam"


def test_classify_netbackup_before_veeam():
    assert classify_datastore_name("NBU-pool-1") == "netbackup"
    assert classify_datastore_name("dc13-nbu-veeam-odd") == "netbackup"


def test_classify_other_and_empty():
    assert classify_datastore_name("KM-SSD-01") == "other"
    assert classify_datastore_name("") == "other"
    assert classify_datastore_name(None) == "other"


def test_zerto_token_opt_in_only():
    assert classify_datastore_name("zerto-journal-01") == "other"
    assert classify_datastore_name("zerto-journal-01", enable_zerto_token=True) == "zerto"
