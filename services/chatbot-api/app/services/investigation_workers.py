"""Map-reduce investigation workers — parallel deterministic data gathering."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Optional

from app.config import settings
from app.services import datacenter_ranking
from app.services.tool_registry import ToolResult, execute_tool, ranking_rows_from_summary


@dataclass
class WorkerFinding:
    entity_id: str
    metrics: dict[str, Any]
    source: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class WorkerBatchResult:
    findings: list[WorkerFinding] = field(default_factory=list)
    extra_results: list[ToolResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def summary_ranking_findings(results: list[ToolResult]) -> list[WorkerFinding]:
    """Extract findings from an existing get_datacenters_summary result."""
    findings: list[WorkerFinding] = []
    for r in results:
        if r.name != "get_datacenters_summary" or r.status != "success":
            continue
        for row in ranking_rows_from_summary(r.summary):
            dc_id = str(row.get("id") or "").upper()
            if not dc_id:
                continue
            findings.append(WorkerFinding(dc_id, dict(row), r.source or r.name))
    return findings


def coverage_status(results: list[ToolResult]) -> tuple[int, int, list[str]]:
    """Return (expected_count, analyzed_count, dc_ids_missing_metrics)."""
    rows, expected = datacenter_ranking.collect_ranking_rows(results)
    missing = datacenter_ranking.rows_missing_metrics(rows)
    analyzed = len(rows)
    if not expected:
        for r in results:
            if r.name == "get_datacenters_summary" and isinstance(r.summary, dict):
                expected = int(r.summary.get("_count") or analyzed)
    return expected, analyzed, missing


def run_detail_workers(
    dc_codes: list[str],
    base_args: dict[str, Any],
    auth_header: Optional[str],
) -> WorkerBatchResult:
    """Fetch get_datacenter_detail in parallel for the given DC codes."""
    if not dc_codes:
        return WorkerBatchResult()

    findings: list[WorkerFinding] = []
    extra: list[ToolResult] = []
    warnings: list[str] = []
    workers = max(1, settings.chatbot_parallel_workers)

    def _fetch(dc_code: str) -> ToolResult:
        args = {**base_args, "dc_code": dc_code}
        return execute_tool("get_datacenter_detail", args, auth_header)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_fetch, dc): dc for dc in dc_codes}
        for fut in as_completed(futures):
            dc = futures[fut]
            try:
                res = fut.result()
            except Exception as exc:  # pragma: no cover
                warnings.append(f"detail worker {dc} failed: {exc}")
                continue
            extra.append(res)
            if res.status != "success" or not isinstance(res.summary, dict):
                warnings.append(f"detail worker {dc}: {res.error or res.status}")
                continue
            row = datacenter_ranking.extract_ranking_row_from_detail(dc, res.summary)
            findings.append(WorkerFinding(dc, row, res.source or res.name))

    return WorkerBatchResult(findings=findings, extra_results=extra, warnings=warnings)
