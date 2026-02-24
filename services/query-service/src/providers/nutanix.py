"""
providers/nutanix.py — Nutanix AOS adaptörü

Kaynak tablo: nutanix_cluster_metrics (db-service üzerinden)

Doğrulanmış birim bilgisi (Task 2.4):
  Memory  : total_memory_capacity bytes cinsinden → db-service ×1024 → GB  (TODO: birim düzelt)
  CPU     : total_cpu_capacity birim belirsiz → db-service doğrudan alır → GHz  (TODO: birim düzelt)
  Storage : storage_capacity bytes cinsinden → SQL /2 (dedup) → db-service ÷1024⁴ → TB

Çoklu cluster davranışı:
  Bir DC'de birden fazla Nutanix cluster bulunabilir.
  db-service BATCH sorgularında DISTINCT ON (cluster_name) + SUM ile
  DC başına tek toplu değer üretir.

IntelMetrics alan haritası (Nutanix katkıları):
  hosts     → Nutanix node sayısı (VMware host'larıyla birleşik → toplam)
  cpu_*     → Nutanix CPU katkısı (VMware katkısıyla birleşik toplamda)
  ram_*     → Nutanix bellek katkısı (VMware katkısıyla birleşik toplamda)
  storage_* → Nutanix depolama katkısı — /2 dedup faktörü uygulanmış
"""

import logging

from shared.schemas.responses import DCDetail
from src.providers.base import BaseProvider

logger = logging.getLogger(__name__)

# Task 2.4: Birim dönüşümü (bytes ÷ 1024⁴) db-service'te uygulandı.
# Eşik 10000 TB (10 PB per cluster) — gerçekçi üst sınır; daha yüksek değerler veri hatasına işaret eder.
STORAGE_SANITY_LIMIT_TB = 10000.0


class NutanixProvider(BaseProvider):
    """Nutanix AOS veri kaynağı adaptörü."""

    def enrich_detail(self, detail: DCDetail) -> DCDetail:
        """
        Nutanix-specific validasyon:
          - storage_cap > 5000 TB per cluster → veri toplama anomalisi olabilir
        db-service bytes→TB dönüşümünü (÷1024⁴) uygular; bu metot yalnızca aşırı değerleri loglar.
        """
        intel = detail.intel
        dc_name = detail.meta.name

        if intel.storage_cap > STORAGE_SANITY_LIMIT_TB:
            logger.warning(
                "DC %s: storage_cap=%.1f TB anormal yüksek — "
                "Nutanix storage/2 dedup faktörü uygulandı mı? "
                "(nutanix_cluster_metrics.storage_capacity doğrula).",
                dc_name,
                intel.storage_cap,
            )

        return detail
