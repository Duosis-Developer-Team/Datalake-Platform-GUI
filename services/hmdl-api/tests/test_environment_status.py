"""Unit tests for environment-level connectivity status."""

from app.services.environment_status import (
    count_environments,
    resolve_environment_status,
)


def test_no_configured_proxy():
    assert resolve_environment_status("no_configured_proxy", {}) == "no_configured_proxy"


def test_connectivity_issue_when_failures_present():
    counts = {"connectivity_issue": 2, "monitored": 10}
    assert resolve_environment_status("configured", counts) == "connectivity_issue"


def test_connected_when_no_connectivity_failures():
    counts = {"monitored": 10, "pending_distribution": 3}
    assert resolve_environment_status("configured", counts) == "connected"


def test_count_environments():
    nodes = [
        {"environment_status": "connected"},
        {"environment_status": "connectivity_issue"},
        {"environment_status": "no_configured_proxy"},
    ]
    assert count_environments(nodes) == (1, 1, 1)
