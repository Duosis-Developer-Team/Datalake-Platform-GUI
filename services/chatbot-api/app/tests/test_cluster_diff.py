from app.models.schemas import FrontendContext
from app.services import query_planner
from app.services.analysis_synthesizer import synthesize
from app.services.evidence_evaluator import evaluate
from app.services.planner import IntentPlan
from app.services.tool_registry import ToolResult

DIFF_Q = (
    "vmware ve dc13 için endpointlerden ve database sorgularından aldığın verileri "
    "karşılaştır ve endpointlerde gelmeyip db'de olan clusterları listele"
)


def _tools(plan):
    return [t["tool"] for t in plan.initial_tools]


def _api_clusters(names):
    return ToolResult(
        "get_dc_classic_clusters", "success", "datacenter-api:/clusters/classic",
        summary={"_count": len(names), "items": list(names)}, rows=len(names),
    )


def _db_clusters(rows):
    return ToolResult(
        "get_dc_vmware_clusters_from_db", "success", "postgres:db_get_dc_vmware_clusters",
        summary={"row_count": len(rows), "rows": rows}, rows=len(rows),
    )


def _row(name, ctype="classic", hc=5, vmc=100, last="2026-06-04 13:30"):
    return {"source": "cluster_metrics", "cluster_name": name, "cluster_type": ctype,
            "host_count": hc, "vm_count": vmc, "latest_collection_time": last}


def _plan():
    return IntentPlan(entity_type="cluster", metric="cluster_inventory",
                      metric_key="dc_vmware_cluster_api_db_diff", architecture="classic",
                      calculation="api_db_diff", analysis_profile="cluster_diff", dc_code="DC13")


# --- tool selection ------------------------------------------------------- #


def test_cluster_diff_uses_classic_and_db_tools_not_customer():
    p = query_planner.plan(DIFF_Q, None, None)
    tools = _tools(p)
    assert "get_dc_classic_clusters" in tools
    assert "get_dc_vmware_clusters_from_db" in tools
    assert not any("customer" in t for t in tools)


def test_stale_customer_context_ignored_for_cluster_diff():
    ctx = FrontendContext(selected_customer="Boyner", pathname="/customer/Boyner")
    p = query_planner.plan(DIFF_Q, ctx, None)
    assert not any("customer" in t for t in _tools(p))
    assert p.customer_name is None


# --- comparison logic ----------------------------------------------------- #


def test_cluster_diff_computes_db_only_clusters():
    results = [_api_clusters(["A", "B"]),
               _db_clusters([_row("A"), _row("B"), _row("C"), _row("D")])]
    a = synthesize(_plan(), results, evaluate(_plan(), results))
    assert set(a.extra["db_only_clusters"]) == {"C", "D"}
    assert a.extra["api_cluster_count"] == 2
    assert a.extra["db_cluster_count"] == 4
    assert a.extra["common_count"] == 2
    assert a.risk_level == "medium"


def test_cluster_diff_normalizes_names():
    # case / spacing differences must count as common, not db_only
    results = [_api_clusters(["DC13-KM-CLS"]),
               _db_clusters([_row(" dc13-km-cls "), _row("DC13-KM2-CLS")])]
    a = synthesize(_plan(), results, evaluate(_plan(), results))
    assert a.extra["db_only_clusters"] == ["DC13-KM2-CLS"]


def test_cluster_diff_empty_when_identical():
    results = [_api_clusters(["A", "B"]), _db_clusters([_row("A"), _row("B")])]
    a = synthesize(_plan(), results, evaluate(_plan(), results))
    assert a.extra["db_only_count"] == 0
    assert a.risk_level == "low"


# --- deterministic fallback when the LLM fails ---------------------------- #


def _outcome_with_diff():
    from app.services.agent_loop import AgentOutcome

    results = [
        _api_clusters(["DC13-KM-CLS-NVME"]),
        _db_clusters([_row("DC13-KM-CLS-NVME"), _row("DC13-G11-CLS-HYBRID", "hyperconverged", 8, 513),
                      _row("DC13-G3-CLS", "hyperconverged", 0, 0)]),
    ]
    plan = _plan()
    ev = evaluate(plan, results)
    an = synthesize(plan, results, ev)
    return AgentOutcome(plan=plan, results=results, evaluation=ev, analysis=an, iterations=1)


def test_format_from_analysis_renders_cluster_diff_table():
    from app.services.context_builder import format_from_analysis

    out = format_from_analysis(_outcome_with_diff())
    assert "API cluster count: 1" in out
    assert "DB cluster count: 3" in out
    assert "Endpointte olmayıp DB'de olan cluster count: 2" in out
    assert "DC13-G11-CLS-HYBRID" in out and "DC13-G3-CLS" in out
    assert "| Cluster |" in out
    assert "get_dc_vmware_clusters_from_db" in out


def test_llm_error_falls_back_to_deterministic_answer(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.routers import chatbot as cr
    from app.services.llm_client import LLMError

    monkeypatch.setattr(cr.settings, "chatbot_agentic_mode", True)
    monkeypatch.setattr(cr.agent_loop, "run", lambda *a, **k: _outcome_with_diff())

    class _FailLLM:
        def complete(self, *a, **k):
            raise LLMError("empty", "AI servisinde geçici bir sorun oluştu. Lütfen biraz sonra tekrar dene.", "empty")

    monkeypatch.setattr(cr, "get_llm_client", lambda: _FailLLM())

    resp = TestClient(app).post("/api/v1/chatbot/messages", json={"message": DIFF_Q})
    body = resp.json()
    assert "AI servisinde geçici" not in body["answer"]
    assert "Endpointte olmayıp DB'de olan cluster count: 2" in body["answer"]
    assert "DC13-G11-CLS-HYBRID" in body["answer"]
    assert "| Cluster |" in body["answer"]
