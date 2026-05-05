"""Panel mapping rules for IBM Power / NVMi (shared/sellable/panel_mapping)."""

from __future__ import annotations

from shared.sellable import panel_mapping as pm


def test_ibm_power_cpu_classified():
    assert pm.classify("Bulutistan Managed Cloud IBM Power — CPU 1 Core", None) == "virt_power_cpu"


def test_ibm_power_ram_classified():
    assert pm.classify("IBM Power — RAM 1 GB", None) == "virt_power_ram"


def test_sap_power_hana_still_distinct():
    assert pm.classify("SAP Power HANA — CPU", None) == "virt_power_hana_cpu"


def test_nvmi_storage_classified():
    assert pm.classify("Enterprise NVMi Storage Pool", None) == "virt_power_storage"
