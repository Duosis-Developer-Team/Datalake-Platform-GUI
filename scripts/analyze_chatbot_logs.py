"""Analyze chatbot audit logs for CRM/customer quality signals."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_CRM_RE = re.compile(
    r"crm|satılabilir|satilabilir|sellable|potansiyel|satış|satis|fırsat|firsat",
    re.I,
)
_CUSTOMER_RE = re.compile(
    r"müşteri|musteri|customer|boyner|akbank|aselsan|tenant",
    re.I,
)


def _fetch_turns(base_url: str, api_key: str, *, limit: int = 100, days: int = 30) -> dict[str, Any]:
    params = urlencode({"limit": limit, "days": days})
    url = f"{base_url.rstrip('/')}/api/v1/logs/turns?{params}"
    req = Request(url, headers={"X-API-Key": api_key})
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _tool_entries(turn: dict[str, Any]) -> list[dict[str, Any]]:
    return turn.get("tool_executions") or turn.get("tools") or []


def _is_crm_customer_turn(turn: dict[str, Any]) -> bool:
    text = (turn.get("user_message") or "") + " " + (turn.get("assistant_answer") or "")
    return bool(_CRM_RE.search(text) or _CUSTOMER_RE.search(text))


def _sellable_dc_scope_ok(turn: dict[str, Any]) -> bool | None:
    plan = turn.get("plan_snapshot") or {}
    expected_dc = plan.get("dc_code")
    if not expected_dc:
        return None
    for te in _tool_entries(turn):
        if te.get("name") != "get_sellable_summary":
            continue
        summary = te.get("summary") or {}
        if isinstance(summary, dict):
            actual = summary.get("dc_code")
            if actual is not None:
                return str(actual).upper() == str(expected_dc).upper()
    return False


def analyze(turns: list[dict[str, Any]]) -> dict[str, Any]:
    errors: Counter = Counter()
    tools: Counter = Counter()
    plans: Counter = Counter()
    crm_turns = 0
    sellable_scope_failures = 0
    unknown_tools: set[str] = set()

    for turn in turns:
        plan = turn.get("plan_snapshot") or {}
        plans[plan.get("metric_key") or "none"] += 1
        if _is_crm_customer_turn(turn):
            crm_turns += 1
        scope_ok = _sellable_dc_scope_ok(turn)
        if scope_ok is False:
            sellable_scope_failures += 1
        for te in _tool_entries(turn):
            tools[te.get("name")] += 1
            err = te.get("error")
            if err:
                errors[(te.get("name"), err)] += 1
                if err == "unknown_tool":
                    unknown_tools.add(str(te.get("name")))

    return {
        "total_turns": len(turns),
        "crm_customer_turns": crm_turns,
        "top_errors": errors.most_common(15),
        "top_tools": tools.most_common(15),
        "plan_metric_keys": plans.most_common(15),
        "sellable_dc_scope_failures": sellable_scope_failures,
        "unknown_tools": sorted(unknown_tools),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze chatbot CRM/customer log quality")
    parser.add_argument("--url", required=True, help="chatbot-log-api base URL")
    parser.add_argument("--key", required=True, help="CHATBOT_LOG_API_KEY")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args(argv)

    try:
        payload = _fetch_turns(args.url, args.key, limit=args.limit, days=args.days)
    except (HTTPError, URLError, TimeoutError) as exc:
        print(f"Failed to fetch logs: {exc}", file=sys.stderr)
        return 1

    items = payload.get("items") or []
    report = analyze(items)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
