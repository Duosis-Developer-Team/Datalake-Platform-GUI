"""Tests for shared.service_mapping rule pack (product name → page_key)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_GUI_ROOT = Path(__file__).resolve().parents[1]
if str(_GUI_ROOT) not in sys.path:
    sys.path.insert(0, str(_GUI_ROOT))

from shared.service_mapping.rules import load_rule_pack, match_product_name  # noqa: E402
from shared.service_mapping.yaml_loader import default_config_path, load_mapping_yaml  # noqa: E402


def test_load_mapping_yaml():
    data = load_mapping_yaml(default_config_path())
    assert isinstance(data, dict)
    if data:
        assert "pages" in data or "version" in data


def test_load_rule_pack():
    cats, rules = load_rule_pack()
    assert "virt_classic" in cats
    assert "other" in cats
    assert len(rules) >= 10


@pytest.mark.parametrize(
    "name,expected",
    [
        # Granular taxonomy v2 — see embedded_rules.json
        ("Hyperconverged Mimari Intel RAM", "virt_hyperconverged_ram"),
        ("Hyperconverged Mimari Intel CPU", "virt_hyperconverged_cpu"),
        ("Hyperconverged Mimari Intel Disk - SSD", "virt_hyperconverged_storage"),
        ("Hyperconverged Mimari Intel Disk - SSD Hybrid - DR", "virt_hyperconverged_storage"),
        ("Klasik Mimari Intel RAM - DR", "virt_classic_ram"),
        ("Klasik Mimari Intel Disk - NVMe", "virt_classic_storage"),
        ("Klasik Mimari Intel CPU", "virt_classic_cpu"),
        ("Klasik Mimari Veeam Replication RAM", "backup_veeam_ram"),
        ("Klasik Mimari Veeam Replication Disk - NVMe", "backup_veeam_storage"),
        ("Klasik Mimari Zerto Replication vCpu", "backup_zerto_cpu"),
        ("Hyperconverged Mimari Zerto Replication Disk - SSD", "backup_zerto_storage"),
        ("SAP Power HANA RAM", "virt_power_ram"),
        ("SAP Power HANA Storage - NVMe", "virt_power_storage"),
        ("SAP Intel HANA CPU", "virt_classic_cpu"),
        ("Hyperconverged \u0130maj Yedekleme Hizmeti", "virt_hyperconverged_storage"),
        ("Klasik Mimari \u0130maj Yedekleme (Veritas Netbackup)", "backup_netbackup_storage"),
        ("Offsite Backup Disk Alan\u0131 (Veeam)", "backup_veeam_storage"),
        ("Remote Backup Hizmeti (Nutanix)", "virt_nutanix"),
        ("FortiGate VM02", "firewall_fortigate"),
        ("Red Hat Enterprise Linux 9 subscription", "licensing_redhat"),
        ("CSP - Microsoft 365 E5", "licensing_microsoft"),
        ("SPLA - MS Windows Server Datacenter Editon", "licensing_microsoft"),
        ("Totally unknown SKU xyz", "other"),
    ],
)
def test_match_product_name(name, expected):
    cats, rules = load_rule_pack()
    page_key, meta = match_product_name(name, categories=cats, rules=rules)
    assert page_key == expected, f"{name!r} -> {page_key!r} (expected {expected!r})"
    assert "gui_tab_binding" in meta


def test_granular_categories_present():
    """Make sure the v2 page_key catalog ships with granular suffix entries."""
    cats, _ = load_rule_pack()
    for key in (
        "virt_hyperconverged_ram",
        "virt_hyperconverged_storage",
        "virt_hyperconverged_cpu",
        "virt_classic_ram",
        "virt_classic_storage",
        "virt_classic_cpu",
        "backup_zerto_storage",
        "backup_zerto_cpu",
        "backup_veeam_ram",
        "backup_netbackup_storage",
        "virt_power_ram",
        "virt_power_storage",
    ):
        assert key in cats, f"missing granular page_key {key!r}"
