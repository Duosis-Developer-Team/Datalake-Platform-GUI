"""Unit tests for datalake coverage logic (Location derivation, status, reason)."""

from app.services.coverage import (
    derive_dc,
    empty_bucket,
    reason_text,
    row_status,
    tally,
)


def test_derive_dc_from_cluster_prefix():
    assert derive_dc("DC13-G3-CLS") == "DC13"
    assert derive_dc("AZ11-G1-SSD") == "AZ11"
    assert derive_dc("ICT21-G2-HYBRID") == "ICT21"


def test_derive_dc_from_ibm_embedded():
    assert derive_dc("G2HV12DC13") == "DC13"
    assert derive_dc("G10HV2DC15") == "DC15"


def test_derive_dc_other_when_no_token():
    assert derive_dc("Mg-CLS") == "Diğer"
    assert derive_dc("PRISM-Central") == "Diğer"
    assert derive_dc(None) == "Diğer"


def test_row_status():
    assert row_status(True, True, True) == "live"
    assert row_status(True, True, False) == "stale"
    assert row_status(False, True, False) == "missing"
    assert row_status(True, False, False) == "extra"
    assert row_status(False, False, False) == "unknown"
    assert row_status(False, True, False, is_offline=True) == "offline"


def test_reason_text_stale_includes_clock():
    from datetime import datetime, timezone

    ts = datetime(2026, 8, 2, 3, 3, 1, tzinfo=timezone.utc)
    assert reason_text("stale", ts, []) == "Bayat — son veri 02.08.2026 03:03"


def test_reason_missing_with_target_issues():
    issues = [{"dc_code": "DC13", "platform": "VmWare", "check_status": "telnet_fail"}]
    r = reason_text("missing", None, issues)
    assert "DC13/VmWare" in r
    assert "telnet_fail" in r


def test_reason_missing_without_issues():
    assert "Toplanmıyor" in reason_text("missing", None, [])
    assert "collector yok" in reason_text("missing", None, [], source="ibm")
    assert "Offline" in reason_text("offline", None, [])


def test_reason_live_and_extra():
    assert reason_text("live", None, []) == "Canlı"
    assert "Envanter dışı" in reason_text("extra", None, [])


def test_tally_accumulates():
    b = empty_bucket()
    tally(b, True, True, True)
    tally(b, False, True, False)
    tally(b, False, True, False, is_offline=True)
    assert b == {"total": 3, "collected": 1, "missing": 1, "live": 1, "offline": 1}
