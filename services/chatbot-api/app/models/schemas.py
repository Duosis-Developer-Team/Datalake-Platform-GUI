"""Request/response contracts for chatbot-api.

Matches CTO pack 03_CHATBOT_API_SERVICE_SPEC and 08_API_CONTRACTS. Kept
deliberately small and explicit so the frontend Dash store shape and the service
stay in lockstep.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# --------------------------------------------------------------------------- #
# Request
# --------------------------------------------------------------------------- #


class FrontendContext(BaseModel):
    """WebUI page context the Dash callback attaches to each message."""

    pathname: Optional[str] = None
    search: Optional[str] = None
    time_range: Optional[dict[str, Any]] = None
    selected_customer: Optional[str] = None
    selected_datacenter: Optional[str] = None
    page_title: Optional[str] = None
    visible_sections: Optional[list[str]] = None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., description="Current user message")
    conversation: list[ChatMessage] = Field(default_factory=list)
    frontend_context: Optional[FrontendContext] = None

    @field_validator("message")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("message is required")
        return v


# --------------------------------------------------------------------------- #
# Response
# --------------------------------------------------------------------------- #


class ToolCallSummary(BaseModel):
    name: str
    status: Literal["success", "error", "skipped"]
    rows: Optional[int] = None
    source: Optional[str] = None


class ClarificationChoice(BaseModel):
    id: str
    label: str
    value: str


class ClarificationBlock(BaseModel):
    prompt: str
    choices: list[ClarificationChoice] = Field(default_factory=list)
    allow_free_text: bool = True


class ResponseBlock(BaseModel):
    type: Literal["markdown", "table", "kpi_strip"] = "markdown"
    content: Optional[str] = None
    columns: Optional[list[str]] = None
    rows: Optional[list[list[str]]] = None


class ChatResponse(BaseModel):
    answer: str
    model: str
    used_tools: list[ToolCallSummary] = Field(default_factory=list)
    usage: Optional[dict[str, Any]] = None
    request_id: str
    llm_rounds: Optional[int] = None
    tool_call_count: Optional[int] = None
    investigation_summary: Optional[str] = None
    response_type: Literal["answer", "clarification"] = "answer"
    clarification: Optional[ClarificationBlock] = None
    blocks: list[ResponseBlock] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Health / readiness
# --------------------------------------------------------------------------- #


class HealthResponse(BaseModel):
    status: str
    service: str


class ReadyResponse(BaseModel):
    status: str
    checks: dict[str, Any]
