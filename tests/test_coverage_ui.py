"""Datalake coverage UI builders + empty-state contract."""

from src.services.api_client import _EMPTY_HMDL_COVERAGE
from src.utils.hmdl_sync_ui import (
    build_coverage_section,
    build_coverage_summary,
    build_coverage_table,
    coverage_status_badge,
)

_SAMPLE = {
    "summary": {
        "cluster": {"all": {"total": 2, "collected": 1, "missing": 1, "live": 1}},
        "ibm_host": {"total": 1, "collected": 1, "missing": 0, "live": 1},
    },
    "clusters": [
        {"source": "vmware", "cluster_name": "DC13-G3-CLS", "dc": "DC13", "status": "missing", "reason": "Toplanmıyor"},
        {"source": "nutanix", "cluster_name": "DC13-G12-SSD", "dc": "DC13", "status": "live", "reason": "Canlı"},
    ],
    "ibm_hosts": [
        {"servername": "G2HV12DC13", "dc": "DC13", "status": "live", "reason": "Canlı"},
    ],
}


def test_empty_coverage_contract():
    assert _EMPTY_HMDL_COVERAGE["clusters"] == []
    assert _EMPTY_HMDL_COVERAGE["ibm_hosts"] == []
    assert "summary" in _EMPTY_HMDL_COVERAGE
    assert "locations" in _EMPTY_HMDL_COVERAGE


def test_coverage_status_badge_renders():
    for status in ("live", "stale", "missing", "extra", "unknown"):
        assert coverage_status_badge(status) is not None


def test_build_coverage_summary_renders():
    assert build_coverage_summary(_SAMPLE["summary"]) is not None


def test_build_coverage_table_renders_with_rows():
    assert build_coverage_table(_SAMPLE["clusters"], _SAMPLE["ibm_hosts"]) is not None


def test_build_coverage_table_empty_state():
    # No rows → an alert component, not a crash.
    assert build_coverage_table([], []) is not None


def test_build_coverage_section_composes():
    assert build_coverage_section(_SAMPLE) is not None
