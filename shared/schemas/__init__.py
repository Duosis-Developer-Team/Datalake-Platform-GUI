"""
shared.schemas — Proje geneli Pydantic veri sözleşmeleri.

Tüm servisler (db-service, query-service, gui-service) veri transferinde
bu modüldeki tipleri kullanmak zorundadır.
"""

from shared.schemas.infrastructure import DCMeta, PowerInfo
from shared.schemas.metrics import DCStats, EnergyMetrics, IntelMetrics
from shared.schemas.responses import DCDetail, DCSummary, GlobalOverview

__all__ = [
    # infrastructure
    "DCMeta",
    "PowerInfo",
    # metrics
    "IntelMetrics",
    "EnergyMetrics",
    "DCStats",
    # responses
    "DCSummary",
    "DCDetail",
    "GlobalOverview",
]
