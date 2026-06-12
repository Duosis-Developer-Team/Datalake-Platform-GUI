"""Fire-and-forget client for chatbot-log-api (MongoDB turn persistence)."""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.config import settings
from app.models.schemas import ChatResponse, ClarificationBlock, FrontendContext, ToolCallSummary
from app.services.audit_service import AuditRecord
from app.services.redaction import redact_mapping, redact_text

logger = logging.getLogger("chatbot-api.log_client")


def _headers() -> dict[str, str]:
    key = (settings.chatbot_log_api_key or "").strip()
    return {"X-Internal-Api-Key": key} if key else {}


def build_turn_payload(
    *,
    audit: AuditRecord,
    user_message: str,
    response: ChatResponse,
    frontend_context: Optional[FrontendContext],
    tools: Optional[list[ToolCallSummary]] = None,
    investigation_trace: Optional[list[dict[str, Any]]] = None,
    retention_days: Optional[int] = None,
) -> dict[str, Any]:
    clarification = None
    if response.clarification is not None:
        clarification = response.clarification.model_dump(mode="json")
    fc = frontend_context.model_dump(exclude_none=True) if frontend_context else None
    return {
        "request_id": audit.request_id,
        "user_id": audit.user_id,
        "username": audit.username,
        "status": audit.status,
        "model": response.model or audit.model,
        "user_message": redact_text(user_message),
        "assistant_answer": redact_text(response.answer),
        "response_type": response.response_type,
        "clarification": clarification,
        "frontend_context": redact_mapping(fc) if fc else None,
        "tools": [t.model_dump(mode="json") for t in (tools or [])],
        "investigation_trace": investigation_trace or [],
        "investigation_summary": response.investigation_summary,
        "llm_rounds": response.llm_rounds if response.llm_rounds is not None else audit.llm_rounds,
        "tool_call_count": response.tool_call_count if response.tool_call_count is not None else audit.tool_call_count,
        "latency_ms": audit.latency_ms,
        "usage": response.usage,
        "retention_days": retention_days or settings.chatbot_log_retention_days,
    }


def record_turn(payload: dict[str, Any]) -> None:
    """Sync POST to log-api; failures are logged only."""
    if not settings.chatbot_log_api_enabled:
        return
    url = f"{settings.chatbot_log_api_url.rstrip('/')}/api/v1/logs/turns"
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(url, json=payload, headers=_headers())
            if resp.status_code >= 400:
                logger.warning("log-api rejected turn %s: %s", payload.get("request_id"), resp.status_code)
    except Exception as exc:
        logger.warning("log-api write failed for %s: %s", payload.get("request_id"), exc)


def schedule_turn_log(background_tasks, payload: dict[str, Any]) -> None:
    if background_tasks is not None:
        background_tasks.add_task(record_turn, payload)
    else:
        record_turn(payload)
