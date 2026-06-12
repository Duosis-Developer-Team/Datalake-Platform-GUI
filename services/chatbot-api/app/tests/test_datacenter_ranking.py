"""Tests for datacenter summary normalization, ranking, and synthesis."""

from __future__ import annotations

from app.services import analysis_synthesizer, datacenter_ranking
from app.services.evidence_evaluator import EvidenceEvaluation, evaluate
from app.services.planner import IntentPlan
from app.services.tool_registry import (
    _normalize_datacenter_summary_list,
    ranking_rows_from_summary,
)
from app.services.tool_registry import ToolResult


_DC_CODES = ("AZ11", "DC11", "DC12", "DC13", "DC14", "DC15", "DC16", "DC17", "ICT11")


def _sample_dcs(n: int = 9) -> list[dict]:
    return [
        {
            "id": _DC_CODES[i] if i < len(_DC_CODES) else f"DC{i}",
            "name": _DC_CODES[i] if i < len(_DC_CODES) else f"DC {i}",
            "location": "Istanbul" if _DC_CODES[i] == "DC11" else "Ankara",
            "vm_count": 100 + i * 50,
            "host_count": 10 + i,
            "stats": {
                "used_cpu_pct": 10.0 + i * 5,
                "used_ram_pct": 20.0 + i * 6,
                "used_storage_pct": 30.0,
            },
        }
        for i in range(n)
    ]


def test_normalize_datacenter_summary_keeps_all_ranking_rows():
    payload = _sample_dcs(9)
    payload[0]["id"] = "AZ11"
    summary = _normalize_datacenter_summary_list(payload)
    assert summary["_count"] == 9
    assert len(summary["ranking_rows"]) == 9
    assert "_sample" not in summary
    assert summary["ranking_rows"][0]["used_cpu_pct"] is not None


def test_ranking_rows_from_summary():
    summary = _normalize_datacenter_summary_list(_sample_dcs(3))
    rows = ranking_rows_from_summary(summary)
    assert len(rows) == 3


def test_rank_datacenters_by_cpu():
    summary = _normalize_datacenter_summary_list(_sample_dcs(5))
    rows = ranking_rows_from_summary(summary)
    ranked = datacenter_ranking.rank_datacenters(rows, "cpu")
    assert ranked[0]["rank"] == 1
    assert ranked[0]["used_cpu_pct"] >= ranked[-1]["used_cpu_pct"]


def test_rank_datacenters_by_memory():
    rows = [
        {"id": "A", "used_cpu_pct": 10, "used_ram_pct": 90, "vm_count": 1},
        {"id": "B", "used_cpu_pct": 90, "used_ram_pct": 10, "vm_count": 1},
    ]
    ranked = datacenter_ranking.rank_datacenters(rows, "memory")
    assert ranked[0]["id"] == "A"


def test_synthesizer_datacenter_ranking_profile():
    payload = _sample_dcs(9)
    by_id = {dc["id"]: dc for dc in payload}
    by_id["AZ11"]["stats"]["used_cpu_pct"] = 4.9
    by_id["DC11"]["stats"]["used_cpu_pct"] = 51.8
    by_id["DC11"]["stats"]["used_ram_pct"] = 74.5
    by_id["DC11"]["vm_count"] = 1458
    payload = list(by_id.values())
    summary = _normalize_datacenter_summary_list(payload)
    results = [
        ToolResult(
            "get_datacenters_summary",
            "success",
            "datacenter-api:/api/v1/datacenters/summary",
            summary=summary,
            rows=9,
        )
    ]
    plan = IntentPlan(
        analysis_profile="datacenter_ranking",
        ranking_metric="cpu",
        entity_type="datacenter",
    )
    ev = evaluate(plan, results)
    assert ev.enough_for_answer
    analysis = analysis_synthesizer.synthesize(plan, results, ev)
    dr = analysis.extra["datacenter_ranking"]
    assert dr["analyzed_count"] == 9
    assert dr["winner"]["id"] == "DC11"
    assert dr["metric_used"] == "cpu"
    assert dr.get("narrative_summary", {}).get("winner_id") == "DC11"
    ctx = analysis.as_context()
    dr_ctx = (ctx.get("extra") or {}).get("datacenter_ranking") or {}
    assert "ranking_table" not in dr_ctx
    assert "narrative_summary" in dr_ctx


def test_evaluator_datacenter_ranking_high_confidence():
    summary = _normalize_datacenter_summary_list(_sample_dcs(4))
    results = [
        ToolResult("get_datacenters_summary", "success", "api", summary=summary, rows=4)
    ]
    plan = IntentPlan(analysis_profile="datacenter_ranking", ranking_metric="composite")
    ev = evaluate(plan, results)
    assert ev.confidence == "high"
    assert len(ev.primary_rows) == 4
