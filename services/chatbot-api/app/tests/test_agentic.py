from app.services import agent_loop, planner, tool_registry
from app.services.analysis_synthesizer import synthesize
from app.services.evidence_evaluator import evaluate
from app.services.planner import IntentPlan
from app.services.tool_registry import ToolResult

VM_Q = "DC13'teki VM'lerin son bir haftada en çok CPU tüketen 10 tanesini listele. Direkt DB kullan."


def _vm_top(rows):
    return ToolResult(
        "get_dc_vm_cpu_top", "success", "postgres:db_get_dc_vm_cpu_top",
        summary={"row_count": len(rows), "rows": rows}, rows=len(rows),
    )


def _vm_summary(rows):
    return ToolResult(
        "get_dc_vm_cpu_summary", "success", "postgres:db_get_dc_vm_cpu_summary",
        summary={"row_count": len(rows), "rows": rows}, rows=len(rows),
    )


def _row(name, host, avg, mx, src="nutanix", unit="percent", samples=100, last="2026-06-04 10:00"):
    return {
        "source": src, "vm_name": name, "host_name": host, "cluster": None,
        "cpu_pct_avg": avg, "cpu_pct_max": mx, "cpu_used_avg": avg, "cpu_total": None,
        "unit": unit, "sample_count": samples,
        "first_collection_time": last, "last_collection_time": last,
    }


# --- planner ---------------------------------------------------------------- #


def test_planner_parses_vm_top_db_intent():
    p = planner.make_plan(VM_Q, None)
    assert p.entity_type == "vm"
    assert p.metric == "cpu"
    assert p.dc_code == "DC13"
    assert p.days == 7
    assert p.requested_source == "db"
    assert p.requested_output == "top_list"
    assert p.limit == 10
    assert any(t["tool"] == "get_dc_vm_cpu_top" for t in p.initial_tools)


def test_planner_distinguishes_host_from_vm():
    assert planner.make_plan("DC13 host bazlı CPU özetle", None).entity_type == "host"
    assert planner.make_plan("DC13 VM bazlı CPU özetle", None).entity_type == "vm"


# --- evidence evaluator ----------------------------------------------------- #


def _plan():
    return IntentPlan(entity_type="vm", metric="cpu", dc_code="DC13", days=7,
                      requested_output="top_list", needs_analysis=True,
                      analysis_profile="cpu_usage")


def test_evaluator_requests_summary_after_top():
    ev = evaluate(_plan(), [_vm_top([_row("a", "h1", 50, 60)])])
    assert ev.enough_for_answer is False
    assert ev.recommended_followup_tools[0].tool == "get_dc_vm_cpu_summary"


def test_evaluator_empty_top_falls_back_to_latest():
    ev = evaluate(_plan(), [_vm_top([])])
    assert ev.enough_for_answer is False
    assert ev.recommended_followup_tools[0].tool == "get_dc_vm_cpu_latest"


def test_evaluator_enough_after_summary_no_concentration():
    ev = evaluate(_plan(), [_vm_top([_row("a", "h1", 50, 60), _row("b", "h2", 40, 55)]),
                            _vm_summary([{"source": "nutanix", "vm_count": 2}])])
    assert ev.enough_for_answer is True


def test_evaluator_low_sample_lowers_confidence():
    ev = evaluate(_plan(), [_vm_top([_row("a", "h1", 50, 60, samples=2)]),
                            _vm_summary([{"source": "nutanix", "vm_count": 1}])])
    assert ev.confidence in ("medium", "low")


def test_evaluator_stale_data_warning():
    ev = evaluate(_plan(), [_vm_top([_row("a", "h1", 50, 60, last="2026-01-01 00:00")]),
                            _vm_summary([{"source": "nutanix", "vm_count": 1}])])
    assert any("stale" in w for w in ev.data_quality_warnings)


def test_evaluator_concentration_requests_host_context():
    rows = [_row(f"vm{i}", "sameHost", 50, 60) for i in range(4)]
    ev = evaluate(_plan(), [_vm_top(rows), _vm_summary([{"source": "nutanix", "vm_count": 4}])])
    assert ev.recommended_followup_tools and ev.recommended_followup_tools[0].tool == "get_dc_host_cpu_summary"


# --- analysis synthesizer --------------------------------------------------- #


def test_synthesizer_sustained_high_is_critical():
    rows = [_row("a", "h1", 90, 95, src="ibm", unit="cores")]
    res = [_vm_top(rows), _vm_summary([{"source": "ibm", "vm_count": 1}])]
    ev = evaluate(_plan(), res)
    an = synthesize(_plan(), res, ev)
    assert "a" in an.sustained_high
    assert an.risk_level == "critical"


def test_synthesizer_peak_spike_detected():
    rows = [_row("a", "h1", 30, 96)]  # low avg, high peak
    res = [_vm_top(rows), _vm_summary([{"source": "nutanix", "vm_count": 1}])]
    an = synthesize(_plan(), res, evaluate(_plan(), res))
    assert "a" in an.peak_spikes
    assert an.risk_level in ("high", "medium")


# --- agent loop ------------------------------------------------------------- #


def test_agent_loop_runs_summary_followup(monkeypatch):
    calls = []

    def fake_exec(name, args, auth):
        calls.append(name)
        if name == "get_dc_vm_cpu_top":
            return _vm_top([_row("a", "h1", 88, 95, src="ibm", unit="cores"),
                            _row("b", "h2", 40, 55)])
        if name == "get_dc_vm_cpu_summary":
            return _vm_summary([{"source": "ibm", "vm_count": 1}, {"source": "nutanix", "vm_count": 1}])
        return ToolResult(name, "success", name, summary={}, rows=0)

    monkeypatch.setattr(tool_registry, "execute_tool", fake_exec)
    out = agent_loop.run(VM_Q, None, None)
    assert "get_dc_vm_cpu_top" in calls
    assert "get_dc_vm_cpu_summary" in calls  # follow-up was triggered
    assert out.iterations >= 2
    assert out.analysis is not None and out.analysis.risk_level == "critical"


def test_agent_loop_dedup_and_caps(monkeypatch):
    seen = []

    def fake_exec(name, args, auth):
        seen.append((name, args.get("days"), args.get("limit")))
        return _vm_top([_row("a", "h1", 50, 60)]) if name == "get_dc_vm_cpu_top" else \
            (_vm_summary([{"source": "nutanix", "vm_count": 1}]) if name == "get_dc_vm_cpu_summary"
             else ToolResult(name, "success", name, summary={}, rows=0))

    monkeypatch.setattr(tool_registry, "execute_tool", fake_exec)
    agent_loop.run(VM_Q, None, None)
    # no (tool, days, limit) tuple appears twice; total calls within the per-turn cap
    assert len(seen) == len(set(seen))
    from app.config import settings

    assert len(seen) <= settings.chatbot_max_tool_calls_per_turn
