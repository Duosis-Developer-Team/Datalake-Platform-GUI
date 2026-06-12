"""Deterministic datacenter utilization ranking (no LLM)."""

from __future__ import annotations

from typing import Any, Optional

from app.services.tool_registry import ToolResult, ranking_rows_from_summary

RankingMetric = str  # cpu | memory | vm_count | composite

_METRIC_LABELS = {
    "cpu": "CPU kullanım %",
    "memory": "Bellek kullanım %",
    "vm_count": "VM sayısı",
    "composite": "Bileşik skor (CPU 40% + bellek 40% + VM 20%)",
}


def metric_label(metric: Optional[str]) -> str:
    return _METRIC_LABELS.get(metric or "composite", metric or "composite")


def _f(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _score_row(row: dict[str, Any], metric: RankingMetric, max_vms: float) -> float:
    if metric == "cpu":
        return _f(row.get("used_cpu_pct"))
    if metric == "memory":
        return _f(row.get("used_ram_pct"))
    if metric == "vm_count":
        return _f(row.get("vm_count"))
    cpu = _f(row.get("used_cpu_pct"))
    mem = _f(row.get("used_ram_pct"))
    vm_norm = (_f(row.get("vm_count")) / max_vms * 100.0) if max_vms > 0 else 0.0
    return 0.4 * cpu + 0.4 * mem + 0.2 * vm_norm


def rank_datacenters(
    rows: list[dict[str, Any]],
    metric: RankingMetric = "composite",
) -> list[dict[str, Any]]:
    """Return rows sorted by metric (desc) with rank and score fields."""
    if not rows:
        return []
    max_vms = max((_f(r.get("vm_count")) for r in rows), default=0.0)
    scored = []
    for row in rows:
        score = _score_row(row, metric, max_vms)
        scored.append({**row, "ranking_score": round(score, 2)})
    scored.sort(
        key=lambda r: (
            r.get("ranking_score") or 0,
            _f(r.get("used_cpu_pct")),
            _f(r.get("used_ram_pct")),
            _f(r.get("vm_count")),
        ),
        reverse=True,
    )
    for i, row in enumerate(scored, start=1):
        row["rank"] = i
    return scored


def collect_ranking_rows(results: list[ToolResult]) -> tuple[list[dict[str, Any]], int]:
    """Merge ranking rows from summary and optional detail tool results."""
    rows_by_id: dict[str, dict[str, Any]] = {}
    expected = 0

    for r in results:
        if r.name != "get_datacenters_summary" or r.status != "success":
            continue
        for row in ranking_rows_from_summary(r.summary):
            dc_id = str(row.get("id") or "").upper()
            if dc_id:
                rows_by_id[dc_id] = row
        if isinstance(r.summary, dict):
            expected = max(expected, int(r.summary.get("_count") or len(rows_by_id)))

    for r in results:
        if r.name != "get_datacenter_detail" or r.status != "success":
            continue
        if not isinstance(r.summary, dict):
            continue
        dc_id = _dc_code_from_detail_result(r)
        if not dc_id:
            continue
        detail_row = extract_ranking_row_from_detail(dc_id, r.summary)
        rows_by_id[dc_id] = {**rows_by_id.get(dc_id, {}), **detail_row}

    return list(rows_by_id.values()), expected


def _dc_code_from_detail_result(result: ToolResult) -> str:
    source = result.source or ""
    if "/datacenters/" in source:
        part = source.rsplit("/datacenters/", 1)[-1].split("?")[0].strip("/")
        if part:
            return part.upper()
    if isinstance(result.summary, dict):
        meta = result.summary.get("meta") or {}
        for key in ("id", "dc_code", "name"):
            val = meta.get(key)
            if val:
                return str(val).upper()
    return ""


def extract_ranking_row_from_detail(dc_code: str, detail: dict[str, Any]) -> dict[str, Any]:
    """Build a compact ranking row from a datacenter detail payload."""
    intel = detail.get("intel") if isinstance(detail.get("intel"), dict) else {}
    meta = detail.get("meta") if isinstance(detail.get("meta"), dict) else {}
    cpu_cap = _f(intel.get("cpu_cap"))
    cpu_used = _f(intel.get("cpu_used"))
    ram_cap = _f(intel.get("ram_cap"))
    ram_used = _f(intel.get("ram_used"))
    return {
        "id": dc_code,
        "name": meta.get("name") or dc_code,
        "location": meta.get("location"),
        "used_cpu_pct": round(cpu_used / cpu_cap * 100, 1) if cpu_cap > 0 else None,
        "used_ram_pct": round(ram_used / ram_cap * 100, 1) if ram_cap > 0 else None,
        "vm_count": intel.get("vms"),
        "host_count": intel.get("hosts"),
    }


def rows_missing_metrics(rows: list[dict[str, Any]]) -> list[str]:
    """DC ids that lack usable CPU/RAM metrics (candidate for detail fan-out)."""
    missing: list[str] = []
    for row in rows:
        dc_id = str(row.get("id") or "").upper()
        if not dc_id:
            continue
        if row.get("used_cpu_pct") is None and row.get("used_ram_pct") is None:
            missing.append(dc_id)
    return missing
