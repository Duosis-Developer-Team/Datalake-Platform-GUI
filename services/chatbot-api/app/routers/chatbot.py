"""Main chat endpoint: POST /api/v1/chatbot/messages (alias /chat).

Pipeline (CTO pack 03 "Request Handling Steps"):
  validate -> rate-limit -> forbidden-intent guard -> orchestrate tools ->
  build LLM messages -> call LLM (with fallback) -> normalize -> audit -> respond.

The endpoint always returns HTTP 200 with a user-safe ``answer`` for *operational*
failures (LLM down, rate limited, tool errors). Only malformed requests (empty
message) surface as 422 validation errors.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Request

from app.config import settings
from app.core.api_auth import verify_api_user
from app.core.security import RateLimiter, classify_intent
from app.models.schemas import ChatRequest, ChatResponse, ToolCallSummary
from app.services import agent_loop, context_builder, scope_guard, tool_orchestrator
from app.services.audit_service import AuditRecord, record
from app.services.llm_client import LLMError, get_llm_client

logger = logging.getLogger("chatbot-api.chat")

router = APIRouter()

_rate_limiter = RateLimiter(settings.rate_limit_per_minute, settings.rate_limit_per_hour)

# Deterministic, LLM-free refusal for secret/injection asks (CTO pack 09).
_REFUSAL = (
    "Buna yardımcı olamam; API key, şifre, token veya gizli environment "
    "değerlerini gösteremem ya da paylaşamam. İstersen chatbot servisinin "
    "secret/env yapılandırmasının nasıl güvenli şekilde doğrulanacağını anlatabilirim."
)
# Deterministic, LLM-free response for destructive/write-SQL intent.
_READONLY_REFUSAL = (
    "Ben yalnızca okuma (read-only) modunda çalışıyorum; veri ekleme, silme, "
    "güncelleme veya SQL çalıştırma gibi değişiklik yapan işlemleri "
    "gerçekleştiremem. İstersen ilgili veriyi özetleyebilir veya yorumlayabilirim."
)


def _summaries(results) -> list[ToolCallSummary]:
    out: list[ToolCallSummary] = []
    for r in results:
        if r.status in ("success", "error"):
            out.append(ToolCallSummary(name=r.name, status=r.status, rows=r.rows, source=r.source))
    return out


# Strong denial phrases the model must NOT use when tools actually returned rows.
# Kept narrow so legitimate staleness/caveat wording isn't caught.
_DENY_PHRASES = (
    "erişemiyorum", "erişimim yok", "veri yok", "veri bulunmuyor", "veriye ulaşamıyorum",
    "sağlayamıyorum", "veri setinde yok", "elimde veri yok", "bilgiye sahip değilim",
)


def _has_rows(results) -> bool:
    return any(r.status == "success" and (r.rows or 0) > 0 for r in results)


def _denies_data(answer: str) -> bool:
    # Only treat it as a denial if there's no data presented (no table) — a rich
    # tabular answer that merely notes staleness must not be discarded.
    text = answer or ""
    if "|" in text and "---" in text:
        return False
    low = text.lower()
    return any(p in low for p in _DENY_PHRASES)


def _handle(req: ChatRequest, request: Request, user_id: Optional[str]) -> ChatResponse:
    request_id = uuid.uuid4().hex
    started = time.monotonic()
    created_at = datetime.now(timezone.utc).isoformat()
    model = settings.chatbot_model
    rate_key = user_id or "anon"

    message = req.message[: settings.max_message_chars]
    auth_header = request.headers.get("authorization")

    audit = AuditRecord(
        request_id=request_id,
        user_id=user_id,
        created_at=created_at,
        model=model,
        message_chars=len(message),
    )

    # 1) Rate limit.
    decision = _rate_limiter.check(rate_key)
    if not decision.allowed:
        audit.status = "rate_limited"
        audit.error_type = decision.reason
        record(audit)
        return ChatResponse(
            answer="Çok sık istek gönderildi. Lütfen biraz bekleyip tekrar dene.",
            model=model,
            request_id=request_id,
        )

    # 2) Forbidden-intent hard guard (independent of the LLM).
    flags = classify_intent(message)
    if flags.wants_secret or flags.injection:
        audit.status = "refused"
        audit.error_type = "forbidden_intent"
        record(audit)
        return ChatResponse(answer=_REFUSAL, model=model, request_id=request_id)
    if flags.wants_write:
        audit.status = "refused"
        audit.error_type = "write_intent"
        record(audit)
        return ChatResponse(answer=_READONLY_REFUSAL, model=model, request_id=request_id)

    # 2.5) Domain scope guard (before any tool/LLM). Off-topic + no domain signal
    #      => deterministic refusal. An instruction-override on a domain question
    #      is allowed but the prior conversation is dropped.
    scope = scope_guard.evaluate(message)
    if not scope.in_scope:
        audit.status = "out_of_scope"
        audit.error_type = scope.reason
        audit.latency_ms = int((time.monotonic() - started) * 1000)
        record(audit)
        return ChatResponse(answer=scope_guard.REFUSAL, model=model, request_id=request_id)
    if scope.reset_conversation:
        req.conversation = []

    # 3) Gather evidence — agentic multi-step loop, or legacy single pass.
    outcome = None
    try:
        if settings.chatbot_agentic_mode:
            outcome = agent_loop.run(
                message, req.frontend_context, auth_header, conversation=req.conversation
            )
            tool_results = outcome.results
        else:
            tool_results = tool_orchestrator.run(message, req.frontend_context, auth_header)
    except Exception as exc:  # pragma: no cover - loop/orchestrator already guard
        logger.warning("Evidence gathering failed: %s", exc)
        tool_results = []

    # Page-independent planner needs a required param it couldn't resolve →
    # ask a short clarification instead of guessing or giving up.
    if outcome is not None and outcome.plan.clarification:
        audit.status = "clarification"
        audit.latency_ms = int((time.monotonic() - started) * 1000)
        record(audit)
        return ChatResponse(
            answer=outcome.plan.clarification, model=model, request_id=request_id
        )

    audit.tools = [r.name for r in tool_results if r.status in ("success", "error")]
    if outcome is not None:
        audit.iterations = outcome.iterations
    if tool_results:
        audit.tool_status = (
            "success" if any(r.status == "success" for r in tool_results) else "error"
        )

    # 4) Build messages + 5) call LLM.
    if outcome is not None:
        messages = context_builder.build_agentic_messages(
            user_message=message,
            conversation=req.conversation,
            frontend_context=req.frontend_context,
            outcome=outcome,
            user_id=user_id,
        )
    else:
        messages = context_builder.build_messages(
            user_message=message,
            conversation=req.conversation,
            frontend_context=req.frontend_context,
            tool_results=tool_results,
            user_id=user_id,
        )
    llm = get_llm_client()
    llm_failed = False
    try:
        result = llm.complete(messages)
        answer, model, usage = result.answer, result.model, result.usage
        audit.status = "success"
        if usage:
            audit.prompt_tokens = usage.get("prompt_tokens")
            audit.completion_tokens = usage.get("completion_tokens")
    except LLMError as exc:
        # User-safe message; technical detail stays in logs only.
        logger.warning("LLM error [%s]: %s", exc.error_type, exc.detail)
        answer, usage = exc.user_message, None
        audit.status = "llm_error"
        audit.error_type = exc.error_type
        llm_failed = True

    # Deterministic fallback: if the tools actually returned rows, the user must
    # never see a generic LLM error or a "no data" claim. Build the answer from
    # the analysis summary instead — whether the model errored/returned empty or
    # denied existing data.
    if outcome is not None and _has_rows(tool_results) and (llm_failed or _denies_data(answer)):
        logger.info("deterministic fallback formatter used (llm_failed=%s)", llm_failed)
        answer = context_builder.format_from_analysis(outcome)
        if audit.status == "llm_error":
            audit.status = "llm_error_fallback"
        else:
            audit.error_type = "missing_data_guard"

    audit.latency_ms = int((time.monotonic() - started) * 1000)
    record(audit)

    return ChatResponse(
        answer=answer,
        model=model,
        used_tools=_summaries(tool_results),
        usage=usage,
        request_id=request_id,
    )


@router.post("/messages", response_model=ChatResponse)
def post_message(
    req: ChatRequest,
    request: Request,
    user_id: Optional[str] = Depends(verify_api_user),
) -> ChatResponse:
    return _handle(req, request, user_id)


# Alias kept because both /messages and /chat appear in the task brief.
@router.post("/chat", response_model=ChatResponse, include_in_schema=False)
def post_chat(
    req: ChatRequest,
    request: Request,
    user_id: Optional[str] = Depends(verify_api_user),
) -> ChatResponse:
    return _handle(req, request, user_id)
