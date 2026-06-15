"""Tests for map-reduce investigation coordinator."""

from __future__ import annotations

from unittest.mock import patch

from app.services import investigation_coordinator, investigation_workers
from app.services.investigation_trace import InvestigationTrace
from app.services.planner import IntentPlan
from app.services.tool_registry import ToolResult, _normalize_datacenter_summary_list


def _summary_result(n: int = 3) -> ToolResult:
    payload = [
        {
            "id": f"DC{i}",
            "name": f"DC{i}",
            "location": "City",
            "vm_count": i * 10,
            "host_count": i,
            "stats": {"used_cpu_pct": i * 10.0, "used_ram_pct": i * 5.0},
        }
        for i in range(1, n + 1)
    ]
    summary = _normalize_datacenter_summary_list(payload)
    return ToolResult(
        "get_datacenters_summary",
        "success",
        "datacenter-api:/api/v1/datacenters/summary",
        summary=summary,
        rows=n,
    )


def test_summary_ranking_findings():
    results = [_summary_result(4)]
    findings = investigation_workers.summary_ranking_findings(results)
    assert len(findings) == 4
    assert findings[0].entity_id == "DC1"


def test_coordinator_no_extra_when_full_coverage():
    plan = IntentPlan(analysis_profile="datacenter_ranking", ranking_metric="cpu")
    trace = InvestigationTrace()
    outcome = investigation_coordinator.run(plan, [_summary_result(3)], None, trace)
    assert not outcome.extra_results
    assert len(outcome.findings) == 3


def test_detail_workers_parallel():
    def fake_execute(name, args, auth):
        dc = args.get("dc_code")
        return ToolResult(
            name,
            "success",
            f"datacenter-api:/api/v1/datacenters/{dc}",
            summary={
                "meta": {"name": dc, "location": "X"},
                "intel": {"cpu_cap": 100, "cpu_used": 50, "ram_cap": 200, "ram_used": 80, "vms": 5, "hosts": 2},
            },
            rows=1,
        )

    with patch("app.services.investigation_workers.execute_tool", side_effect=fake_execute):
        batch = investigation_workers.run_detail_workers(["DC1", "DC2"], {}, None)
    assert len(batch.extra_results) == 2
    assert len(batch.findings) == 2
    assert batch.findings[0].metrics["used_cpu_pct"] == 50.0


def test_coordinator_fans_out_for_missing_metrics():
    payload = [
        {
            "id": "DC1",
            "name": "DC1",
            "location": "X",
            "vm_count": None,
            "host_count": None,
            "stats": {},
        }
    ]
    summary = _normalize_datacenter_summary_list(payload)
    results = [
        ToolResult("get_datacenters_summary", "success", "api", summary=summary, rows=1)
    ]
    plan = IntentPlan(analysis_profile="datacenter_ranking", ranking_metric="cpu")

    def fake_execute(name, args, auth):
        dc = args.get("dc_code")
        return ToolResult(
            name,
            "success",
            f"datacenter-api:/api/v1/datacenters/{dc}",
            summary={
                "meta": {"name": dc, "location": "X"},
                "intel": {"cpu_cap": 100, "cpu_used": 70, "ram_cap": 100, "ram_used": 40, "vms": 3, "hosts": 1},
            },
        )

    trace = InvestigationTrace()
    with patch("app.services.investigation_workers.execute_tool", side_effect=fake_execute):
        outcome = investigation_coordinator.run(plan, results, None, trace)
    assert len(outcome.extra_results) == 1
    assert trace.entries[-1].tool == "get_datacenter_detail"
