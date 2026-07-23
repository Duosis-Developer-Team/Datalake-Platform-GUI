import pytest
from shared.licensing.os_classifier import classify, is_licensed, LICENSED_FAMILIES


@pytest.mark.parametrize("raw,expected_family", [
    # RHEL — display strings
    ("Red Hat Enterprise Linux 8 (64-bit)", "rhel"),
    ("Red Hat Enterprise Linux 9", "rhel"),
    ("RHEL 7", "rhel"),
    # SUSE
    ("SUSE Linux Enterprise 15 (64-bit)", "suse"),
    ("SUSE Linux Enterprise Server 12 SP5", "suse"),
    ("SLES 15", "suse"),
    ("SUSE Linux Enterprise Server for SAP Applications", "suse"),
    # Windows
    ("Microsoft Windows Server 2019 (64-bit)", "windows"),
    ("Microsoft Windows Server 2016 (64-bit)", "windows"),
    ("Windows Server 2022", "windows"),
    # Free
    ("Ubuntu Linux (64-bit)", "free"),
    ("CentOS 7 (64-bit)", "free"),
    ("Debian GNU/Linux 11 (64-bit)", "free"),
    ("Rocky Linux 9", "free"),
    ("AlmaLinux 9", "free"),
    ("Oracle Linux 8 (64-bit)", "free"),
    # Unknown
    ("Other Linux (64-bit)", "unknown"),
    ("Other 3.x Linux (64-bit)", "unknown"),
    ("Other (32-bit)", "unknown"),
])
def test_classify_display_strings(raw, expected_family):
    assert classify(raw).family == expected_family


@pytest.mark.parametrize("guest_id,expected_family", [
    ("rhel8_64Guest", "rhel"),
    ("rhel9_64Guest", "rhel"),
    ("sles15_64Guest", "suse"),
    ("sles12_64Guest", "suse"),
    ("windows2019srv_64Guest", "windows"),
    ("windows9Server64Guest", "windows"),
    ("centos8_64Guest", "free"),
    ("ubuntu64Guest", "free"),
    ("debian11_64Guest", "free"),
    ("oracleLinux8_64Guest", "free"),
    ("otherLinux64Guest", "unknown"),
    ("otherGuest", "unknown"),
])
def test_classify_guest_id_enum(guest_id, expected_family):
    assert classify(None, guest_id=guest_id).family == expected_family


def test_guest_id_rescues_ambiguous_display():
    # config display says generic, but the enum is specific
    assert classify("Other Linux (64-bit)", guest_id="rhel8_64Guest").family == "rhel"


@pytest.mark.parametrize("raw", [None, "", "   ", "\t"])
def test_empty_is_unknown_none(raw):
    r = classify(raw)
    assert r.family == "unknown"
    assert r.confidence == "none"


def test_case_insensitive():
    assert classify("red hat ENTERPRISE linux").family == "rhel"
    assert classify("MICROSOFT WINDOWS SERVER 2019").family == "windows"


def test_confidence_confirmed_for_matches():
    assert classify("Red Hat Enterprise Linux 8").confidence == "confirmed"
    assert classify("Ubuntu Linux").confidence == "confirmed"


def test_confidence_none_for_unknown():
    assert classify("Other Linux").confidence == "none"


def test_is_licensed():
    assert is_licensed("rhel") is True
    assert is_licensed("suse") is True
    assert is_licensed("windows") is True
    assert is_licensed("free") is False
    assert is_licensed("unknown") is False
    assert LICENSED_FAMILIES == frozenset({"rhel", "suse", "windows"})
