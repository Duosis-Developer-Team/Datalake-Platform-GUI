"""Probe verdict semantics + fleet rollup shape."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db.queries import probe as probe_q
from app.services.probe import probe_product, reason_category, script_status

NOW = datetime(2026, 7, 31, 10, 0, tzinfo=timezone.utc)


def _row(**kw):
    base = {
        "probe_id": "nutanix_cluster",
        "collector_type": "Nutanix",
        "bucket": "default",
        "dc_code": "DC13",
        "proxy_id": "proxy-dc13",
        "target_host": "10.0.0.1",
        "entity_name": "Prism-1",
        "success": True,
        "reason": "ok",
        "exit_code": 0,
        "duration_sec": 1.5,
        "stdout_bytes": 100,
        "stderr_bytes": 0,
        "stdout_head": None,
        "stderr_head": None,
        "run_id": "probe-1",
        "awx_job_id": "1",
        "started_at": NOW,
        "finished_at": NOW,
    }
    return base | kw


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("script_missing", "script_missing"),
        ("auth_failed", "auth"),
        ("reject_stderr:403 Client Error", "auth"),
        ("reject_stderr:HATA:", "auth"),
        ("build_argv:Nutanix username/password missing", "auth"),
        ("network_unreachable", "network"),
        ("network_timeout", "network"),
        ("timeout_1800s", "timeout"),
        ("missing_stderr_signal", "no_data"),
        ("missing_stdout_signal", "no_data"),
        ("stdout_too_small", "no_data"),
        ("batch_parse:Extra data", "runner"),
        ("something_new", "other"),
    ],
)
def test_reason_category_routes_failures_to_an_owner(reason, expected):
    assert reason_category(reason, False) == expected


def test_successful_probe_is_never_categorised_as_a_failure():
    assert reason_category("timeout_60s", True) == "ok"


def test_credential_reason_beats_the_generic_timeout_rule():
    # "auth" is checked before "timeout" so a 403 during a slow call stays a credentials job.
    assert reason_category("reject_stderr:403 Client Error after timeout", False) == "auth"


@pytest.mark.parametrize(
    ("collector_type", "product"),
    [
        ("VmWare", "vmware"),
        ("Nutanix", "nutanix"),
        ("Acropolis", "nutanix"),
        ("IBM-HMC", "ibm"),
        ("Veeam", "backup"),
        ("Netbackup", "backup"),
        ("Zerto", "backup"),
        ("Mystery", "other"),
    ],
)
def test_probe_product_groups_acropolis_with_nutanix(collector_type, product):
    assert probe_product(collector_type) == product


@pytest.mark.parametrize(
    ("ok", "total", "status"),
    [(3, 3, "ok"), (1, 3, "partial"), (0, 3, "fail"), (0, 0, "unknown")],
)
def test_script_status(ok, total, status):
    assert script_status(ok, total) == status


def test_build_probe_health_summarises_scripts_dcs_and_reasons(monkeypatch):
    rows = [
        _row(),
        _row(probe_id="nutanix_host"),
        _row(probe_id="nutanix_vm", success=False, reason="auth_failed"),
        _row(
            dc_code="dc18",
            target_host="10.0.0.2",
            entity_name="Prism-2",
            success=False,
            reason="timeout_60s",
        ),
        _row(
            probe_id="ibm_hmc",
            collector_type="IBM-HMC",
            bucket="heavy",
            dc_code="DC14",
            target_host="10.0.0.3",
            success=False,
            reason="script_missing",
        ),
    ]
    monkeypatch.setattr(probe_q, "_fetch_latest", lambda **_: rows)
    monkeypatch.setattr(probe_q, "_fetch_runner_errors", lambda: [])

    out = probe_q.build_probe_health()

    assert out["summary"] == {
        "endpoints": 3,
        "probes": 5,
        "ok": 2,
        "fail": 3,
        "scripts": 4,
        "last_probe_at": NOW,
    }
    by_script = {s["probe_id"]: s for s in out["scripts"]}
    assert by_script["nutanix_cluster"]["endpoints"] == 2
    assert by_script["nutanix_cluster"]["status"] == "partial"
    assert by_script["nutanix_vm"]["status"] == "fail"
    assert by_script["ibm_hmc"]["product"] == "ibm"
    # Scripts are ordered by product so the matrix groups VMware/Nutanix/IBM/backup.
    assert [s["product"] for s in out["scripts"]] == ["ibm", "nutanix", "nutanix", "nutanix"]

    cells = {(c["probe_id"], c["dc"]): c for c in out["matrix"]}
    assert cells[("nutanix_cluster", "DC13")]["ok"] == 1
    assert cells[("nutanix_cluster", "DC18")]["status"] == "fail"
    assert out["dcs"] == ["DC13", "DC14", "DC18"]

    categories = {r["reason"]: r["category"] for r in out["reasons"]}
    assert categories == {
        "auth_failed": "auth",
        "timeout_60s": "timeout",
        "script_missing": "script_missing",
    }


def test_build_probe_health_normalises_dc_and_truncates_log_heads(monkeypatch):
    monkeypatch.setattr(
        probe_q,
        "_fetch_latest",
        lambda **_: [_row(dc_code=None, stdout_head="x" * 900, stderr_head="")],
    )
    monkeypatch.setattr(probe_q, "_fetch_runner_errors", lambda: [])

    item = probe_q.build_probe_health()["items"][0]

    assert item["dc"] == "UNKNOWN"
    assert len(item["stdout_head"]) == 400
    assert item["stderr_head"] is None


def test_probe_rollup_keyed_by_host_reports_partial_endpoints(monkeypatch):
    monkeypatch.setattr(
        probe_q.pool,
        "fetch_all",
        lambda *_a, **_k: [
            {
                "target_host": "10.0.0.1",
                "total": 3,
                "ok": 2,
                "last_probe_at": NOW,
                "reasons": "auth_failed",
            },
            {
                "target_host": "10.0.0.2",
                "total": 1,
                "ok": 1,
                "last_probe_at": NOW - timedelta(hours=6),
                "reasons": None,
            },
        ],
    )

    rollup = probe_q.fetch_probe_rollup_by_host()

    assert rollup["10.0.0.1"]["probe_status"] == "partial"
    assert rollup["10.0.0.1"]["probe_reasons"] == "auth_failed"
    assert rollup["10.0.0.2"]["probe_status"] == "ok"
    assert rollup["10.0.0.2"]["probe_reasons"] is None
