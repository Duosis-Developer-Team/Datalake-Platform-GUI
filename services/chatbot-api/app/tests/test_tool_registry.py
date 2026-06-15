from app.models.schemas import FrontendContext
from app.services import tool_orchestrator
from app.services.tool_registry import execute_tool, list_tool_names


def _names(message, ctx=None):
    return [s.tool for s in tool_orchestrator.select_tools(message, ctx)]


def test_dc_intent_selects_datacenter_tool_from_context():
    ctx = FrontendContext(selected_datacenter="DC13")
    assert "get_datacenter_detail" in _names("Bu datacenter'ı özetle", ctx)


def test_dc_code_extracted_from_message_text():
    assert "get_datacenter_detail" in _names("DC13 CPU durumunu özetle", None)


def test_customer_intent_selects_customer_tool():
    ctx = FrontendContext(selected_customer="Boyner")
    assert "get_customer_resources" in _names("Bu müşterinin kaynak kullanımını yorumla", ctx)


def test_backup_intent_selects_backup_tool():
    ctx = FrontendContext(selected_datacenter="DC13")
    assert "get_dc_backup_jobs" in _names("DC13 Zerto job durumunu özetle", ctx)


def test_crm_intent_selects_sellable_tool():
    names = _names("Satılabilir potansiyelde riskli panel hangisi?", None)
    assert "get_sellable_by_panel" in names or "get_sellable_summary" in names


def test_unknown_request_no_dashboard_fallback():
    assert "get_dashboard_overview" not in _names("Merhaba, nasıl yardımcı olursun?", None)


def test_overview_intent_selects_dashboard():
    assert "get_dashboard_overview" in _names("Genel kapasite durumunu özetle", None)


def test_tool_call_cap_enforced():
    ctx = FrontendContext(selected_datacenter="DC13", selected_customer="Boyner")
    picks = tool_orchestrator.select_tools(
        "DC13 cpu storage network backup s3 müşteri sla crm panel", ctx
    )
    assert len(picks) <= 4


def test_execute_tool_skips_when_required_context_missing():
    res = execute_tool("get_datacenter_detail", {"dc_code": None}, None)
    assert res.status == "skipped"
    assert res.error == "missing:dc_code"


def test_query_passthrough_rejects_unapproved_key():
    res = execute_tool("run_registered_query", {"query_key": "anything"}, None)
    assert res.status == "skipped"
    assert res.error == "query_key_not_allowed"


def test_unknown_tool_is_skipped():
    res = execute_tool("definitely_not_a_tool", {}, None)
    assert res.status == "skipped"


def test_registry_is_non_empty():
    assert len(list_tool_names()) >= 10


def test_row_count_for_detail_dict():
    from datalake_tools_core.registry import _row_count

    payload = {"meta": {"id": "DC17"}, "intel": {"cpu_cap": 100, "cpu_used": 50}}
    assert _row_count(payload, tool_name="get_datacenter_detail") == 1
    assert _row_count({"meta": {}}, tool_name="get_datacenter_detail") is None


def test_empty_reason_for_detail_without_metrics():
    from datalake_tools_core.registry import _empty_reason

    reason = _empty_reason(
        "get_datacenter_detail",
        {"meta": {}},
        {"dc_code": "DC17"},
        {},
    )
    assert reason == "no_detail_metrics"


# --- host-level CPU DB tools ------------------------------------------------ #


def test_host_cpu_intent_selects_db_latest_tool():
    assert "get_dc_host_cpu_latest" in _names("DC13 host bazlı CPU kullanımını göster", None)


def test_host_cpu_top_intent_selects_top_tool():
    assert "get_dc_host_cpu_top" in _names("DC13 en yüksek CPU kullanan hostlar hangileri?", None)


def test_host_cpu_summary_intent_selects_summary_tool():
    assert "get_dc_host_cpu_summary" in _names("DC13 host CPU durumunu özetle", None)


def test_cluster_cpu_without_host_keyword_does_not_use_db_tool():
    # "DC13 CPU durumunu özetle" (no 'host') must use API compute, not the DB tool.
    names = _names("DC13 CPU durumunu özetle", None)
    assert "get_dc_host_cpu_latest" not in names
    assert "get_dc_host_cpu_top" not in names


def test_customer_cpu_question_does_not_select_host_db_tool():
    ctx = FrontendContext(selected_customer="Boyner")
    names = _names("Bu müşterinin CPU kullanımını özetle", ctx)
    assert not any(n.startswith("get_dc_host_cpu") for n in names)


def test_db_tool_skipped_when_db_disabled(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "chatbot_db_enabled", False)
    res = execute_tool("get_dc_host_cpu_latest", {"dc_code": "DC13"}, None)
    assert res.status == "skipped"
    assert res.error == "db_disabled"


def test_db_tool_skipped_when_missing_dc():
    res = execute_tool("get_dc_host_cpu_summary", {"dc_code": None}, None)
    assert res.status == "skipped"


# --- VM-level CPU DB tools -------------------------------------------------- #


def _sel(message, ctx=None):
    return tool_orchestrator.select_tools(message, ctx)


def test_vm_cpu_top_intent_selects_vm_tool_with_days_and_limit():
    by = {s.tool: s.args for s in _sel("DC13'teki VM'lerin son bir haftada en çok CPU tüketen 10 tanesini listele")}
    assert "get_dc_vm_cpu_top" in by
    assert by["get_dc_vm_cpu_top"]["days"] == 7
    assert by["get_dc_vm_cpu_top"]["limit"] == 10


def test_vm_keyword_routes_to_vm_tool_not_host():
    names = _names("DC13 VM bazlı CPU kullanımını göster", None)
    assert any(n.startswith("get_dc_vm_cpu") for n in names)
    assert not any(n.startswith("get_dc_host_cpu") for n in names)


def test_host_keyword_still_routes_to_host_tool():
    names = _names("DC13 host bazlı CPU kullanımını özetle", None)
    assert "get_dc_host_cpu_summary" in names
    assert not any(n.startswith("get_dc_vm_cpu") for n in names)


def test_explicit_db_cpu_routes_to_db_not_api():
    names = _names("DC13 CPU durumunu direkt DB'den çek", None)
    assert any(n.startswith("get_dc_host_cpu") or n.startswith("get_dc_vm_cpu") for n in names)
    assert "get_dc_compute_classic" not in names


def test_vm_days_extraction_son_n_gun():
    by = {s.tool: s.args for s in _sel("DC13 son 14 günde en çok CPU kullanan VM'ler")}
    assert by.get("get_dc_vm_cpu_top", {}).get("days") == 14


def test_vm_db_tool_skipped_when_disabled(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "chatbot_db_enabled", False)
    res = execute_tool("get_dc_vm_cpu_top", {"dc_code": "DC13"}, None)
    assert res.status == "skipped"
    assert res.error == "db_disabled"
