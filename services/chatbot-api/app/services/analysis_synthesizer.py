"""Analysis synthesizer — turn tool rows into a structured operational analysis.

Deterministic (no LLM): the model later writes the prose, but every number and
risk verdict here comes from the tool data + configured thresholds, so the model
cannot fabricate. Produces an ``AnalysisSummary`` fed into the LLM context.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from app.config import settings
from app.services.evidence_evaluator import (
    EvidenceEvaluation,
    _concentrated,
    _freshness,
    _num,
    _rows_of,
)
from app.services.planner import IntentPlan
from app.services.tool_registry import ToolResult


@dataclass
class AnalysisSummary:
    risk_level: str = "low"  # critical | high | medium | low
    confidence: str = "medium"
    time_window_days: Optional[int] = None
    top_entities: list[dict[str, Any]] = field(default_factory=list)
    sustained_high: list[str] = field(default_factory=list)
    peak_spikes: list[str] = field(default_factory=list)
    outliers: Optional[str] = None
    source_distribution: dict[str, int] = field(default_factory=dict)
    source_breakdown: list[dict[str, Any]] = field(default_factory=list)
    host_concentration: Optional[str] = None
    host_context: list[dict[str, Any]] = field(default_factory=list)
    freshness: dict[str, Any] = field(default_factory=dict)
    data_quality_warnings: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)

    def as_context(self) -> dict[str, Any]:
        return asdict(self)


def _avg(r: dict) -> Optional[float]:
    return _num(r, "cpu_pct_avg", "cpu_pct")


def _max(r: dict) -> Optional[float]:
    return _num(r, "cpu_pct_max")


def _name(r: dict) -> str:
    return str(r.get("vm_name") or r.get("host_name") or "?")


def synthesize(
    plan: IntentPlan, results: list[ToolResult], evaluation: EvidenceEvaluation
) -> AnalysisSummary:
    rows = evaluation.primary_rows
    warn = settings.chatbot_cpu_avg_warning_threshold
    crit = settings.chatbot_cpu_avg_critical_threshold
    peak = settings.chatbot_cpu_peak_warning_threshold

    a = AnalysisSummary(confidence=evaluation.confidence, time_window_days=plan.days)
    a.data_quality_warnings = list(evaluation.data_quality_warnings)

    if not rows:
        a.risk_level = "low"
        a.risks = list(evaluation.data_quality_warnings)
        a.recommended_actions = ["İlgili kaynaklarda veri bulunamadı; kaynak/zaman aralığını gözden geçir."]
        return a

    a.top_entities = [
        {
            "name": _name(r),
            "host": r.get("host_name"),
            "source": r.get("source"),
            "cpu_pct_avg": _avg(r),
            "cpu_pct_max": _max(r),
            "unit": r.get("unit"),
        }
        for r in rows[:10]
    ]
    a.sustained_high = [_name(r) for r in rows if (_avg(r) or 0) >= crit]
    a.peak_spikes = [
        _name(r) for r in rows if (_max(r) or 0) >= peak and (_avg(r) or 0) < warn
    ]

    for r in rows:
        s = str(r.get("source", "?"))
        a.source_distribution[s] = a.source_distribution.get(s, 0) + 1

    # per-source breakdown + host context from any summary/host tools that ran
    for r in results:
        if r.status != "success":
            continue
        if "_summary" in r.name and (r.source or "").startswith("postgres") and plan.entity_type in r.name:
            a.source_breakdown = _rows_of(r)
        if r.name == "get_dc_host_cpu_summary" and r.status == "success":
            a.host_context = _rows_of(r)

    a.host_concentration = _concentrated(rows)

    is_stale, latest, age_h = _freshness(rows)
    a.freshness = {"latest": latest, "age_hours": age_h, "stale": is_stale}

    # outliers: are the top-3 clearly separated from the rest?
    avgs = [v for v in (_avg(r) for r in rows) if v is not None]
    if len(avgs) >= 6:
        t3 = sum(avgs[:3]) / 3
        rest = sum(avgs[3:]) / len(avgs[3:])
        if rest > 0 and t3 >= rest * 1.3:
            a.outliers = f"top-3 ort {t3:.0f}% vs diğerleri ort {rest:.0f}%"

    # --- risks + risk level ---
    if a.sustained_high:
        a.risks.append(f"{len(a.sustained_high)} kayıt sürekli yüksek CPU (ort ≥ {crit:.0f}%)")
    if a.peak_spikes:
        a.risks.append(f"{len(a.peak_spikes)} kayıt dönemsel spike (max ≥ {peak:.0f}%, ortalama düşük)")
    if a.host_concentration:
        a.risks.append(f"host yoğunlaşması ({a.host_concentration})")
    if is_stale and latest:
        a.risks.append(f"veri güncel değil (son toplama {latest})")

    if a.sustained_high:
        a.risk_level = "critical"
    elif a.peak_spikes or a.host_concentration:
        a.risk_level = "high"
    elif any((_avg(r) or 0) >= warn for r in rows):
        a.risk_level = "medium"
    else:
        a.risk_level = "low"

    # --- recommended actions ---
    if a.sustained_high:
        a.recommended_actions.append(
            "Sürekli yüksek CPU kullanan kayıtlarda kapasite kontrolü + VM/owner ile sizing görüşmesi."
        )
    if a.peak_spikes:
        a.recommended_actions.append(
            "Spike yapanlarda zamanlı iş/yedek/batch ihtimalini ve CPU trendini incele."
        )
    if a.host_concentration:
        a.recommended_actions.append(
            "Yoğunlaşan host/cluster'da contention analizi (host CPU + üzerindeki VM dağılımı)."
        )
    if is_stale:
        a.recommended_actions.append("Telemetri toplama gecikmesini kontrol et (veri güncel değil).")
    if not a.recommended_actions:
        a.recommended_actions.append("Kritik bulgu yok; rutin kapasite takibi yeterli.")

    return a
