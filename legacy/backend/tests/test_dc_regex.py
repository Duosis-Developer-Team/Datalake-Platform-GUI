import re

from app.services.db_service import _DC_CODE_RE


def test_regex_matches_dc_code_with_two_digit_number():
    assert _DC_CODE_RE.search("DC11") is not None


def test_regex_matches_dc_code_embedded_in_hostname():
    m = _DC_CODE_RE.search("server-DC11-host1")
    assert m is not None
    assert m.group(1).upper() == "DC11"


def test_regex_matches_az_code():
    assert _DC_CODE_RE.search("AZ11") is not None


def test_regex_matches_ict_code():
    assert _DC_CODE_RE.search("ICT11") is not None


def test_regex_matches_uz_code():
    assert _DC_CODE_RE.search("UZ11") is not None


def test_regex_matches_dh_code():
    assert _DC_CODE_RE.search("DH11") is not None


def test_regex_is_case_insensitive_with_lowercase_dc():
    m = _DC_CODE_RE.search("dc11-server")
    assert m is not None


def test_regex_is_case_insensitive_with_lowercase_az():
    m = _DC_CODE_RE.search("az11")
    assert m is not None


def test_regex_is_case_insensitive_with_lowercase_ict():
    m = _DC_CODE_RE.search("ict11")
    assert m is not None


def test_regex_does_not_match_plain_text_without_code():
    assert _DC_CODE_RE.search("random-server-name") is None


def test_regex_does_not_match_partial_prefix_without_digits():
    assert _DC_CODE_RE.search("DCserver") is None


def test_regex_captures_correct_group_for_dc16():
    m = _DC_CODE_RE.search("DC16-backup")
    assert m is not None
    assert m.group(1).upper() == "DC16"


def test_regex_captures_multiple_occurrences_with_findall():
    results = _DC_CODE_RE.findall("DC11 and DC12 and AZ11")
    assert len(results) == 3
    upper = [r.upper() for r in results]
    assert "DC11" in upper
    assert "DC12" in upper
    assert "AZ11" in upper
