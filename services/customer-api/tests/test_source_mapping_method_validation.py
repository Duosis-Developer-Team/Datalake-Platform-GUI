"""id_exact must be rejected for name-matched sources at the API boundary.

id_exact correlates by numeric tenant id. On a name source the SQL resolver
drops the rule and the in-memory classifier used to read it as `contains`, so
the resource disappeared from both the customer view and the Unmapped page.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.routers.sales import validate_source_mappings


def test_id_exact_rejected_on_name_sources():
    for source in ("virtualization", "netbox_vm_customer", "backup_veeam", "s3_icos", "itsm_servicecore"):
        with pytest.raises(HTTPException) as exc:
            validate_source_mappings([{"data_source": source, "match_method": "id_exact", "match_value": "5"}])
        assert exc.value.status_code == 422
        assert "id_exact" in str(exc.value.detail)


def test_id_exact_allowed_on_id_sources():
    for source in ("physical_device", "auranotify"):
        validate_source_mappings([{"data_source": source, "match_method": "id_exact", "match_value": "5"}])


def test_name_methods_rejected_on_id_sources():
    with pytest.raises(HTTPException) as exc:
        validate_source_mappings([{"data_source": "physical_device", "match_method": "contains", "match_value": "x"}])
    assert exc.value.status_code == 422


def test_valid_name_methods_pass():
    for method in ("contains", "prefix", "suffix", "exact"):
        validate_source_mappings([{"data_source": "virtualization", "match_method": method, "match_value": "Deneme"}])


def test_unknown_method_is_rejected():
    with pytest.raises(HTTPException) as exc:
        validate_source_mappings([{"data_source": "virtualization", "match_method": "regex", "match_value": "x"}])
    assert exc.value.status_code == 422


def test_empty_list_is_fine():
    validate_source_mappings([])
