from app.models.schemas import ChatMessage, FrontendContext
from app.services import metric_catalog, query_planner

# The exact live-bug message (no DC code in the text).
CLASSIC_Q = (
    "Bana son bir haftada cpu kapasite değişimi (allocated) en değişken olan 3 Klasik "
    "mimari host'unu verir misin? Yani KM mimariye ait hostlar arasından vm'lere atanmış "
    "cpu (ghz cinsinden) miktarındaki değişkenlik oranı en yüksek olan host'ları paylaş."
)


def _tools(plan):
    return [t["tool"] for t in plan.initial_tools]


# --- catalog -------------------------------------------------------------- #


def test_catalog_matches_classic_allocation():
    assert metric_catalog.match(CLASSIC_Q).key == "classic_host_cpu_allocation_variability"


def test_catalog_matches_examples():
    assert metric_catalog.match("Klasik mimari ile hyperconverged CPU kullanımını karşılaştır").key == "classic_vs_hyperconverged_cpu"
    assert metric_catalog.match("Zerto job failure oranı en kötü DC hangisi?").key == "backup_job_failure"
    assert metric_catalog.match("S3 tarafında kapasite riski olan datacenter var mı?").key == "s3_capacity_risk"
    assert metric_catalog.match("VM seviyesinde en çok CPU kullanan makineleri listele").key == "dc_vm_cpu_top"


# --- page independence ---------------------------------------------------- #


def test_dc_from_message_no_context():
    plan = query_planner.plan(CLASSIC_Q + " DC13 için.", None, None)
    assert plan.dc_code == "DC13"
    assert "get_dc_classic_host_cpu_allocation_variability" in _tools(plan)
    assert plan.clarification is None


def test_dc_from_context_when_not_in_message():
    ctx = FrontendContext(selected_datacenter="DC13", pathname="/datacenter/DC13")
    plan = query_planner.plan(CLASSIC_Q, ctx, None)
    assert plan.dc_code == "DC13"
    assert "get_dc_classic_host_cpu_allocation_variability" in _tools(plan)


def test_classic_question_ignores_customer_context():
    # On a customer page, a classic-host question must NOT pick a customer tool.
    ctx = FrontendContext(selected_customer="Boyner", selected_datacenter="DC13",
                          pathname="/customer/Boyner")
    plan = query_planner.plan(CLASSIC_Q, ctx, None)
    assert "get_dc_classic_host_cpu_allocation_variability" in _tools(plan)
    assert not any("customer" in t for t in _tools(plan))


def test_missing_dc_asks_clarification():
    plan = query_planner.plan(CLASSIC_Q, None, None)
    assert plan.missing_required_params == ["dc_code"]
    assert plan.clarification and "data center" in plan.clarification.lower()
    assert plan.initial_tools == []


def test_dc_from_conversation_memory():
    convo = [ChatMessage(role="user", content="DC13 hakkında konuşalım"),
             ChatMessage(role="assistant", content="Tabii.")]
    plan = query_planner.plan(CLASSIC_Q, None, convo)
    assert plan.dc_code == "DC13"
    assert plan.clarification is None


# --- param extraction ----------------------------------------------------- #


def test_days_limit_architecture_extracted():
    plan = query_planner.plan(CLASSIC_Q + " DC13", None, None)
    assert plan.days == 7
    assert plan.limit == 3
    assert plan.architecture == "classic"
    assert plan.analysis_profile == "cpu_allocation"


def test_message_overrides_stale_context():
    # message says DC13; stale context points at DC99 -> message wins
    ctx = FrontendContext(selected_datacenter="DC99")
    plan = query_planner.plan(CLASSIC_Q + " DC13 için", ctx, None)
    assert plan.dc_code == "DC13"


def test_explicit_db_and_api_source_preference():
    assert query_planner.plan("DC13 VM cpu, direkt db kullan", None, None).requested_source == "db"
    assert query_planner.plan("DC13 VM cpu, endpoint üzerinden", None, None).requested_source == "api"


# --- customer metric ------------------------------------------------------ #


GLOBAL_MEMORY_Q = (
    "Bana tüm datacenter'lar arasında memory kullanımı en yüksek 5 KM cluster'ı verir misin?"
)


def test_catalog_matches_global_km_cluster_memory_top():
    assert metric_catalog.match(GLOBAL_MEMORY_Q).key == "global_km_cluster_memory_top"


def test_global_memory_plan_no_dc_required():
    plan = query_planner.plan(GLOBAL_MEMORY_Q, None, None)
    assert plan.metric_key == "global_km_cluster_memory_top"
    assert plan.dc_code is None
    assert plan.limit == 5
    assert "get_global_km_cluster_memory_top" in _tools(plan)
    assert plan.clarification is None


def test_global_memory_ignores_stale_dc_context():
    ctx = FrontendContext(selected_datacenter="DC99", pathname="/datacenters")
    plan = query_planner.plan(GLOBAL_MEMORY_Q, ctx, None)
    assert plan.dc_code is None


def test_customer_extracted_from_possessive():
    plan = query_planner.plan("Boyner'in son bir ayda kaynak değişimi nasıl?", None, None)
    assert plan.entity_type == "customer"
    assert plan.customer_name == "Boyner"
    assert "get_customer_resources" in _tools(plan)


# --- missing-data guard helpers ------------------------------------------- #


def test_missing_data_guard_helpers():
    from app.routers.chatbot import _denies_data, _has_rows
    from app.services.tool_registry import ToolResult

    assert _denies_data("Maalesef bu veri setinde yok.") is True
    assert _denies_data("İşte sonuçlar:") is False
    assert _has_rows([ToolResult("t", "success", "postgres:x", summary={"rows": [1]}, rows=2)]) is True
    assert _has_rows([ToolResult("t", "success", "x", summary={}, rows=0)]) is False
