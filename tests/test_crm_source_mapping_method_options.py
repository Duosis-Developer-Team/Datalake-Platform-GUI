"""The alias UI must only offer methods that mean something for the source."""
from src.utils.crm_source_mapping_ui import MATCH_METHOD_OPTIONS, method_options_for_source


def test_method_options_exclude_id_exact_for_name_sources():
    for source in ("virtualization", "netbox_vm_customer", "backup_veeam", "s3_icos", "itsm_servicecore"):
        values = [o["value"] for o in method_options_for_source(source)]
        assert "id_exact" not in values, f"{source} must not offer id_exact"
        assert values == ["contains", "prefix", "suffix", "exact"]


def test_method_options_are_id_only_for_id_sources():
    for source in ("physical_device", "auranotify"):
        values = [o["value"] for o in method_options_for_source(source)]
        assert values == ["id_exact"]


def test_every_option_has_a_label():
    for source in ("virtualization", "physical_device"):
        for option in method_options_for_source(source):
            assert option["label"]


def test_legacy_constant_still_lists_every_method():
    # Kept for backward compatibility with existing importers.
    assert [o["value"] for o in MATCH_METHOD_OPTIONS] == [
        "contains", "prefix", "suffix", "exact", "id_exact",
    ]
