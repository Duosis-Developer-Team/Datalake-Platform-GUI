"""Audit logging for chat requests (CTO pack 06).

Metadata only — never the raw prompt, never secrets. MVP writes a single
structured JSON line to the application logger; a later sprint can persist to the
``chatbot_audit_logs`` table without changing this call site.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Optional

from app.config import settings
from app.services.redaction import redact_text

logger = logging.getLogger("chatbot-api.audit")


@dataclass
class AuditRecord:
    request_id: str
    user_id: Optional[str] = None
    username: Optional[str] = None
    created_at: Optional[str] = None  # ISO8601, stamped by caller (no clock in lib)
    model: str = ""
    message_chars: int = 0
    tools: list[str] = field(default_factory=list)
    tool_status: str = "none"
    latency_ms: Optional[int] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    status: str = "success"
    error_type: Optional[str] = None


def record(audit: AuditRecord, message_preview: Optional[str] = None) -> None:
    """Emit one audit line. ``message_preview`` only logged if explicitly enabled."""
    payload = asdict(audit)
    if settings.log_full_prompt and message_preview:
        # Even when opted-in, redact obvious secrets first.
        payload["message_preview"] = redact_text(message_preview)[:200]
    try:
        logger.info("chatbot_audit %s", json.dumps(payload, ensure_ascii=False))
    except Exception:  # pragma: no cover - logging must never break a request
        logger.info("chatbot_audit <unserializable record_id=%s>", audit.request_id)
