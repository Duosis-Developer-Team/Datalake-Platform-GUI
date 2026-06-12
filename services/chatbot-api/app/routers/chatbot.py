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
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from app.config import settings
from app.core.api_auth import verify_api_user
from app.core.security import RateLimiter, classify_intent
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    ClarificationBlock,
    ResponseBlock,
    ToolCallSummary,
    TurnDebugSummary,
)
from app.services import agent_loop, context_builder, log_client, scope_guard, tool_orchestrator
from app.services import answer_reviewer
from app.services.answer_quality import NARRATIVE_RETRY_PROMPT, is_narrative_incomplete
from app.services.audit_service import AuditRecord, record
from app.services.llm_client import LLMError, get_llm_client
from app.services.pipeline_recorder import TurnPipelineRecorder

logger = logging.getLogger("chatbot-api.chat")

router = APIRouter()

_rate_limiter = RateLimiter(settings.rate_limit_per_minute, settings.rate_limit_per_hour)

_REFUSAL = (
    "Buna yardımcı olamam; API key, şifre, token veya gizli environment "
    "değerlerini gösteremem ya da paylaşamam. İstersen chatbot servisinin "
    "secret/env yapılandırmasının nasıl güvenli şekilde doğrulanacağını anlatabilirim."
)
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


def _investigation_trace(outcome) -> list[dict[str, Any]]:
    if outcome and outcome.analysis and outcome.analysis.extra:
        trace = outcome.analysis.extra.get("investigation_trace")
        if isinstance(trace, list):
            return trace
    return []


def _clarification_response(
    block: ClarificationBlock,
    model: str,
    request_id: str,
) -> ChatResponse:
    return ChatResponse(
        answer=block.prompt,
        model=model,
        request_id=request_id,
        response_type="clarification",
        clarification=block,
    )


def _finish(
    background_tasks: BackgroundTasks,
    audit: AuditRecord,
    message: str,
    req: ChatRequest,
    response: ChatResponse,
    outcome=None,
    recorder: Optional[TurnPipelineRecorder] = None,
) -> ChatResponse:
    record(audit)
    pipeline_extra = recorder.to_log_payload() if recorder else None
    payload = log_client.build_turn_payload(
        audit=audit,
        user_message=message,
        response=response,
        frontend_context=req.frontend_context,
        tools=response.used_tools,
        investigation_trace=_investigation_trace(outcome),
        pipeline_extra=pipeline_extra,
    )
    log_client.schedule_turn_log(background_tasks, payload)
    return response


def _handle(
    req: ChatRequest,
    request: Request,
    user_id: Optional[str],
    background_tasks: BackgroundTasks,
) -> ChatResponse:
    request_id = uuid.uuid4().hex
    started = time.monotonic()
    created_at = datetime.now(timezone.utc).isoformat()
    model = settings.chatbot_model
    rate_key = user_id or "anon"
    recorder = TurnPipelineRecorder(request_id=request_id)

    message = req.message[: settings.max_message_chars]
    auth_header = request.headers.get("authorization")

    audit = AuditRecord(
        request_id=request_id,
        user_id=user_id,
        created_at=created_at,
        model=model,
        message_chars=len(message),
    )

    recorder.start_stage("rate_limit")
    decision = _rate_limiter.check(rate_key)
    recorder.finish()
    if not decision.allowed:
        audit.status = "rate_limited"
        audit.error_type = decision.reason
        return _finish(
            background_tasks,
            audit,
            message,
            req,
            ChatResponse(
                answer="Çok sık istek gönderildi. Lütfen biraz bekleyip tekrar dene.",
                model=model,
                request_id=request_id,
            ),
        )

    flags = classify_intent(message)
    if flags.wants_secret or flags.injection:
        audit.status = "refused"
        audit.error_type = "forbidden_intent"
        return _finish(
            background_tasks,
            audit,
            message,
            req,
            ChatResponse(answer=_REFUSAL, model=model, request_id=request_id),
        )
    if flags.wants_write:
        audit.status = "refused"
        audit.error_type = "write_intent"
        return _finish(
            background_tasks,
            audit,
            message,
            req,
            ChatResponse(answer=_READONLY_REFUSAL, model=model, request_id=request_id),
        )

    recorder.start_stage("scope_guard")
    scope = scope_guard.evaluate(message)
    recorder.scope_decision = {
        "in_scope": scope.in_scope,
        "run_tools": scope.run_tools,
        "reason": scope.reason,
    }
    recorder.finish()
    if not scope.in_scope:
        audit.status = "out_of_scope"
        audit.error_type = scope.reason
        audit.latency_ms = int((time.monotonic() - started) * 1000)
        return _finish(
            background_tasks,
            audit,
            message,
            req,
            ChatResponse(answer=scope_guard.REFUSAL, model=model, request_id=request_id),
        )
    if scope.reset_conversation:
        req.conversation = []

    recorder.start_stage("tools")
    outcome = None
    try:
        if settings.chatbot_agentic_mode:
            outcome = agent_loop.run(
                message,
                req.frontend_context,
                auth_header,
                conversation=req.conversation,
                run_tools=scope.run_tools,
            )
            tool_results = outcome.results
        elif scope.run_tools:
            tool_results = tool_orchestrator.run(message, req.frontend_context, auth_header)
        else:
            tool_results = []
    except Exception as exc:  # pragma: no cover
        logger.warning("Evidence gathering failed: %s", exc)
        tool_results = []

    recorder.record_tools(tool_results)
    if outcome is not None:
        recorder.set_plan(outcome.plan)
        if outcome.react_mode_used:
            recorder.record_llm("react_tools", model=model, skipped=False)
    recorder.finish()

    clar_block = None
    if outcome is not None:
        clar_block = outcome.plan.clarification_block
        if clar_block is None and outcome.plan.clarification:
            clar_block = ClarificationBlock(
                prompt=outcome.plan.clarification,
                choices=[],
                allow_free_text=True,
            )
    if clar_block is not None:
        audit.status = "clarification"
        audit.latency_ms = int((time.monotonic() - started) * 1000)
        return _finish(
            background_tasks,
            audit,
            message,
            req,
            _clarification_response(clar_block, model, request_id),
            outcome=outcome,
            recorder=recorder,
        )
    audit.tools = [r.name for r in tool_results if r.status in ("success", "error")]
    if outcome is not None:
        audit.iterations = outcome.iterations
        audit.llm_rounds = outcome.llm_rounds
        audit.tool_call_count = outcome.tool_call_count
        audit.react_mode_used = outcome.react_mode_used
    if tool_results:
        audit.tool_status = (
            "success" if any(r.status == "success" for r in tool_results) else "error"
        )

    investigation_summary = None
    if outcome is not None and outcome.analysis and outcome.analysis.extra:
        investigation_summary = outcome.analysis.extra.get("investigation_summary")

    answer = ""
    usage = None
    llm_failed = False
    post_meta: dict = {
        "answer_source": "llm",
        "blocks_parsed": 0,
        "llm_failed": False,
        "narrative_retry": False,
        "narrative_retry_failed": False,
    }
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
    recorder.start_stage("synthesis_llm")
    llm = get_llm_client()
    try:
        result = llm.complete(messages)
        answer, model, usage = result.answer, result.model, result.usage
        audit.status = "success"
        synthesis_rounds = 1
        if outcome is not None:
            outcome.llm_rounds = (outcome.llm_rounds or 0) + synthesis_rounds
        recorder.record_llm("synthesis", model=model, usage=usage)
        if usage:
            audit.prompt_tokens = usage.get("prompt_tokens")
            audit.completion_tokens = usage.get("completion_tokens")
    except LLMError as exc:
        logger.warning("LLM error [%s]: %s", exc.error_type, exc.detail)
        answer, usage = exc.user_message, None
        audit.status = "llm_error"
        audit.error_type = exc.error_type
        llm_failed = True
        recorder.record_llm("synthesis", model=model, skipped=True, skip_reason=exc.error_type)
    recorder.finish()

    if not llm_failed and is_narrative_incomplete(answer):
        recorder.start_stage("narrative_retry")
        retry_messages = list(messages) + [
            {"role": "assistant", "content": answer},
            {"role": "user", "content": NARRATIVE_RETRY_PROMPT},
        ]
        post_meta["narrative_retry"] = True
        try:
            retry_result = llm.complete(retry_messages)
            retry_answer = (retry_result.answer or "").strip()
            if retry_answer:
                answer = retry_answer
                model = retry_result.model or model
                if retry_result.usage:
                    usage = retry_result.usage
                    audit.prompt_tokens = (audit.prompt_tokens or 0) + (
                        retry_result.usage.get("prompt_tokens") or 0
                    )
                    audit.completion_tokens = (audit.completion_tokens or 0) + (
                        retry_result.usage.get("completion_tokens") or 0
                    )
                if outcome is not None:
                    outcome.llm_rounds = (outcome.llm_rounds or 0) + 1
                recorder.record_llm("synthesis", model=model, usage=retry_result.usage)
            post_meta["narrative_retry_failed"] = is_narrative_incomplete(answer)
        except LLMError as exc:
            logger.warning("Narrative retry LLM error [%s]: %s", exc.error_type, exc.detail)
            post_meta["narrative_retry_failed"] = True
        recorder.finish()

    recorder.start_stage("blocks_parse")
    blocks: list[ResponseBlock] = []
    if outcome is not None or answer:
        answer, blocks, post_meta = answer_reviewer.review(
            answer,
            outcome,
            llm_failed=llm_failed,
            user_message=message,
        )
    recorder.record_post_process(post_meta)
    recorder.finish()

    audit.latency_ms = int((time.monotonic() - started) * 1000)
    debug = None
    if req.include_debug:
        debug = TurnDebugSummary(
            **recorder.to_debug_summary(
                latency_ms=audit.latency_ms,
                tool_call_count=outcome.tool_call_count if outcome else len(tool_results),
                llm_rounds=outcome.llm_rounds if outcome else 1,
            )
        )
    response = ChatResponse(
        answer=answer,
        model=model,
        used_tools=_summaries(tool_results),
        usage=usage,
        request_id=request_id,
        llm_rounds=outcome.llm_rounds if outcome else 1,
        tool_call_count=outcome.tool_call_count if outcome else len(tool_results),
        investigation_summary=investigation_summary,
        response_type="answer",
        blocks=blocks,
        debug=debug,
    )
    return _finish(background_tasks, audit, message, req, response, outcome=outcome, recorder=recorder)


@router.post("/messages", response_model=ChatResponse)
def post_message(
    req: ChatRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user_id: Optional[str] = Depends(verify_api_user),
) -> ChatResponse:
    return _handle(req, request, user_id, background_tasks)


@router.post("/chat", response_model=ChatResponse, include_in_schema=False)
def post_chat(
    req: ChatRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user_id: Optional[str] = Depends(verify_api_user),
) -> ChatResponse:
    return _handle(req, request, user_id, background_tasks)
