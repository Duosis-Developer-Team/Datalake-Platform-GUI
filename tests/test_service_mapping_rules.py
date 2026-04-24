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
        ("Remote Backup Hizmeti (Nutanix)", "virt_nutanix"),
        ("Veeam something backup", "backup_veeam"),
        ("FortiGate VM02", "firewall_fortigate"),
        ("Red Hat Enterprise Linux 9 subscription", "licensing_redhat"),
        ("Totally unknown SKU xyz", "other"),
    ],
)
def test_match_product_name(name, expected):
    cats, rules = load_rule_pack()
    page_key, meta = match_product_name(name, categories=cats, rules=rules)
    assert page_key == expected
    assert "gui_tab_binding" in meta
