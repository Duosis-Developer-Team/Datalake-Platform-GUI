"""Domain catalog — canonical metric definitions and architecture mapping.

Static and compact. Gives the planner canonical names, aliases and tool mappings;
it does not grant any tool outside the allowlisted ToolRegistry. Reconciled
against the live repo (repo code is the source of truth): tool names, units and
table references reflect what actually exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    aliases: tuple[str, ...]
    entity: str  # vm | host | cluster | customer | datacenter | s3 | backup | sla | crm
    metric: Optional[str] = None
    calculation: str = "summary"  # top | summary | latest | variability | trend | comparison | risk
    architecture: Optional[str] = None  # classic | hyperconverged | power
    unit: Optional[str] = None
    output_type: str = "summary"  # top_list | summary | latest | trend | comparison | risk_analysis
    analysis_profile: str = "generic"  # cpu_usage | cpu_allocation | storage | backup | s3 | sla | crm | generic
    primary_tools: tuple[str, ...] = ()
    fallback_tools: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    required_params: tuple[str, ...] = ()
    default_params: dict[str, Any] = field(default_factory=dict)
    answer_guidance: tuple[str, ...] = ()
    explanation: str = ""


# Architecture vocabulary. cluster_endpoint_tool is the API tool that lists the
# clusters of that architecture for a DC (power has none -> datacenter detail).
ARCHITECTURES: dict[str, dict[str, Any]] = {
    "classic": {
        "aliases": ("klasik", "classic", " km", "km ", "km-", "klasik mimari", "vmware"),
        "provider": "vmware",
        "cluster_endpoint_tool": "get_dc_classic_clusters",
    },
    "hyperconverged": {
        "aliases": ("hyperconverged", "hci", "nutanix", "hiperkonverjant", "hyper-converged"),
        "provider": "nutanix",
        "cluster_endpoint_tool": "get_dc_hyperconverged_clusters",
    },
    "power": {
        "aliases": ("power", "ibm", "lpar", "power mimari"),
        "provider": "ibm",
        "cluster_endpoint_tool": "get_datacenter_detail",  # no /power cluster endpoint
    },
}

_CUSTOMER_FORBIDDEN = ("get_customer_resources", "get_customer_itsm_summary", "get_customer_s3_vaults")

METRICS: dict[str, MetricDefinition] = {
    "dc_vmware_cluster_api_db_diff": MetricDefinition(
        key="dc_vmware_cluster_api_db_diff",
        aliases=(
            "endpointlerde gelmeyip db'de olan cluster", "endpointlerde gelmeyip db'de olan",
            "db'de olup endpointte olmayan cluster", "vmware cluster farkı",
            "classic cluster api db difference", "dc cluster endpoint database compare",
            "vmware endpoint db cluster", "endpoint ve database karşılaştır",
            "endpointlerden ve database", "cluster karşılaştır",
        ),
        entity="cluster", architecture="classic", metric="cluster_inventory",
        calculation="api_db_diff", output_type="comparison", analysis_profile="cluster_diff",
        primary_tools=("get_dc_classic_clusters", "get_dc_vmware_clusters_from_db"),
        forbidden_tools=_CUSTOMER_FORBIDDEN,
        required_params=("dc_code",), default_params={"limit": 200},
        answer_guidance=(
            "API cluster sayısı, DB cluster sayısı, ortak ve endpointte olmayan (db_only) sayısını ver.",
            "Önce API vs DB farkını 2-3 cümleyle özetle; db_only cluster sayısını ve en kritik 3 örneği prose içinde ver.",
            "5+ db_only satır varsa sona destekleyici tablo ekle; asla yalnızca tablo döndürme.",
            "Endpoint'in zaman filtreli/aktif-cluster filtreli olabileceğini, DB envanterinin daha geniş olabileceğini yorumla.",
            "Aksiyon: endpoint filtering/cluster visibility kuralı ve cluster_metrics↔API mapping kontrolü.",
        ),
        explanation="VMware classic cluster listesini API endpoint ile DB envanteri (cluster_metrics) arasında karşılaştırır; endpointte olmayıp DB'de olan cluster'ları çıkarır.",
    ),
    "classic_host_cpu_allocation_variability": MetricDefinition(
        key="classic_host_cpu_allocation_variability",
        aliases=(
            "cpu allocated değişken", "allocated cpu değişken", "atanmış cpu değişim",
            "atanmis cpu degisim", "vm'lere atanmış cpu", "vm'lere atanmis cpu",
            "cpu kapasite değişim", "allocation variability", "allocated cpu trend",
            "cpu tahsis değişken", "en değişken klasik host", "km host cpu allocated",
            "klasik mimari host", "tahsis edilen cpu", "cpu allocation",
        ),
        entity="host", architecture="classic", metric="cpu_allocated",
        calculation="variability", unit="vCPU", output_type="top_list",
        analysis_profile="cpu_allocation",
        primary_tools=("get_dc_classic_clusters", "get_dc_classic_host_cpu_allocation_variability"),
        fallback_tools=("get_dc_compute_classic",),
        forbidden_tools=_CUSTOMER_FORBIDDEN,
        required_params=("dc_code",), default_params={"days": 7, "limit": 3},
        answer_guidance=(
            "Min/max/avg/last atanmış vCPU değerlerini ve değişkenliği (stddev/range) prose içinde özetle.",
            "Değişim yönünü artış/azalış/karışık olarak belirt.",
            "Kapasite planlama, VM placement/vMotion ve overcommit riskini yorumla.",
            "Birim vCPU'dur (GHz kapasite kolonu bu veri setinde boş — GHz uydurma).",
            "Top 3 host'u cümle içinde sırala; 4+ satır varsa sona opsiyonel tablo ekle.",
        ),
        explanation="KM (klasik) cluster host'larında VM'lere atanmış vCPU toplamının N günlük değişkenliği.",
    ),
    "dc_vm_cpu_top": MetricDefinition(
        key="dc_vm_cpu_top",
        aliases=(
            "en çok cpu kullanan vm", "en cok cpu kullanan vm", "vm cpu tüketim",
            "vm cpu usage", "vm cpu", "top vm cpu", "vm seviyesinde", "en yüksek cpu vm",
            "vm bazlı cpu", "sanal makine cpu", "cpu kullanan makine",
        ),
        entity="vm", metric="cpu_usage", calculation="top", unit="%/MHz/cores",
        output_type="top_list", analysis_profile="cpu_usage",
        primary_tools=("get_dc_vm_cpu_top",),
        fallback_tools=("get_dc_vm_cpu_latest", "get_dc_vm_cpu_summary", "get_dc_host_cpu_summary"),
        forbidden_tools=_CUSTOMER_FORBIDDEN,
        required_params=("dc_code",), default_params={"days": 7, "limit": 10},
        answer_guidance=(
            "Avg vs max CPU ayrımını yap (sustained high vs spike) — prose özet önce.",
            "Kaynak/birimleri açıkla; VMware VM yüzdesi yoksa uydurma.",
            "En yüksek VM'leri cümle içinde sırala; 4+ satır varsa sona opsiyonel tablo ekle.",
        ),
        explanation="Datacenter'da son N günde en yüksek CPU'lu VM'ler (Nutanix + IBM).",
    ),
    "dc_host_cpu_top": MetricDefinition(
        key="dc_host_cpu_top",
        aliases=("host bazlı cpu", "host cpu kullanım", "dc host cpu", "en yüksek host cpu",
                 "host seviyesinde cpu", "en çok cpu kullanan host", "sunucu cpu", "node cpu"),
        entity="host", metric="cpu_usage", calculation="top", unit="%/GHz/cores",
        output_type="top_list", analysis_profile="cpu_usage",
        primary_tools=("get_dc_host_cpu_top",),
        fallback_tools=("get_dc_host_cpu_summary", "get_dc_host_cpu_latest"),
        forbidden_tools=_CUSTOMER_FORBIDDEN,
        required_params=("dc_code",), default_params={"limit": 10},
        explanation="Datacenter'da host seviyesinde en yüksek CPU (VMware/Nutanix/IBM).",
    ),
    "classic_vs_hyperconverged_cpu": MetricDefinition(
        key="classic_vs_hyperconverged_cpu",
        aliases=("klasik mimari ile hyperconverged", "classic vs hyperconverged",
                 "klasik ve hiperkonverjant", "mimari karşılaştır", "compare architecture",
                 "klasik hyperconverged karşılaştır", "klasik vs nutanix"),
        entity="datacenter", metric="cpu_usage", calculation="comparison",
        unit="mixed", output_type="comparison", analysis_profile="generic",
        primary_tools=("get_dc_compute_classic", "get_dc_compute_hyperconverged"),
        forbidden_tools=_CUSTOMER_FORBIDDEN,
        required_params=("dc_code",),
        explanation="Klasik (VMware/KM) ve hyperconverged (Nutanix) compute kullanımını karşılaştırır.",
    ),
    "classic_compute_summary": MetricDefinition(
        key="classic_compute_summary",
        aliases=("klasik mimari cpu", "classic compute", "km cpu ram", "classic virtualization",
                 "klasik compute özet"),
        entity="cluster", architecture="classic", metric="compute_summary",
        calculation="summary", unit="mixed", output_type="summary", analysis_profile="generic",
        primary_tools=("get_dc_classic_clusters", "get_dc_compute_classic"),
        forbidden_tools=_CUSTOMER_FORBIDDEN,
        required_params=("dc_code",),
        explanation="Klasik (KM) cluster compute (CPU/RAM/storage) özeti.",
    ),
    "global_datacenter_utilization": MetricDefinition(
        key="global_datacenter_utilization",
        aliases=(
            "en yoğun datacenter", "en yogun datacenter", "en yoğun dc", "en yogun dc",
            "hangi datacenter en yoğun", "hangi dc en yoğun", "busiest datacenter",
            "busiest dc", "datacenter karşılaştır", "datacenter karsilastir",
            "dc yoğunluk", "dc yogunluk", "datacenter yoğunluk", "datacenter yogunluk",
            "en yoğun veri merkezi", "en yogun veri merkezi",
        ),
        entity="datacenter", metric="utilization", calculation="comparison",
        unit="mixed", output_type="comparison", analysis_profile="datacenter_ranking",
        primary_tools=("get_datacenters_summary",),
        forbidden_tools=_CUSTOMER_FORBIDDEN,
        required_params=(),
        answer_guidance=(
            "Tüm datacenter'ları karşılaştır; kaç DC incelendiğini açıkça belirt — prose özet önce.",
            "Eksik DC varsa belirt; yalnızca örneklem üzerinden global sonuç çıkarma.",
            "Sıralama kullanıcının seçtiği metriğe göre yapılır (CPU, bellek, VM veya bileşik).",
            "Kazanan DC ve skorunu cümle içinde ver; 4+ satır varsa sona opsiyonel tablo ekle.",
        ),
        explanation="Tüm datacenter'lar arasında kullanım yoğunluğu karşılaştırması.",
    ),
    "global_km_cluster_memory_top": MetricDefinition(
        key="global_km_cluster_memory_top",
        aliases=(
            "memory kullanım", "bellek kullanım", "ram kullanım", "km cluster memory",
            "en yüksek km cluster", "en yuksek km cluster", "km cluster bellek",
            "km cluster ram", "memory en yüksek cluster", "bellek en yüksek cluster",
            "tüm datacenter", "tüm dc", "tum datacenter",
        ),
        entity="cluster", architecture="classic", metric="memory_usage",
        calculation="top", unit="GB/%", output_type="top_list", analysis_profile="memory_usage",
        primary_tools=("get_global_km_cluster_memory_top",),
        fallback_tools=("get_dc_compute_classic",),
        forbidden_tools=_CUSTOMER_FORBIDDEN,
        required_params=(),
        default_params={"limit": 5},
        answer_guidance=(
            "Cluster adı, datacenter, memory_used_gb, memory_capacity_gb ve memory_pct değerlerini prose içinde özetle.",
            "Sıralama memory_used_gb (GB kullanım) bazlıdır; yüzdeyi de göster.",
            "Kaynak: cluster_metrics (KM cluster'lar). API yalnızca DC aggregate döner.",
            "Top bulguları cümle içinde ver; 4+ satır varsa sona opsiyonel tablo ekle.",
        ),
        explanation="Tüm datacenter'lar arasında memory kullanımı en yüksek KM (klasik) cluster'lar.",
    ),
    "hci_compute_summary": MetricDefinition(
        key="hci_compute_summary",
        aliases=("hyperconverged cpu", "nutanix cpu", "hci compute", "hiperkonverjant compute"),
        entity="cluster", architecture="hyperconverged", metric="compute_summary",
        calculation="summary", unit="mixed", output_type="summary", analysis_profile="generic",
        primary_tools=("get_dc_hyperconverged_clusters", "get_dc_compute_hyperconverged"),
        forbidden_tools=_CUSTOMER_FORBIDDEN,
        required_params=("dc_code",),
        explanation="Hyperconverged (Nutanix) cluster compute özeti.",
    ),
    "dc_storage_trend": MetricDefinition(
        key="dc_storage_trend",
        aliases=("storage usage trend", "storage trend", "depolama trend", "storage kullanım trend",
                 "disk kullanım trend", "storage büyüme", "storage capacity", "depolama kapasite"),
        entity="datacenter", metric="storage", calculation="trend", output_type="trend",
        analysis_profile="storage",
        primary_tools=("get_dc_storage_capacity",),
        fallback_tools=("get_dc_zabbix_storage_trend", "get_dc_storage_performance"),
        forbidden_tools=_CUSTOMER_FORBIDDEN,
        required_params=("dc_code",),
        explanation="Datacenter storage kapasite/kullanım durumu ve büyüme eğilimi.",
    ),
    "s3_capacity_risk": MetricDefinition(
        key="s3_capacity_risk",
        aliases=("s3 kapasite risk", "s3 tarafında kapasite", "object storage kapasite",
                 "s3 pool", "nesne depolama kapasite", "s3 doluluk"),
        entity="s3", metric="storage", calculation="risk", output_type="risk_analysis",
        analysis_profile="s3",
        primary_tools=("get_dc_s3_pools",),
        forbidden_tools=_CUSTOMER_FORBIDDEN,
        required_params=("dc_code",),
        explanation="S3/object storage pool kapasite baskısı / risk.",
    ),
    "backup_job_failure": MetricDefinition(
        key="backup_job_failure",
        aliases=("zerto job failure", "job failure oranı", "yedek başarısız", "backup failure",
                 "zerto fail", "veeam fail", "netbackup fail", "yedekleme hata", "backup başarısızlık",
                 "backup job", "yedek job"),
        entity="backup", metric="backup", calculation="risk", output_type="risk_analysis",
        analysis_profile="backup",
        primary_tools=("get_dc_backup_jobs",),
        fallback_tools=("get_dc_backup_summary",),
        required_params=("dc_code",),
        explanation="Yedek/DR job başarısızlık oranı (NetBackup/Zerto/Veeam).",
    ),
    "customer_resource_change": MetricDefinition(
        key="customer_resource_change",
        aliases=("kaynak değişim", "kaynak değişimi", "resource change", "müşteri kaynak",
                 "customer resource", "kaynak kullanım değişim"),
        entity="customer", metric="resource", calculation="trend", output_type="trend",
        analysis_profile="generic",
        primary_tools=("get_customer_resources",),
        required_params=("customer_name",),
        explanation="Bir müşterinin kaynak kullanımının zaman içindeki değişimi.",
    ),
    "sla_risk": MetricDefinition(
        key="sla_risk",
        aliases=("sla", "availability", "erişilebilirlik", "uptime", "downtime", "sla risk"),
        entity="sla", metric="availability", calculation="risk", output_type="risk_analysis",
        analysis_profile="sla",
        primary_tools=("get_sla",),
        explanation="Datacenter SLA / availability riski.",
    ),
    "crm_sellable": MetricDefinition(
        key="crm_sellable",
        aliases=("satılabilir", "satilabilir", "sellable", "potansiyel", "potential", "crm",
                 "fırsat", "firsat"),
        entity="crm", metric="sellable", calculation="summary", output_type="summary",
        analysis_profile="crm",
        primary_tools=("get_sellable_summary",),
        fallback_tools=("get_sellable_by_panel", "get_sellable_by_family"),
        explanation="Satılabilir kapasite (sellable potential) fırsat/risk.",
    ),
}


def all_metric_definitions() -> list[MetricDefinition]:
    return list(METRICS.values())


def get(key: str) -> Optional[MetricDefinition]:
    return METRICS.get(key)


def find_metric_candidates(text: str) -> list[MetricDefinition]:
    """Rank metrics by alias specificity + architecture/entity signal.

    Longest alias hit dominates (more specific question wins), with small
    boosts when the architecture vocabulary or the entity word also appears.
    """
    hay = (text or "").casefold()
    scored: list[tuple[int, MetricDefinition]] = []
    for m in METRICS.values():
        alias_score = 0
        for a in m.aliases:
            if a.casefold() in hay:
                alias_score = max(alias_score, len(a))
        if not alias_score:
            continue
        score = alias_score
        if m.architecture:
            arch_aliases = ARCHITECTURES.get(m.architecture, {}).get("aliases", ())
            if any(a in hay for a in arch_aliases):
                score += 5
        if m.entity and m.entity.casefold() in hay:
            score += 2
        scored.append((score, m))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored]


def match(text: str) -> Optional[MetricDefinition]:
    cands = find_metric_candidates(text)
    return cands[0] if cands else None


def get_by_key(key: str) -> Optional[MetricDefinition]:
    return METRICS.get(key)
