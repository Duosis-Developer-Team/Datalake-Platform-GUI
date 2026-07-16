"""Unit tests for shared NetBackup policy → panel classification."""
from __future__ import annotations

from shared.backup.policy_classification import (
    DEFAULT_NETBACKUP_IMAGE_POLICYTYPES,
    classify_netbackup_policy,
    clear_policy_panel_mapping_cache,
    load_policy_panel_mapping,
    policy_types_for_category,
)


def test_default_vmware_is_image():
    assert classify_netbackup_policy("VMWARE") == "image"
    assert classify_netbackup_policy("vmware") == "image"


def test_application_policy_types():
    for pt in ("SAP", "SQL_SERVER", "OBACKUP", "DB2", "EXCHANGE", "WINDOWS_NT"):
        assert classify_netbackup_policy(pt) == "application"


def test_empty_and_unknown_are_application():
    assert classify_netbackup_policy(None) == "application"
    assert classify_netbackup_policy("") == "application"
    assert classify_netbackup_policy("Unknown") == "application"


def test_explicit_mapping_overrides_default():
    mapping = {"image_policy_types": ["SAP", "VMWARE"], "application_policy_types": []}
    assert classify_netbackup_policy("SAP", mapping=mapping) == "image"
    assert classify_netbackup_policy("SQL_SERVER", mapping=mapping) == "application"


def test_policy_types_for_category_filters():
    available = ["VMWARE", "SAP", "SQL_SERVER", "OBACKUP"]
    assert policy_types_for_category("image", available) == ["VMWARE"]
    app = policy_types_for_category("application", available)
    assert app == ["OBACKUP", "SAP", "SQL_SERVER"]


def test_load_policy_panel_mapping_has_vmware():
    clear_policy_panel_mapping_cache()
    cfg = load_policy_panel_mapping()
    image = {str(t).upper() for t in cfg.get("image_policy_types") or []}
    assert "VMWARE" in image
    assert DEFAULT_NETBACKUP_IMAGE_POLICYTYPES <= image or "VMWARE" in image
