"""Tests for TurnPipelineRecorder."""

from __future__ import annotations

from app.services.pipeline_recorder import TurnPipelineRecorder
from app.services.tool_registry import ToolResult


def test_recorder_debug_summary_and_log_payload():
    rec = TurnPipelineRecorder(request_id="abc123")
    rec.start_stage("scope_guard")
    rec.finish()
    rec.scope_decision = {"in_scope": True, "run_tools": False}
    rec.record_tools(
        [
            ToolResult(
                "get_dashboard_overview",
                "success",
                "datacenter-api:/api/v1/dashboard/overview",
                summary={"overview": {"dc_count": 1}},
                rows=1,
            )
        ]
    )
    rec.record_llm("synthesis", model="test-model", usage={"prompt_tokens": 10, "completion_tokens": 5})
    rec.record_post_process({"answer_source": "llm", "blocks_parsed": 1, "llm_failed": False})

    debug = rec.to_debug_summary(latency_ms=100, tool_call_count=1, llm_rounds=2)
    assert debug["request_id"] == "abc123"
    assert debug["post_process"]["answer_source"] == "llm"
    assert len(debug["tools"]) == 1

    log = rec.to_log_payload()
    assert log["scope_decision"]["run_tools"] is False
    assert len(log["tool_executions"]) == 1
    assert log["tool_executions"][0]["summary"]["overview"]["dc_count"] == 1
