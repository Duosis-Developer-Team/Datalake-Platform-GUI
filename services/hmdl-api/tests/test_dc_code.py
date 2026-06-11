"""Unit tests for DC code extraction."""

from app.services.dc_code import dc_code_from_proxy_id, extract_dc_code


def test_extract_dc_code_from_location_name():
    assert extract_dc_code("DC13") == "DC13"
    assert extract_dc_code("Equinix DC18") == "DC18"
    assert extract_dc_code("AZ11") == "AZ11"
    assert extract_dc_code("ICT11") == "ICT11"


def test_extract_dc_code_excludes_dh_sub_locations():
    assert extract_dc_code("DH3") == ""


def test_extract_dc_code_empty():
    assert extract_dc_code("") == ""
    assert extract_dc_code(None) == ""


def test_dc_code_from_proxy_id():
    assert dc_code_from_proxy_id("DC18-NIFI1") == "DC18"
    assert dc_code_from_proxy_id("UZ11-NIFI2") == "UZ11"
    assert dc_code_from_proxy_id("") == ""
