#!/usr/bin/env python3
"""Analyze chatbot turn logs from chatbot-log-api.

Usage:
  python scripts/analyze_chatbot_logs.py --url http://127.0.0.1:8000 --key "$CHATBOT_LOG_API_KEY"
  python scripts/analyze_chatbot_logs.py --via-docker bulutistan-chatbot-log-api --days 30
  python scripts/analyze_chatbot_logs.py --ssh-host root@10.134.52.250 --deploy-dir /opt/Datalake-Platform-GUI
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional


CUSTOMER_KEYWORDS = (
    "müşteri", "musteri", "customer", "itsm", "ticket", "boyner", "akbank",
    "sipariş", "siparis", "sales", "satış", "satis",
)
CRM_KEYWORDS = ("crm", "sellable", "potansiyel", "satılabilir", "satilabilir", "fırsat", "firsat")
BAD_ANSWER_PATTERNS = (
    "erişemiyorum", "veri setinde yok", "belirleyemiyoruz", "httpstatuserror",
    "connecterror", "readtimeout", "hiçbir araç çalıştırılamadı",
)
CUSTOMER_TOOLS = {
    "list_customers", "get_customer_catalog", "get_customer_resources",
    "get_customer_s3_vaults", "get_customer_itsm_summary", "get_customer_itsm_extremes",
    "get_customer_itsm_tickets", "get_customer_sales_summary", "get_customer_sales_active_orders",
    "get_customer_efficiency_by_category", "get_customer_resource_compliance",
}
CRM_TOOLS = {"get_sellable_summary", "get_sellable_by_panel", "get_sellable_by_family"}


@dataclass
class AnalysisReport:
    source: str
    generated_at: str
    days: int
    focus: list[str]
    total_turns: int = 0
    status_counts: dict[str, int] = field(default_factory=dict)
    response_type_counts: dict[str, int] = field(default_factory=dict)
    tool_counts: dict[str, int] = field(default_factory=dict)
    tool_error_counts: dict[str, int] = field(default_factory=dict)
    avg_latency_ms: Optional[float] = None
    avg_tool_calls: Optional[float] = None
    avg_llm_rounds: Optional[float] = None
    customer_related_messages: int = 0
    crm_related_messages: int = 0
    bad_answer_count: int = 0
    zero_tool_success_count: int = 0
    customer_tool_turns: int = 0
    crm_tool_turns: int = 0
    bad_samples: list[dict[str, Any]] = field(default_factory=list)
    customer_samples: list[dict[str, Any]] = field(default_factory=list)
    crm_samples: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "generated_at": self.generated_at,
            "days": self.days,
            "focus": self.focus,
            "total_turns": self.total_turns,
            "status_counts": self.status_counts,
            "response_type_counts": self.response_type_counts,
            "tool_counts": self.tool_counts,
            "tool_error_counts": self.tool_error_counts,
            "avg_latency_ms": self.avg_latency_ms,
            "avg_tool_calls": self.avg_tool_calls,
            "avg_llm_rounds": self.avg_llm_rounds,
            "customer_related_messages": self.customer_related_messages,
            "crm_related_messages": self.crm_related_messages,
            "bad_answer_count": self.bad_answer_count,
            "zero_tool_success_count": self.zero_tool_success_count,
            "customer_tool_turns": self.customer_tool_turns,
            "crm_tool_turns": self.crm_tool_turns,
            "bad_samples": self.bad_samples,
            "customer_samples": self.customer_samples,
            "crm_samples": self.crm_samples,
        }


def _matches_focus(text: str, focus: list[str]) -> bool:
    if not focus or "all" in focus:
        return True
    lower = text.lower()
    if "customer" in focus and any(k in lower for k in CUSTOMER_KEYWORDS):
        return True
    if "crm" in focus and any(k in lower for k in CRM_KEYWORDS):
        return True
    if "sales" in focus and any(k in lower for k in ("sales", "satış", "satis", "sipariş", "siparis")):
        return True
    return False


def _fetch_turns(base_url: str, api_key: str, days: int, max_turns: int) -> list[dict[str, Any]]:
    date_from = (date.today() - timedelta(days=days)).isoformat()
    items: list[dict[str, Any]] = []
    skip = 0
    page_size = 100
    while len(items) < max_turns:
        params = urllib.parse.urlencode({
            "skip": skip,
            "limit": min(page_size, max_turns - len(items)),
            "date_from": date_from,
        })
        url = f"{base_url.rstrip('/')}/api/v1/logs/turns?{params}"
        req = urllib.request.Request(url, headers={"X-Internal-Api-Key": api_key} if api_key else {})
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode())
        batch = payload.get("items") or []
        if not batch:
            break
        items.extend(batch)
        if len(batch) < page_size:
            break
        skip += page_size
    return items


def analyze_turns(
    turns: list[dict[str, Any]],
    *,
    source: str,
    days: int,
    focus: list[str],
) -> AnalysisReport:
    report = AnalysisReport(
        source=source,
        generated_at=datetime.now(timezone.utc).isoformat(),
        days=days,
        focus=focus,
        total_turns=len(turns),
    )
    if not turns:
        return report

    status = Counter()
    response_types = Counter()
    tools = Counter()
    tool_errors = Counter()
    latencies: list[int] = []
    tool_call_counts: list[int] = []
    llm_rounds: list[int] = []

    for turn in turns:
        msg = (turn.get("user_message") or "").lower()
        answer = (turn.get("assistant_answer") or "").lower()
        status[turn.get("status") or "unknown"] += 1
        response_types[turn.get("response_type") or "unknown"] += 1

        if turn.get("latency_ms") is not None:
            latencies.append(int(turn["latency_ms"]))
        if turn.get("tool_call_count") is not None:
            tool_call_counts.append(int(turn["tool_call_count"]))
        elif turn.get("tools"):
            tool_call_counts.append(len(turn["tools"]))
        if turn.get("llm_rounds") is not None:
            llm_rounds.append(int(turn["llm_rounds"]))

        tool_names = []
        for tool in turn.get("tools") or []:
            name = tool.get("name") or "unknown"
            tools[name] += 1
            tool_names.append(name)
            if tool.get("status") == "error":
                tool_errors[name] += 1

        if any(k in msg for k in CUSTOMER_KEYWORDS):
            report.customer_related_messages += 1
            if len(report.customer_samples) < 8:
                report.customer_samples.append({
                    "request_id": turn.get("request_id"),
                    "user_message": turn.get("user_message"),
                    "tools": tool_names,
                    "status": turn.get("status"),
                })
        if any(k in msg for k in CRM_KEYWORDS):
            report.crm_related_messages += 1
            if len(report.crm_samples) < 8:
                report.crm_samples.append({
                    "request_id": turn.get("request_id"),
                    "user_message": turn.get("user_message"),
                    "tools": tool_names,
                    "status": turn.get("status"),
                })

        if any(name in CUSTOMER_TOOLS for name in tool_names):
            report.customer_tool_turns += 1
        if any(name in CRM_TOOLS for name in tool_names):
            report.crm_tool_turns += 1

        is_bad = any(p in answer for p in BAD_ANSWER_PATTERNS)
        zero_tools = not tool_names and turn.get("status") == "success"
        if zero_tools:
            report.zero_tool_success_count += 1
            is_bad = True
        if is_bad and len(report.bad_samples) < 12:
            report.bad_samples.append({
                "request_id": turn.get("request_id"),
                "user_message": turn.get("user_message"),
                "status": turn.get("status"),
                "tools": tool_names,
                "snippet": (turn.get("assistant_answer") or "")[:240],
            })
        if is_bad:
            report.bad_answer_count += 1

    report.status_counts = dict(status)
    report.response_type_counts = dict(response_types)
    report.tool_counts = dict(tools.most_common(30))
    report.tool_error_counts = dict(tool_errors.most_common(15))
    if latencies:
        report.avg_latency_ms = round(sum(latencies) / len(latencies), 1)
    if tool_call_counts:
        report.avg_tool_calls = round(sum(tool_call_counts) / len(tool_call_counts), 2)
    if llm_rounds:
        report.avg_llm_rounds = round(sum(llm_rounds) / len(llm_rounds), 2)
    return report


def render_markdown(report: AnalysisReport) -> str:
    lines = [
        f"# Chatbot Log Analysis — {report.generated_at[:10]}",
        "",
        f"Source: `{report.source}`",
        f"Days window: **{report.days}**",
        f"Focus: `{', '.join(report.focus) or 'all'}`",
        "",
        f"Turns analyzed: **{report.total_turns}**",
        "",
        "## Status distribution",
        "",
    ]
    if report.status_counts:
        for key, val in sorted(report.status_counts.items()):
            lines.append(f"- {key}: {val}")
    else:
        lines.append("- No turns fetched.")
    lines.extend([
        "",
        "## Averages",
        "",
        f"- Latency (ms): {report.avg_latency_ms if report.avg_latency_ms is not None else 'n/a'}",
        f"- Tool calls: {report.avg_tool_calls if report.avg_tool_calls is not None else 'n/a'}",
        f"- LLM rounds: {report.avg_llm_rounds if report.avg_llm_rounds is not None else 'n/a'}",
        "",
        "## Customer / CRM signals",
        "",
        f"- Customer-related messages: {report.customer_related_messages}",
        f"- CRM-related messages: {report.crm_related_messages}",
        f"- Turns with customer tools: {report.customer_tool_turns}",
        f"- Turns with CRM/sellable tools: {report.crm_tool_turns}",
        f"- Bad or empty-investigation answers: {report.bad_answer_count}",
        f"- Zero-tool success turns: {report.zero_tool_success_count}",
        "",
        "## Top tools",
        "",
    ])
    if report.tool_counts:
        for name, count in report.tool_counts.items():
            lines.append(f"- {name}: {count}")
    else:
        lines.append("- n/a")
    lines.extend(["", "## Tool errors", ""])
    if report.tool_error_counts:
        for name, count in report.tool_error_counts.items():
            lines.append(f"- {name}: {count}")
    else:
        lines.append("- n/a")
    if report.bad_samples:
        lines.extend(["", "## Bad answer samples", ""])
        for sample in report.bad_samples:
            lines.append(f"- `{sample['request_id']}` — {(sample.get('user_message') or '')[:80]}")
    if report.customer_samples:
        lines.extend(["", "## Customer message samples", ""])
        for sample in report.customer_samples:
            lines.append(f"- `{sample['request_id']}` — {(sample.get('user_message') or '')[:80]} | tools: {sample.get('tools')}")
    if report.crm_samples:
        lines.extend(["", "## CRM message samples", ""])
        for sample in report.crm_samples:
            lines.append(f"- `{sample['request_id']}` — {(sample.get('user_message') or '')[:80]} | tools: {sample.get('tools')}")
    lines.append("")
    return "\n".join(lines)


def _load_key_from_env_file(deploy_dir: str) -> str:
    env_path = Path(deploy_dir) / ".env.local"
    if not env_path.is_file():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("CHATBOT_LOG_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _remote_fetch_script() -> str:
    return """
import json
import os
import urllib.parse
import urllib.request
from datetime import date, timedelta

key = os.environ.get("CHATBOT_LOG_API_KEY", "")
days = int(os.environ.get("LOG_DAYS", "30"))
max_turns = int(os.environ.get("LOG_MAX", "500"))
date_from = (date.today() - timedelta(days=days)).isoformat()
items = []
skip = 0
while len(items) < max_turns:
    params = urllib.parse.urlencode({
        "skip": skip,
        "limit": min(100, max_turns - len(items)),
        "date_from": date_from,
    })
    headers = {"X-Internal-Api-Key": key} if key else {}
    req = urllib.request.Request(
        f"http://127.0.0.1:8000/api/v1/logs/turns?{params}",
        headers=headers,
    )
    batch = json.loads(urllib.request.urlopen(req, timeout=60).read()).get("items") or []
    items.extend(batch)
    if len(batch) < 100:
        break
    skip += 100
print(json.dumps(items))
"""


def _fetch_via_ssh(ssh_host: str, deploy_dir: str, days: int, max_turns: int) -> list[dict[str, Any]]:
    import base64

    encoded = base64.b64encode(_remote_fetch_script().encode("utf-8")).decode("ascii")
    key_from_env = (
        f'KEY=$(grep "^CHATBOT_LOG_API_KEY=" {deploy_dir}/.env.local 2>/dev/null | cut -d= -f2-); '
        'if [ -z "$KEY" ]; then KEY=$(docker exec bulutistan-chatbot-api printenv CHATBOT_LOG_API_KEY 2>/dev/null); fi; '
    )
    cmd = (
        key_from_env
        + f"docker exec -e CHATBOT_LOG_API_KEY=\"$KEY\" -e LOG_DAYS={days} -e LOG_MAX={max_turns} "
        + f"bulutistan-chatbot-log-api python -c \"import base64; exec(base64.b64decode('{encoded}'))\""
    )
    proc = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", ssh_host, cmd],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(proc.stdout.strip() or "[]")


def _fetch_via_docker(container: str, api_key: str, days: int, max_turns: int) -> list[dict[str, Any]]:
    import base64

    if not api_key:
        api_key = os.environ.get("CHATBOT_LOG_API_KEY", "")
    encoded = base64.b64encode(_remote_fetch_script().encode("utf-8")).decode("ascii")
    proc = subprocess.run(
        [
            "docker", "exec",
            "-e", f"CHATBOT_LOG_API_KEY={api_key}",
            "-e", f"LOG_DAYS={days}",
            "-e", f"LOG_MAX={max_turns}",
            container,
            "python", "-c", f"import base64; exec(base64.b64decode('{encoded}'))",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(proc.stdout.strip() or "[]")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze chatbot audit logs.")
    parser.add_argument("--url", default="", help="chatbot-log-api base URL")
    parser.add_argument("--key", default=os.environ.get("CHATBOT_LOG_API_KEY", ""), help="X-Internal-Api-Key")
    parser.add_argument("--via-docker", default="", help="Fetch via docker exec on this container")
    parser.add_argument("--ssh-host", default="", help="SSH host (e.g. root@10.134.52.250)")
    parser.add_argument("--deploy-dir", default="/opt/Datalake-Platform-GUI", help="Deploy dir for .env.local on SSH host")
    parser.add_argument("--days", type=int, default=30, help="Lookback window in days")
    parser.add_argument("--max-turns", type=int, default=500, help="Maximum turns to fetch")
    parser.add_argument("--focus", default="all", help="Comma-separated: customer,crm,sales,all")
    parser.add_argument("--output-dir", default="docs/chatbot-knowledge/reports", help="Report output directory")
    parser.add_argument("--label", default="", help="Short label for report filename (e.g. test-250, prod-251)")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    focus = [part.strip().lower() for part in args.focus.split(",") if part.strip()]
    label = args.label or (args.ssh_host.replace("@", "-").replace(":", "-") if args.ssh_host else "local")
    source = args.url or args.via_docker or args.ssh_host or "unknown"

    try:
        if args.ssh_host:
            turns = _fetch_via_ssh(args.ssh_host, args.deploy_dir, args.days, args.max_turns)
        elif args.via_docker:
            turns = _fetch_via_docker(args.via_docker, args.key, args.days, args.max_turns)
        else:
            if not args.url:
                print("ERROR: --url required (or use --via-docker / --ssh-host)", file=sys.stderr)
                return 2
            turns = _fetch_turns(args.url, args.key, args.days, args.max_turns)
    except (urllib.error.URLError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"ERROR: failed to fetch logs: {exc}", file=sys.stderr)
        return 1

    if focus and "all" not in focus:
        turns = [t for t in turns if _matches_focus((t.get("user_message") or "").lower(), focus)]

    report = analyze_turns(turns, source=source, days=args.days, focus=focus)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    json_path = out_dir / f"log_analysis_{label}_{stamp}.json"
    md_path = out_dir / f"log_analysis_{label}_{stamp}.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print(f"Turns: {report.total_turns}; bad answers: {report.bad_answer_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
