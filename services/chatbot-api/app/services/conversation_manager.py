"""Conversation history budgeting and rolling summarization for the LLM context.

When the combined developer block + conversation + new user message would exceed
the context budget, older turns are compressed into a short summary while the
most recent turns are kept verbatim.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.config import settings
from app.models.schemas import ChatMessage
from app.services.redaction import redact_text

logger = logging.getLogger("chatbot-api.conversation")

_SUMMARY_SYSTEM = (
    "You compress prior chat turns into a short Turkish summary for an infrastructure "
    "assistant. Preserve datacenter codes (e.g. DC13), customer names, metrics, limits, "
    "and conclusions. Use at most 8 bullet points. Do not invent facts or reveal secrets."
)


def _message_chars(messages: list[ChatMessage]) -> int:
    return sum(len(m.content or "") for m in messages)


def _truncate_fallback(messages: list[ChatMessage], max_chars: int = 2000) -> str:
    """Deterministic fallback when LLM summarization is unavailable."""
    parts = [f"{m.role}: {(m.content or '')[:400]}" for m in messages]
    text = redact_text("\n".join(parts))
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + "\n… (truncated)"


def _summarize_older_turns(older: list[ChatMessage]) -> str:
    if not older:
        return ""
    if not settings.chatbot_conversation_summary_enabled:
        return _truncate_fallback(older)

    try:
        from app.services.llm_client import LLMError, get_llm_client

        transcript = redact_text(
            "\n".join(f"{m.role}: {m.content or ''}" for m in older)[-12000:]
        )
        messages = [
            {"role": "system", "content": _SUMMARY_SYSTEM},
            {"role": "user", "content": transcript},
        ]
        result = get_llm_client().complete(
            messages,
            max_tokens=settings.chatbot_conversation_summary_max_tokens,
        )
        summary = (result.answer or "").strip()
        return summary or _truncate_fallback(older)
    except Exception as exc:  # pragma: no cover - LLM optional in tests
        logger.warning("conversation summary failed: %s", type(exc).__name__)
        return _truncate_fallback(older)


def prepare_conversation(
    conversation: list[ChatMessage],
    user_message: str,
    fixed_overhead_chars: int = 0,
) -> tuple[list[ChatMessage], Optional[str]]:
    """Return (messages_for_llm, optional_earlier_summary).

    ``fixed_overhead_chars`` should include the developer/system blocks already
    assembled (tool results, plan, etc.) so budgeting reflects the real prompt size.
    """
    conv = list(conversation or [])
    budget = max(1000, settings.max_context_chars - fixed_overhead_chars - len(user_message or ""))

    keep_messages = max(2, settings.chatbot_conversation_keep_recent * 2)
    recent = conv[-keep_messages:] if len(conv) > keep_messages else conv
    older = conv[:-keep_messages] if len(conv) > keep_messages else []

    # Fast path: recent history fits comfortably.
    if _message_chars(recent) <= min(settings.max_history_chars, budget) and not older:
        trimmed = _trim_tail(recent, budget)
        return trimmed, None

    total = _message_chars(conv) + len(user_message or "")
    if total <= budget and _message_chars(recent) <= settings.max_history_chars:
        return _trim_tail(conv[-settings.max_history_messages :], budget), None

    summary = _summarize_older_turns(older) if older else None
    trimmed_recent = _trim_tail(recent, budget - len(summary or ""))
    return trimmed_recent, summary


def _trim_tail(messages: list[ChatMessage], budget: int) -> list[ChatMessage]:
    """Keep the most recent messages within a character budget."""
    if not messages:
        return []
    capped = messages[-settings.max_history_messages :]
    out: list[ChatMessage] = []
    total = 0
    for msg in reversed(capped):
        total += len(msg.content or "")
        if total > min(settings.max_history_chars, budget):
            break
        out.append(msg)
    out.reverse()
    return out
