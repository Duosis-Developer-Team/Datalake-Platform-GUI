"""LLM ReAct loop — function-calling investigation until answer or budget cap."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from app.config import settings
from app.services import llm_tool_schemas, tool_registry
from app.services.investigation_trace import InvestigationTrace
from app.services.llm_client import LLMError, get_llm_client
from app.services.planner import IntentPlan
from app.services.tool_registry import ToolResult

logger = logging.getLogger("chatbot-api.react")

REACT_SYSTEM = """You are Bulutistan Datalake Platform analyst for datacenter and company executives.
Investigate the user's question using the provided tools before answering.
Rules:
- Call tools until you can answer OR you have confirmed data is unavailable in accessible sources.
- Never invent metrics; use only tool outputs.
- When finished (no more tools needed), respond in Turkish with this structure:
  1. **Analiz** — what you checked, findings, business/risk interpretation
  2. **Sonuç** — direct answer (1-3 sentences)
  3. Table/list if applicable
  4. Risk level + recommended actions
  5. Sources + data quality notes
- Do NOT claim data is missing without listing which tools were tried.
- Read-only; never suggest destructive actions.
"""


@dataclass
class ReactOutcome:
    results: list[ToolResult] = field(default_factory=list)
    llm_rounds: int = 0
    tool_call_count: int = 0
    investigation_trace: InvestigationTrace = field(default_factory=InvestigationTrace)
    draft_answer: Optional[str] = None
    model: Optional[str] = None
    usage: Optional[dict[str, Any]] = None
    react_used: bool = False


def _dedupe_key(tool: str, args: dict[str, Any]) -> tuple:
    return (
        tool,
        args.get("dc_code"),
        args.get("customer_name"),
        args.get("days"),
        args.get("limit"),
        args.get("vendor"),
        args.get("query_key"),
    )


def _parse_tool_args(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _merge_plan_args(plan: IntentPlan, args: dict[str, Any]) -> dict[str, Any]:
    """Fill missing args from the intent plan defaults."""
    merged = dict(args)
    if plan.dc_code and not merged.get("dc_code"):
        merged["dc_code"] = plan.dc_code
    if plan.customer_name and not merged.get("customer_name"):
        merged["customer_name"] = plan.customer_name
    if plan.days is not None and merged.get("days") is None:
        merged["days"] = plan.days
    if plan.limit is not None and merged.get("limit") is None:
        merged["limit"] = plan.limit
    return merged


def _execute_tool(
    tool: str,
    args: dict[str, Any],
    auth_header: Optional[str],
    executed: set[tuple],
    trace: InvestigationTrace,
    results: list[ToolResult],
) -> bool:
    """Run one tool if not deduped. Returns True if executed."""
    key = _dedupe_key(tool, args)
    if key in executed:
        return False
    executed.add(key)
    try:
        res = tool_registry.execute_tool(tool, args, auth_header)
    except Exception as exc:  # pragma: no cover
        logger.warning("react tool %s failed: %s", tool, exc)
        res = ToolResult(tool, "error", tool, error="tool_exception")
    results.append(res)
    trace.record(res)
    return True


def run(
    message: str,
    plan: IntentPlan,
    seed_results: list[ToolResult],
    auth_header: Optional[str],
) -> ReactOutcome:
    """Run the LLM ReAct loop on top of seed tool results."""
    outcome = ReactOutcome(results=list(seed_results))
    for r in seed_results:
        outcome.investigation_trace.record(r)

    if not settings.chatbot_llm_react_mode:
        return outcome

    llm = get_llm_client()
    if not llm.is_configured:
        return outcome

    if not llm.probe_tools_support():
        logger.info("LLM tool-calling not supported; skipping ReAct loop")
        return outcome

    max_llm = max(1, settings.chatbot_max_llm_rounds)
    max_tools = max(1, settings.chatbot_max_tool_calls_per_turn)
    executed: set[tuple] = set()

    plan_ctx = plan.as_context()
    developer = (
        f"Intent plan:\n{json.dumps(plan_ctx, ensure_ascii=False)}\n\n"
        f"{llm_tool_schemas.catalog_guidance_summary()}\n\n"
        "Seed tool results are already in the conversation context."
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": REACT_SYSTEM},
        {"role": "system", "content": developer},
        {"role": "user", "content": message},
    ]

    # Inject compact seed summaries so the model knows what was already tried.
    if seed_results:
        seed_block = "\n".join(
            f"- {r.name}: status={r.status}, rows={r.rows}, error={r.error}"
            for r in seed_results[:30]
        )
        messages.append(
            {
                "role": "system",
                "content": f"Already executed tools:\n{seed_block}",
            }
        )

    tools = llm_tool_schemas.build_openai_tools()
    outcome.react_used = True

    for _ in range(max_llm):
        if outcome.tool_call_count >= max_tools:
            break
        try:
            result = llm.complete_with_tools(messages, tools=tools)
        except LLMError as exc:
            logger.warning("ReAct LLM round failed: %s", exc.error_type)
            break

        outcome.llm_rounds += 1
        outcome.model = result.model
        if result.usage:
            outcome.usage = result.usage

        if result.tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": result.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": tc.arguments,
                            },
                        }
                        for tc in result.tool_calls
                    ],
                }
            )
            for tc in result.tool_calls:
                if outcome.tool_call_count >= max_tools:
                    break
                args = _merge_plan_args(plan, _parse_tool_args(tc.arguments))
                if _execute_tool(tc.name, args, auth_header, executed, outcome.investigation_trace, outcome.results):
                    outcome.tool_call_count += 1
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": llm_tool_schemas.tool_result_for_llm(
                            tc.name,
                            outcome.results[-1] if outcome.results else {},
                        ),
                    }
                )
            continue

        # No tool calls — model produced a final answer.
        if result.content and result.content.strip():
            outcome.draft_answer = result.content.strip()
        break

    return outcome
