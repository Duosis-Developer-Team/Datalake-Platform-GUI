"""Turn pipeline recorder — structured debug metadata for MongoDB and API debug field."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from app.config import settings
from app.services.redaction import redact_mapping, redact_text
from app.services.tool_registry import ToolResult


@dataclass
class PipelineStage:
    name: str
    duration_ms: int = 0
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolExecutionLog:
    name: str
    status: str
    rows: Optional[int] = None
    source: Optional[str] = None
    error: Optional[str] = None
    duration_ms: Optional[int] = None
    summary: Optional[dict[str, Any]] = None
    summary_truncated: bool = False


@dataclass
class LlmCallLog:
    phase: Literal["react_tools", "synthesis"]
    model: str = ""
    skipped: bool = False
    skip_reason: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None


@dataclass
class PostProcessLog:
    llm_failed: bool = False
    blocks_parsed: int = 0
    answer_source: Literal["llm", "llm_error_message"] = "llm"


@dataclass
class TurnPipelineRecorder:
    request_id: str
    stages: list[PipelineStage] = field(default_factory=list)
    tool_executions: list[ToolExecutionLog] = field(default_factory=list)
    llm_calls: list[LlmCallLog] = field(default_factory=list)
    post_process: Optional[PostProcessLog] = None
    scope_decision: dict[str, Any] = field(default_factory=dict)
    plan_snapshot: dict[str, Any] = field(default_factory=dict)
    _stage_started: float = 0.0

    def start_stage(self, name: str, **detail: Any) -> None:
        self._flush_stage()
        self._stage_started = time.monotonic()
        self.stages.append(PipelineStage(name=name, detail=dict(detail)))

    def _flush_stage(self) -> None:
        if not self.stages or self._stage_started <= 0:
            return
        self.stages[-1].duration_ms = int((time.monotonic() - self._stage_started) * 1000)

    def finish(self) -> None:
        self._flush_stage()

    def record_tools(self, results: list[ToolResult]) -> None:
        max_chars = getattr(settings, "chatbot_log_tool_summary_max_chars", 16384)
        seen: set[str] = set()
        for r in results:
            key = f"{r.name}:{r.source}"
            if key in seen:
                continue
            seen.add(key)
            summary = r.summary if isinstance(r.summary, dict) else None
            truncated = False
            if summary is not None:
                raw = json.dumps(summary, ensure_ascii=False, default=str)
                if len(raw) > max_chars:
                    truncated = True
                    try:
                        summary = json.loads(raw[: max_chars - 1] + "…")
                    except json.JSONDecodeError:
                        summary = {"_truncated_preview": raw[:max_chars]}
                summary = redact_mapping(summary)
            self.tool_executions.append(
                ToolExecutionLog(
                    name=r.name,
                    status=r.status,
                    rows=r.rows,
                    source=r.source,
                    error=r.error,
                    summary=summary,
                    summary_truncated=truncated,
                )
            )

    def record_llm(
        self,
        phase: Literal["react_tools", "synthesis"],
        *,
        model: str = "",
        skipped: bool = False,
        skip_reason: Optional[str] = None,
        usage: Optional[dict[str, Any]] = None,
    ) -> None:
        self.llm_calls.append(
            LlmCallLog(
                phase=phase,
                model=model,
                skipped=skipped,
                skip_reason=skip_reason,
                prompt_tokens=(usage or {}).get("prompt_tokens"),
                completion_tokens=(usage or {}).get("completion_tokens"),
            )
        )

    def record_post_process(self, meta: dict[str, Any]) -> None:
        src = meta.get("answer_source") or "llm"
        if src not in ("llm", "llm_error_message"):
            src = "llm"
        self.post_process = PostProcessLog(
            llm_failed=bool(meta.get("llm_failed")),
            blocks_parsed=int(meta.get("blocks_parsed") or 0),
            answer_source=src,
        )

    def set_plan(self, plan) -> None:
        if plan is None:
            return
        self.plan_snapshot = {
            "entity_type": getattr(plan, "entity_type", None),
            "metric_key": getattr(plan, "metric_key", None),
            "analysis_profile": getattr(plan, "analysis_profile", None),
            "initial_tools": [
                t.get("tool") if isinstance(t, dict) else getattr(t, "tool", None)
                for t in (getattr(plan, "initial_tools", None) or [])
            ],
        }

    def to_debug_summary(
        self,
        *,
        latency_ms: int,
        tool_call_count: int,
        llm_rounds: int,
    ) -> dict[str, Any]:
        preview_len = 512
        tools = []
        for t in self.tool_executions:
            preview = ""
            if t.summary is not None:
                preview = redact_text(
                    json.dumps(t.summary, ensure_ascii=False, default=str)[:preview_len]
                )
            tools.append(
                {
                    "name": t.name,
                    "status": t.status,
                    "rows": t.rows,
                    "source": t.source,
                    "summary_preview": preview,
                }
            )
        return {
            "request_id": self.request_id,
            "latency_ms": latency_ms,
            "tool_call_count": tool_call_count,
            "llm_rounds": llm_rounds,
            "llm_calls": [
                {
                    "phase": c.phase,
                    "model": c.model,
                    "skipped": c.skipped,
                    "skip_reason": c.skip_reason,
                    "prompt_tokens": c.prompt_tokens,
                    "completion_tokens": c.completion_tokens,
                }
                for c in self.llm_calls
            ],
            "pipeline_stages": [
                {"name": s.name, "duration_ms": s.duration_ms, "detail": s.detail}
                for s in self.stages
            ],
            "tools": tools,
            "post_process": (
                {
                    "llm_failed": self.post_process.llm_failed,
                    "blocks_parsed": self.post_process.blocks_parsed,
                    "answer_source": self.post_process.answer_source,
                }
                if self.post_process
                else None
            ),
            "scope_in_scope": self.scope_decision.get("in_scope", True),
        }

    def to_log_payload(self) -> dict[str, Any]:
        return {
            "pipeline_stages": [
                {"name": s.name, "duration_ms": s.duration_ms, "detail": s.detail}
                for s in self.stages
            ],
            "tool_executions": [
                {
                    "name": t.name,
                    "status": t.status,
                    "rows": t.rows,
                    "source": t.source,
                    "error": t.error,
                    "duration_ms": t.duration_ms,
                    "summary": t.summary,
                    "summary_truncated": t.summary_truncated,
                }
                for t in self.tool_executions
            ],
            "llm_calls": [
                {
                    "phase": c.phase,
                    "model": c.model,
                    "skipped": c.skipped,
                    "skip_reason": c.skip_reason,
                    "prompt_tokens": c.prompt_tokens,
                    "completion_tokens": c.completion_tokens,
                }
                for c in self.llm_calls
            ],
            "post_process": (
                {
                    "llm_failed": self.post_process.llm_failed,
                    "blocks_parsed": self.post_process.blocks_parsed,
                    "answer_source": self.post_process.answer_source,
                }
                if self.post_process
                else None
            ),
            "plan_snapshot": self.plan_snapshot,
            "scope_decision": self.scope_decision,
        }
