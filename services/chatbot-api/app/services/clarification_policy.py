"""Clarification policy — ask the user when ranking scope or metric is ambiguous.

Rule-based (no LLM). Used by query_planner before tools run so we never emit a
premature global ranking answer on partial data or an undefined metric.
"""

from __future__ import annotations

import re
from typing import Literal, Optional

from app.catalog import domain_catalog, metric_semantics
from app.config import settings
from app.models.schemas import ChatMessage, ClarificationBlock, ClarificationChoice

RankingMetric = Literal["cpu", "memory", "vm_count", "composite"]

RANKING_METRIC_CLARIFICATION = (
    "Yoğunluğu hangi metriğe göre değerlendireyim?"
)

_OPTION_MAP = {
    "1": "cpu",
    "cpu": "cpu",
    "cpu kullanım": "cpu",
    "cpu kullanim": "cpu",
    "2": "memory",
    "memory": "memory",
    "bellek": "memory",
    "ram": "memory",
    "bellek kullanım": "memory",
    "bellek kullanim": "memory",
    "3": "vm_count",
    "vm": "vm_count",
    "vm sayısı": "vm_count",
    "vm sayisi": "vm_count",
    "sanal makine": "vm_count",
    "4": "composite",
    "hepsi": "composite",
    "hepsini": "composite",
    "bileşik": "composite",
    "bilesik": "composite",
    "birlikte": "composite",
    "composite": "composite",
}


def build_ranking_clarification() -> ClarificationBlock:
    return ClarificationBlock(
        prompt=RANKING_METRIC_CLARIFICATION,
        choices=[
            ClarificationChoice(id="cpu", label="CPU kullanım %", value="cpu"),
            ClarificationChoice(id="memory", label="Bellek kullanım %", value="memory"),
            ClarificationChoice(id="vm_count", label="VM sayısı", value="vm_count"),
            ClarificationChoice(id="composite", label="Hepsini birlikte (bileşik skor)", value="composite"),
        ],
        allow_free_text=True,
    )


def build_param_clarification(param: str) -> ClarificationBlock:
    prompts = {
        "dc_code": "Hangi data center için bakayım?",
        "customer_name": "Hangi müşteri için bakayım?",
    }
    return ClarificationBlock(
        prompt=prompts.get(param, f"Eksik bilgi: {param}"),
        choices=[],
        allow_free_text=True,
    )


def _norm_reply(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().casefold())


def detect_ranking_metric(message: str) -> Optional[RankingMetric]:
    """Infer ranking metric from explicit wording in the user message."""
    text = _norm_reply(message)
    if not text:
        return None

    if any(k in text for k in ("bileşik", "bilesik", "hepsini birlikte", "hepsi birlikte")):
        return "composite"
    if any(k in text for k in ("vm sayısı", "vm sayisi", "vm sayı", "sanal makine say")):
        return "vm_count"
    if metric_semantics.has_any(
        text,
        ("bellek kullanım", "bellek kullanim", "ram kullanım", "ram kullanim", "memory usage"),
    ):
        return "memory"
    if metric_semantics.has_any(
        text,
        ("cpu kullanım", "cpu kullanim", "cpu usage", "cpu'ya göre", "cpu ya göre"),
    ):
        return "cpu"
    if "cpu" in text and not any(k in text for k in ("bellek", "memory", " ram", "vm say")):
        return "cpu"
    if metric_semantics.has_any(text, ("bellek", "memory", " ram ")) and "cpu" not in text:
        return "memory"
    return None


def _metric_from_reply(reply: str) -> Optional[RankingMetric]:
    key = _norm_reply(reply)
    if key in _OPTION_MAP:
        return _OPTION_MAP[key]  # type: ignore[return-value]
    for alias, metric in sorted(_OPTION_MAP.items(), key=lambda x: -len(x[0])):
        if alias in key:
            return metric  # type: ignore[return-value]
    return detect_ranking_metric(reply)


def resolve_ranking_metric(
    message: str,
    conversation: Optional[list[ChatMessage]] = None,
) -> Optional[RankingMetric]:
    """Current message first, then recent user replies to clarification prompts."""
    metric = detect_ranking_metric(message)
    if metric:
        return metric
    for msg in reversed(conversation or []):
        if msg.role != "user":
            continue
        metric = _metric_from_reply(msg.content or "")
        if metric:
            return metric
    return None


def _assistant_had_ranking_clarification(content: str) -> bool:
    return RANKING_METRIC_CLARIFICATION in (content or "")


def is_ranking_followup(conversation: Optional[list[ChatMessage]]) -> bool:
    """True when the user is answering a prior datacenter-ranking clarification."""
    for msg in conversation or []:
        if msg.role == "assistant" and _assistant_had_ranking_clarification(msg.content or ""):
            return True
        if msg.role == "user":
            md = domain_catalog.match(msg.content or "")
            if md and md.analysis_profile == "datacenter_ranking":
                return True
    return False


def check_ranking_clarification(
    message: str,
    analysis_profile: str,
    conversation: Optional[list[ChatMessage]] = None,
) -> Optional[ClarificationBlock]:
    """Return clarification block when ranking metric is ambiguous; else None."""
    if analysis_profile != "datacenter_ranking":
        return None
    if not settings.chatbot_clarification_on_ambiguous_ranking:
        return None
    if resolve_ranking_metric(message, conversation):
        return None
    return build_ranking_clarification()
