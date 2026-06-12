"""Request/response schemas for chatbot-log-api."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ClarificationChoiceLog(BaseModel):
    id: str
    label: str
    value: str


class ClarificationBlockLog(BaseModel):
    prompt: str
    choices: list[ClarificationChoiceLog] = Field(default_factory=list)
    allow_free_text: bool = True


class ToolLogEntry(BaseModel):
    name: str
    status: str
    rows: Optional[int] = None
    source: Optional[str] = None


class ChatTurnLog(BaseModel):
    request_id: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    username: Optional[str] = None
    status: str = "success"
    model: str = ""
    user_message: str = ""
    assistant_answer: str = ""
    response_type: Literal["answer", "clarification"] = "answer"
    clarification: Optional[ClarificationBlockLog] = None
    frontend_context: Optional[dict[str, Any]] = None
    tools: list[ToolLogEntry] = Field(default_factory=list)
    investigation_trace: list[dict[str, Any]] = Field(default_factory=list)
    investigation_summary: Optional[str] = None
    llm_rounds: Optional[int] = None
    tool_call_count: Optional[int] = None
    latency_ms: Optional[int] = None
    usage: Optional[dict[str, Any]] = None
    retention_days: Optional[int] = None


class ChatTurnLogResponse(BaseModel):
    request_id: str
    stored: bool = True


class ChatTurnStored(ChatTurnLog):
    """Document as persisted in MongoDB (includes server timestamps)."""

    created_at: datetime
    expires_at: datetime


class ChatTurnListResponse(BaseModel):
    items: list[ChatTurnStored]
    total: int
    skip: int
    limit: int


class HealthResponse(BaseModel):
    status: str
    service: str


class ReadyResponse(BaseModel):
    status: str
    checks: dict[str, Any]
