"""Analysis synthesizer — turn tool rows into a structured operational analysis.

Deterministic (no LLM): the model later writes the prose, but every number and
risk verdict here comes from the tool data + configured thresholds, so the model
cannot fabricate. Produces an ``AnalysisSummary`` fed into the LLM context.
"""

from __future__ import annotations

import re
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
    extra: dict[str, Any] = field(default_factory=dict)  # profile-specific (e.g. cluster diff)

    def as_context(self) -> dict[str, Any]:
        return asdict(self)


def _avg(r: dict) -> Optional[float]:
    return _num(r, "cpu_pct_avg", "cpu_pct")


def _max(r: dict) -> Optional[float]:
    return _num(r, "cpu_pct_max")


def _name(r: dict) -> str:
    return str(r.get("vm_name") or r.get("host_name") or "?")


def _ckey(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def _synthesize_cluster_diff(plan: IntentPlan, results: list[ToolResult], a: AnalysisSummary) -> AnalysisSummary:
    """Profile: cluster_diff — set difference between the API cluster list and
    the DB cluster inventory. db_only = clusters present in the DB but not
    returned by the endpoint (the user's primary ask)."""
    api_names: list[str] = []
    db_rows: list[dict] = []
    for r in results:
        if r.status != "success":
            continue
        if "clusters" in r.name and not (r.source or "").startswith("postgres"):
            items = r.summary.get("items") if isinstance(r.summary, dict) else None
            if isinstance(items, list):
                api_names = [str(x) for x in items]
        if r.name == "get_dc_vmware_clusters_from_db" or (
            (r.source or "").startswith("postgres") and "cluster" in r.name
        ):
            db_rows = _rows_of(r)

    api_set = {_ckey(n) for n in api_names}
    db_map: dict[str, dict] = {}
    for row in db_rows:
        k = _ckey(row.get("cluster_name"))
        if k:
            db_map[k] = row
    db_only = [row for k, row in db_map.items() if k not in api_set]
    api_only = [n for n in api_names if _ckey(n) not in db_map]
    common = [k for k in db_map if k in api_set]

    # Keep the LLM context compact: the diff lives in `extra` (capped), so we do
    # not also duplicate it into top_entities.
    a.top_entities = []
    classic_only = sum(1 for row in db_only if row.get("cluster_type") == "classic")
    a.extra = {
        "api_cluster_count": len(api_names),
        "db_cluster_count": len(db_rows),
        "common_count": len(common),
        "db_only_count": len(db_only),
        "api_only_count": len(api_only),
        "db_only_classic_count": classic_only,
        # Capped lists keep the LLM context (and fallback table) bounded; the
        # counts above are always the full totals.
        "db_only_clusters": [row.get("cluster_name") for row in db_only[:50]],
        "db_only_rows": [
            {k: row.get(k) for k in ("cluster_name", "cluster_type", "host_count",
                                     "vm_count", "latest_collection_time")}
            for row in db_only[:50]
        ],
        "api_only_clusters": api_only[:50],
        "truncated": len(db_only) > 50,
    }
    a.risks = [
        f"DB'de {len(db_rows)} VMware cluster var; endpoint {len(api_names)} cluster döndürdü → "
        f"{len(db_only)} cluster endpointte yok ({classic_only} classic/KM).",
        "Endpoint zaman/aktiflik filtreli olabilir; DB envanteri eski/inactive cluster'ları da içeriyor.",
    ]
    if api_only:
        a.risks.append(f"{len(api_only)} cluster endpointte var ama DB sorgusunda yok (isim/mapping farkı?).")
    a.recommended_actions = [
        "Endpoint filtering ve cluster visibility kuralını kontrol et.",
        "cluster_metrics ↔ API response mapping'ini ve endpoint zaman penceresini gözden geçir.",
    ]
    a.risk_level = "medium" if db_only else "low"
    a.confidence = "high" if (api_names and db_rows) else "low"
    return a


def _synthesize_allocation(plan: IntentPlan, rows: list[dict], a: AnalysisSummary) -> AnalysisSummary:
    """Profile: cpu_allocation — variability of VM-allocated vCPU per host.

    High variability => VM placement / vCPU change / vMotion / capacity-planning
    signal (not a usage-saturation signal). Direction (artış/azalış) is reported.
    """
    a.top_entities = [
        {
            "name": r.get("host_name"),
            "host": r.get("cluster"),
            "source": "vmware",
            "cpu_pct_avg": _num(r, "alloc_vcpu_avg"),
            "cpu_pct_max": _num(r, "alloc_vcpu_max"),
            "unit": r.get("unit") or "vCPU",
        }
        for r in rows[:10]
    ]
    for r in rows[:5]:
        sd = _num(r, "alloc_vcpu_stddev") or 0
        rng = _num(r, "alloc_vcpu_range") or 0
        chg = _num(r, "alloc_vcpu_change")
        a.risks.append(
            f"{r.get('host_name')} ({r.get('cluster')}): değişkenlik stddev {sd} "
            f"{r.get('unit') or 'vCPU'} (min {r.get('alloc_vcpu_min')}–max {r.get('alloc_vcpu_max')}, "
            f"aralık {rng}), yön: {r.get('direction')} (net değişim {chg})"
        )

    top = rows[0]
    avg = _num(top, "alloc_vcpu_avg") or 0
    sd = _num(top, "alloc_vcpu_stddev") or 0
    ratio = (sd / avg) if avg else 0
    a.risk_level = "high" if ratio >= 0.2 else ("medium" if ratio >= 0.08 else "low")
    a.recommended_actions = [
        "En değişken host'larda VM yerleşimi / vMotion / vCPU değişikliği ve migration geçmişini incele.",
        "Allocation dalgalanması kapasiteyi zorluyorsa cluster bazında vCPU rezervasyon/limitlerini gözden geçir.",
    ]
    is_stale, latest, age_h = _freshness(rows)
    a.freshness = {"latest": latest, "age_hours": age_h, "stale": is_stale}
    if is_stale and latest:
        a.risks.append(f"veri güncel değil (son toplama {latest})")
    return a


def synthesize(
    plan: IntentPlan, results: list[ToolResult], evaluation: EvidenceEvaluation
) -> AnalysisSummary:
    rows = evaluation.primary_rows
    warn = settings.chatbot_cpu_avg_warning_threshold
    crit = settings.chatbot_cpu_avg_critical_threshold
    peak = settings.chatbot_cpu_peak_warning_threshold

    a = AnalysisSummary(confidence=evaluation.confidence, time_window_days=plan.days)
    a.data_quality_warnings = list(evaluation.data_quality_warnings)

    # cluster_diff works off both tool results (API list + DB rows), not primary_rows.
    if plan.analysis_profile == "cluster_diff":
        return _synthesize_cluster_diff(plan, results, a)

    if not rows:
        a.risk_level = "low"
        a.risks = list(evaluation.data_quality_warnings)
        a.recommended_actions = ["İlgili kaynaklarda veri bulunamadı; kaynak/zaman aralığını gözden geçir."]
        return a

    if plan.analysis_profile == "cpu_allocation":
        return _synthesize_allocation(plan, rows, a)

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
