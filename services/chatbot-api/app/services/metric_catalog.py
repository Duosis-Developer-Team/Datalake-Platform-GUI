"""Domain / data-source / metric-semantics catalog.

Single source of truth that maps *domain concepts* (a metric, its aliases, the
architecture, the calculation) to the *allowlisted tools* that answer them. This
is the chatbot's repo/domain knowledge: it is hand-curated metadata (not a
runtime repo scan, not LLM-chosen), so tool selection stays inside the registry
allowlist while becoming domain-aware instead of purely keyword-driven.

Each entry also carries an ``analysis_profile`` (how the synthesizer should
interpret the result) and ``required_params`` (what the planner must resolve,
possibly via a clarification question).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    aliases: tuple[str, ...]
    entity: str  # vm | host | cluster | customer | datacenter | s3 | backup | sla | crm
    metric: Optional[str] = None  # cpu_usage | cpu_allocated | storage | network | availability | ...
    architecture: Optional[str] = None  # classic | hyperconverged | None(any)
    calculation: str = "summary"  # top | summary | latest | variability | trend | comparison
    output_type: str = "summary"  # top_list | summary | latest | trend | comparison | risk_analysis
    analysis_profile: str = "generic"  # cpu_usage | cpu_allocation | storage | backup | s3 | sla | crm | generic
    db_tools: tuple[str, ...] = ()  # preferred read-only DB tools (allowlisted)
    api_tools: tuple[str, ...] = ()  # API tools (allowlisted)
    required_params: tuple[str, ...] = ()  # planner must resolve these (else clarify)
    default_params: dict = field(default_factory=dict)
    explanation: str = ""

    def all_tools(self, prefer: str = "auto") -> tuple[str, ...]:
        """Tool order honouring a source preference (db / api / auto)."""
        if prefer == "db":
            return self.db_tools + self.api_tools
        if prefer == "api":
            return self.api_tools + self.db_tools
        # auto: API first when present, else DB.
        return (self.api_tools + self.db_tools) if self.api_tools else self.db_tools


# --------------------------------------------------------------------------- #
# Catalog. Aliases are lowercase substrings matched against the message.
# --------------------------------------------------------------------------- #
CATALOG: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        key="classic_host_cpu_allocation_variability",
        aliases=(
            "allocated cpu değişken", "atanmış cpu değişim", "atanmis cpu degisim",
            "cpu kapasite değişim", "cpu allocated", "allocation variability",
            "vm'lere atanmış cpu", "vm'lere atanmis cpu", "klasik mimari host",
            "km host", "km mimari", "allocated değişken", "cpu allocation",
            "atanmış cpu", "tahsis edilen cpu",
        ),
        entity="host", metric="cpu_allocated", architecture="classic",
        calculation="variability", output_type="top_list",
        analysis_profile="cpu_allocation",
        db_tools=("get_dc_classic_host_cpu_allocation_variability",),
        required_params=("dc_code",), default_params={"days": 7, "limit": 3},
        explanation="Klasik (KM) cluster host'larında VM'lere atanmış vCPU toplamının N günlük değişkenliği (stddev/range + yön).",
    ),
    MetricDefinition(
        key="dc_vm_cpu_top",
        aliases=("vm cpu", "vm tüketim", "vm bazlı cpu", "en çok cpu kullanan vm",
                 "top vm cpu", "vm seviyesinde", "sanal makine cpu", "vm'lerin cpu",
                 "vm cpu usage", "cpu kullanan makine"),
        entity="vm", metric="cpu_usage", calculation="top", output_type="top_list",
        analysis_profile="cpu_usage",
        db_tools=("get_dc_vm_cpu_top", "get_dc_vm_cpu_summary"),
        required_params=("dc_code",), default_params={"days": 7, "limit": 10},
        explanation="Datacenter'da son N günde en yüksek CPU'lu VM'ler (Nutanix + IBM).",
    ),
    MetricDefinition(
        key="dc_host_cpu_top",
        aliases=("host cpu", "host bazlı cpu", "en çok cpu kullanan host", "sunucu cpu",
                 "node cpu", "host seviyesinde cpu"),
        entity="host", metric="cpu_usage", calculation="top", output_type="top_list",
        analysis_profile="cpu_usage",
        db_tools=("get_dc_host_cpu_top", "get_dc_host_cpu_summary"),
        required_params=("dc_code",), default_params={"limit": 10},
        explanation="Datacenter'da host seviyesinde en yüksek CPU (VMware/Nutanix/IBM).",
    ),
    MetricDefinition(
        key="classic_vs_hyperconverged_cpu",
        aliases=("klasik mimari ile hyperconverged", "classic vs hyperconverged",
                 "klasik ve hiperkonverjant", "mimari karşılaştır", "compare architecture",
                 "klasik hyperconverged karşılaştır"),
        entity="datacenter", metric="cpu_usage", calculation="comparison",
        output_type="comparison", analysis_profile="generic",
        api_tools=("get_dc_compute_classic", "get_dc_compute_hyperconverged"),
        required_params=("dc_code",), default_params={},
        explanation="Klasik (VMware/KM) ve hyperconverged (Nutanix) compute kullanımını karşılaştırır.",
    ),
    MetricDefinition(
        key="dc_storage_trend",
        aliases=("storage usage trend", "storage trend", "depolama trend",
                 "storage kullanım trend", "disk kullanım trend", "storage büyüme"),
        entity="datacenter", metric="storage", calculation="trend", output_type="trend",
        analysis_profile="storage",
        api_tools=("get_dc_storage_capacity", "get_dc_storage_performance"),
        required_params=("dc_code",),
        explanation="Datacenter storage kapasite/kullanım durumu ve büyüme eğilimi.",
    ),
    MetricDefinition(
        key="s3_capacity_risk",
        aliases=("s3 kapasite risk", "s3 tarafında kapasite", "object storage kapasite",
                 "s3 pool", "nesne depolama kapasite", "s3 doluluk"),
        entity="s3", metric="storage", calculation="risk", output_type="risk_analysis",
        analysis_profile="s3",
        api_tools=("get_dc_s3_pools",),
        required_params=("dc_code",),
        explanation="S3/object storage pool kapasite baskısı / risk.",
    ),
    MetricDefinition(
        key="backup_job_failure",
        aliases=("zerto job failure", "job failure oranı", "yedek başarısız",
                 "backup failure", "zerto fail", "veeam fail", "netbackup fail",
                 "yedekleme hata", "backup başarısızlık"),
        entity="backup", metric="backup", calculation="risk", output_type="risk_analysis",
        analysis_profile="backup",
        api_tools=("get_dc_backup_jobs", "get_dc_backup_summary"),
        required_params=("dc_code",),
        explanation="Yedek/DR job başarısızlık oranı (NetBackup/Zerto/Veeam).",
    ),
    MetricDefinition(
        key="customer_resource_change",
        aliases=("kaynak değişim", "kaynak değişimi", "resource change", "müşteri kaynak",
                 "customer resource", "kaynak kullanım değişim"),
        entity="customer", metric="resource", calculation="trend", output_type="trend",
        analysis_profile="generic",
        api_tools=("get_customer_resources",),
        required_params=("customer_name",),
        explanation="Bir müşterinin kaynak kullanımının zaman içindeki değişimi.",
    ),
    MetricDefinition(
        key="sla_risk",
        aliases=("sla", "availability", "erişilebilirlik", "uptime", "downtime",
                 "sla risk"),
        entity="sla", metric="availability", calculation="risk", output_type="risk_analysis",
        analysis_profile="sla",
        api_tools=("get_sla",),
        explanation="Datacenter SLA / availability riski.",
    ),
    MetricDefinition(
        key="crm_sellable",
        aliases=("satılabilir", "satilabilir", "sellable", "potansiyel", "potential",
                 "crm", "fırsat", "firsat"),
        entity="crm", metric="sellable", calculation="summary", output_type="summary",
        analysis_profile="crm",
        api_tools=("get_sellable_summary", "get_sellable_by_panel", "get_sellable_by_family"),
        explanation="Satılabilir kapasite (sellable potential) fırsat/risk.",
    ),
)


def _norm(text: str) -> str:
    return (text or "").lower()


def match(message: str) -> Optional[MetricDefinition]:
    """Return the best catalog match for the message.

    Scores by the longest alias substring hit (more specific wins), so e.g.
    "klasik mimari host ... allocated değişken" beats a generic "cpu" match.
    """
    text = _norm(message)
    best: Optional[MetricDefinition] = None
    best_score = 0
    for m in CATALOG:
        score = 0
        for alias in m.aliases:
            if alias in text:
                score = max(score, len(alias))
        if score > best_score:
            best_score, best = score, m
    return best


def get(key: str) -> Optional[MetricDefinition]:
    for m in CATALOG:
        if m.key == key:
            return m
    return None
