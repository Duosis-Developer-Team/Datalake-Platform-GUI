"""Metric semantics helpers for the domain-aware planner.

Distinguishes the domain concepts the planner reasons about: CPU usage vs CPU
allocation, the calculation type, and the source preference (db / api / auto).
"""

from __future__ import annotations

from typing import Optional

CPU_USAGE_ALIASES = (
    "cpu kullanım", "cpu usage", "cpu tüketim", "utilization", "tüketen", "kullanan",
)
MEMORY_USAGE_ALIASES = (
    "memory kullanım", "memory usage", "bellek kullanım", "ram kullanım", "ram usage",
    "bellek tüketim", "memory tüketim", "bellek", " memory", " ram",
)
GLOBAL_SCOPE_ALIASES = (
    "tüm datacenter", "tüm dc", "tum datacenter", "tum dc", "all datacenter",
    "all dc", "aralarında", "aralarinda", "genel olarak", "platform geneli",
    "en yoğun", "en yogun", "hangi datacenter", "hangi dc", "busiest datacenter",
    "busiest dc", "datacenter karşılaştır", "datacenter karsilastir", "dc karşılaştır",
)
CPU_ALLOCATED_ALIASES = (
    "allocated", "atanmış", "atanmis", "tahsis", "vm'lere atanmış", "cpu kapasite değişim",
    "allocation",
)
VARIABILITY_ALIASES = (
    "değişken", "degisken", "değişim", "degisim", "dalgalanma", "variance", "variability",
)
TOP_ALIASES = ("top", "en yüksek", "en yuksek", "en çok", "en cok", "listele", "ilk")
DB_ALIASES = ("direkt db", "veritaban", "postgre", "postgresql", "db'den", "database'den", " sql")
API_ALIASES = ("endpoint", "api ", "api'", "webui'da görünen", "grafikte görünen", "kartta görünen")


def has_any(text: str, aliases: tuple[str, ...]) -> bool:
    hay = (text or "").casefold()
    return any(a.casefold() in hay for a in aliases)


def classify_cpu_metric(text: str) -> Optional[str]:
    if has_any(text, CPU_ALLOCATED_ALIASES):
        return "cpu_allocated"
    if has_any(text, CPU_USAGE_ALIASES):
        return "cpu_usage"
    if "cpu" in (text or "").casefold():
        return "cpu"
    return None


def classify_memory_metric(text: str) -> Optional[str]:
    if has_any(text, MEMORY_USAGE_ALIASES):
        return "memory_usage"
    return None


def is_global_scope(text: str) -> bool:
    return has_any(text, GLOBAL_SCOPE_ALIASES)


def classify_calculation(text: str) -> Optional[str]:
    low = (text or "").casefold()
    if has_any(text, VARIABILITY_ALIASES):
        return "variability"
    if has_any(text, TOP_ALIASES):
        return "top"
    if "karşılaştır" in low or "compare" in low:
        return "comparison"
    if "risk" in low or "trend" in low:
        return "risk_analysis"
    return None


def source_preference(text: str) -> str:
    if has_any(text, DB_ALIASES):
        return "db"
    if has_any(text, API_ALIASES):
        return "api"
    return "auto"
