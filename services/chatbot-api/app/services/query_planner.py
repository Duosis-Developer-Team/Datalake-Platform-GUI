"""Catalog-based, page-independent query planner.

Page context is *supporting*, never required. Parameters are resolved with a
strict precedence:

    1. the user message (explicit: "DC13", "Boyner", "Klasik", "son 7 gün", "top 3")
    2. frontend context (selected_datacenter / customer / time_range)
    3. conversation memory (dc/customer carried from earlier turns)
    4. catalog defaults (days/limit)
    5. clarification (only when a genuinely required param is still missing)

The metric is resolved against the domain catalog (alias match), which maps it
to allowlisted tools. When nothing in the catalog matches, we fall back to the
legacy keyword planner so existing behaviour is preserved. No LLM picks tools;
the registry allowlist is never bypassed.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.catalog import data_source_catalog, domain_catalog, metric_semantics
from app.models.schemas import ChatMessage, FrontendContext
from app.services import clarification_policy, planner
from app.services import tool_orchestrator as orch
from app.services.planner import IntentPlan

# "Boyner'in", "Akbank'ın", "X'nin" -> capture the proper noun before the suffix.
_POSSESSIVE_RE = re.compile(r"\b([A-ZÇĞİÖŞÜ][\wÇĞİÖŞÜçğıöşü]{2,})['’](?:in|ın|nin|nın|un|ün|nun|nün|nin)\b")
_API_PREF_RE = ("endpoint", "api ", "api'", "webui'da", "web ui", "panelde", "ekranda")


def _arch(text: str) -> Optional[str]:
    if any(k in text for k in ("klasik", "classic", "km mimari", " km ", "km host", "km cluster")):
        return "classic"
    if any(k in text for k in ("hyperconverged", "hiperkonverjant", "hyper-converged", "hiper konverjant")):
        return "hyperconverged"
    return None


def _source_pref(text: str) -> str:
    if orch._has(text, "explicit_db"):
        return "db"
    if any(k in text for k in _API_PREF_RE):
        return "api"
    return "auto"


def _dc_from_conversation(conversation: Optional[list[ChatMessage]]) -> Optional[str]:
    for msg in reversed(conversation or []):
        m = orch._DC_RE.search(msg.content or "")
        if m:
            return m.group(1).upper()
    return None


def _customer_from_message(text_raw: str) -> Optional[str]:
    m = _POSSESSIVE_RE.search(text_raw or "")
    return m.group(1) if m else None


def _resolve_dc(message: str, ctx: Optional[FrontendContext],
                conversation: Optional[list[ChatMessage]]) -> Optional[str]:
    # message first, then ctx, then conversation memory.
    m = orch._DC_RE.search(message or "")
    if m:
        return m.group(1).upper()
    if ctx and ctx.selected_datacenter:
        return ctx.selected_datacenter.upper()
    return _dc_from_conversation(conversation)


def _resolve_customer(message: str, ctx: Optional[FrontendContext],
                      conversation: Optional[list[ChatMessage]]) -> Optional[str]:
    cust = _customer_from_message(message)
    if cust:
        return cust
    if ctx and ctx.selected_customer:
        return ctx.selected_customer
    for msg in reversed(conversation or []):
        if msg.role == "user":
            c = _customer_from_message(msg.content or "")
            if c:
                return c
    return None


def _clarify_block(param: str):
    return clarification_policy.build_param_clarification(param)


def _order_by_source(tools: tuple[str, ...], pref: str) -> list[str]:
    """Order tools by source preference; db/api decided via data_source_catalog."""
    db = data_source_catalog.db_tool_keys()
    if pref == "db":
        return sorted(tools, key=lambda t: 0 if t in db else 1)
    if pref == "api":
        return sorted(tools, key=lambda t: 0 if t not in db else 1)
    return list(tools)


def _plan_datacenter_ranking(
    message: str,
    ctx: Optional[FrontendContext],
    conversation: Optional[list[ChatMessage]],
    ranking_metric: str,
) -> IntentPlan:
    """Build a plan for global datacenter ranking (catalog metric or follow-up)."""
    md = domain_catalog.get_by_key("global_datacenter_utilization")
    text = (message or "").lower()
    base = {
        "dc_code": None,
        "customer_name": None,
        "days": orch._extract_days(text) or (md.default_params.get("days") if md else None),
        "limit": orch._extract_limit(text) or (md.default_params.get("limit") if md else None),
        "time_range": (ctx.time_range if ctx else None),
    }
    tools = list(md.primary_tools) if md else ["get_datacenters_summary"]
    return IntentPlan(
        entity_type="datacenter",
        metric="utilization",
        metric_key="global_datacenter_utilization",
        calculation="comparison",
        analysis_profile="datacenter_ranking",
        ranking_metric=ranking_metric,
        dc_code=None,
        days=base["days"],
        limit=base["limit"],
        requested_output="comparison",
        needs_analysis=True,
        answer_guidance=list(md.answer_guidance) if md else [],
        initial_tools=[{"tool": t, "args": dict(base)} for t in tools],
        fallback_tools=[],
    )


def plan(message: str, ctx: Optional[FrontendContext],
         conversation: Optional[list[ChatMessage]] = None) -> IntentPlan:
    text = (message or "").lower()
    md = domain_catalog.match(message)

    # Ranking metric follow-up (user answered clarification with "1", "cpu", etc.).
    if md is None and clarification_policy.is_ranking_followup(conversation):
        metric = clarification_policy.resolve_ranking_metric(message, conversation)
        if metric:
            return _plan_datacenter_ranking(message, ctx, conversation, metric)

    # No catalog hit -> legacy keyword planner (keeps prior behaviour).
    if md is None:
        return planner.make_plan(message, ctx)

    dc_code = _resolve_dc(message, ctx, conversation)
    # Global-scope questions must not inherit a stale selected_datacenter.
    global_metric = md.key in (
        "global_km_cluster_memory_top",
        "global_datacenter_utilization",
    ) or md.analysis_profile == "datacenter_ranking"
    if global_metric or (not md.required_params and metric_semantics.is_global_scope(text)):
        explicit_dc = bool(orch._DC_RE.search(message or ""))
        if metric_semantics.is_global_scope(text) or (global_metric and not explicit_dc):
            dc_code = None
    # Customer is only resolved for customer metrics — a datacenter/host/cluster
    # question never picks up a (possibly stale) selected_customer.
    customer = _resolve_customer(message, ctx, conversation) if md.entity == "customer" else None
    days = orch._extract_days(text) or md.default_params.get("days")
    limit = orch._extract_limit(text) or md.default_params.get("limit")
    architecture = _arch(text) or md.architecture
    source_pref = _source_pref(text)

    resolved: dict[str, Any] = {"dc_code": dc_code, "customer_name": customer}
    missing = [p for p in md.required_params if not resolved.get(p)]

    p = IntentPlan(
        entity_type=md.entity,
        metric=md.metric,
        metric_key=md.key,
        architecture=architecture,
        calculation=md.calculation,
        analysis_profile=md.analysis_profile,
        dc_code=dc_code,
        customer_name=customer,
        days=days,
        limit=limit,
        requested_source=source_pref,
        requested_output=md.output_type,
        sort_by="max" if ("peak" in text or "tepe" in text) else "avg",
        needs_analysis=True,
        answer_guidance=list(md.answer_guidance),
    )

    if missing:
        p.missing_required_params = missing
        block = _clarify_block(missing[0])
        p.clarification_block = block
        p.clarification = block.prompt
        return p

    p.ranking_metric = clarification_policy.resolve_ranking_metric(message, conversation)
    ranking_clar = clarification_policy.check_ranking_clarification(
        message, md.analysis_profile, conversation
    )
    if ranking_clar:
        p.clarification_block = ranking_clar
        p.clarification = ranking_clar.prompt
        return p

    base = {
        "dc_code": dc_code,
        "customer_name": customer,
        "days": days,
        "limit": limit,
        "time_range": (ctx.time_range if ctx else None),
    }
    # Build the plan from the catalog's primary tools, ordered by source
    # preference, with forbidden tools (e.g. customer tools on a DC metric)
    # explicitly excluded — never bypassing the registry allowlist.
    forbidden = set(md.forbidden_tools)
    tools = [t for t in _order_by_source(md.primary_tools, source_pref) if t not in forbidden]
    fallbacks = [t for t in _order_by_source(md.fallback_tools, source_pref) if t not in forbidden]
    p.initial_tools = [{"tool": t, "args": dict(base)} for t in tools]
    p.fallback_tools = [{"tool": t, "args": dict(base)} for t in fallbacks]
    return p
