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
