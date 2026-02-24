"""
providers/base.py — Provider Adapter temel sınıfı

Her veri kaynağı (VMware, Nutanix, IBM) bu sınıfı genişletir.
query_logic.md'den taşınan business knowledge (eşikler, birim bilgisi) burada merkezlenir.

Statüs hesaplama mantığı:
  DCDetail.intel alanlarından hesaplama → calculate_status()
  DCSummary.stats alanlarından hesaplama → calculate_status_from_stats()
"""

import logging
from abc import ABC, abstractmethod

from shared.schemas.metrics import DCStats, IntelMetrics
from shared.schemas.responses import DCDetail

logger = logging.getLogger(__name__)


class BaseProvider(ABC):
    """
    Provider adapter temel sınıfı.

    Eşik değerleri (query_logic.md iş kuralları):
      CPU     : %80 üzeri kullanım → Degraded
      RAM     : %85 üzeri kullanım → Degraded
      Storage : %80 üzeri kullanım → Degraded
    """

    CPU_DEGRADED_PCT: float = 80.0
    RAM_DEGRADED_PCT: float = 85.0
    STORAGE_DEGRADED_PCT: float = 80.0

    @abstractmethod
    def enrich_detail(self, detail: DCDetail) -> DCDetail:
        """DCDetail'i provider-specific iş mantığıyla zenginleştirir."""
        ...

    @classmethod
    def calculate_status(cls, intel: IntelMetrics) -> str:
        """
        IntelMetrics kapasitesi ve kullanımından DC sağlık durumu hesaplar.
        get_dc_detail() akışında kullanılır (ham sayısal değerlerden).
        """
        if intel.cpu_cap > 0:
            cpu_pct = (intel.cpu_used / intel.cpu_cap) * 100
            if cpu_pct > cls.CPU_DEGRADED_PCT:
                logger.debug("Status → Degraded: cpu_pct=%.1f%%", cpu_pct)
                return "Degraded"

        if intel.ram_cap > 0:
            ram_pct = (intel.ram_used / intel.ram_cap) * 100
            if ram_pct > cls.RAM_DEGRADED_PCT:
                logger.debug("Status → Degraded: ram_pct=%.1f%%", ram_pct)
                return "Degraded"

        if intel.storage_cap > 0:
            stor_pct = (intel.storage_used / intel.storage_cap) * 100
            if stor_pct > cls.STORAGE_DEGRADED_PCT:
                logger.debug("Status → Degraded: storage_pct=%.1f%%", stor_pct)
                return "Degraded"

        return "Healthy"

    @classmethod
    def calculate_status_from_stats(cls, stats: DCStats) -> str:
        """
        Önceden hesaplanmış yüzde değerlerinden DC sağlık durumu hesaplar.
        get_summary() akışında kullanılır (DCSummary.stats üzerinden).
        """
        if stats.used_cpu_pct > cls.CPU_DEGRADED_PCT:
            return "Degraded"
        if stats.used_ram_pct > cls.RAM_DEGRADED_PCT:
            return "Degraded"
        if stats.used_storage_pct > cls.STORAGE_DEGRADED_PCT:
            return "Degraded"
        return "Healthy"
