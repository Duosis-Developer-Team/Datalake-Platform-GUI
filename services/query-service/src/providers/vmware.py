"""
providers/vmware.py — VMware vCenter adaptörü

Kaynak tablo: datacenter_metrics (db-service üzerinden)

query_logic.md'den taşınan birim bilgisi:
  CPU     : total_cpu_ghz_* sütunları GHz → SQL ×1e9 (Hz) → db-service ÷1e9 → GHz
  Memory  : total_memory_*_gb sütunları GB → SQL ×1024³ (Bytes) → db-service ÷1024³ → GB
  Storage : total_storage_*_gb sütunları GB → SQL ×1024² (KB) → db-service ÷1024⁴ → TB

IntelMetrics alan haritası (VMware katkıları):
  clusters  → VMware-only cluster sayısı (total_cluster_count)
  hosts     → VMware fiziksel host sayısı (Nutanix node'larıyla birleşik → toplam)
  vms       → VMware VM sayısı (total_vm_count)
  cpu_*     → VMware CPU katkısı (Nutanix katkısıyla birleşik toplamda)
  ram_*     → VMware bellek katkısı (Nutanix katkısıyla birleşik toplamda)
  storage_* → VMware depolama katkısı (Nutanix katkısıyla birleşik toplamda)
"""

import logging

from shared.schemas.responses import DCDetail
from src.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class VMwareProvider(BaseProvider):
    """VMware vCenter veri kaynağı adaptörü."""

    def enrich_detail(self, detail: DCDetail) -> DCDetail:
        """
        VMware-specific validasyon:
          - cluster_count > 0 ama cpu_cap == 0 → olası birim dönüşüm sorunu
          - cluster_count > 0 ama ram_cap == 0 → eksik veri
        db-service birim dönüşümünü halleder; bu metot sadece tutarsızlıkları loglar.
        """
        intel = detail.intel
        dc_name = detail.meta.name

        if intel.clusters > 0 and intel.cpu_cap == 0.0:
            logger.warning(
                "DC %s: VMware %d cluster bildiriyor ancak cpu_cap=0 — "
                "datacenter_metrics birim dönüşümünü doğrula (total_cpu_ghz_capacity).",
                dc_name,
                intel.clusters,
            )

        if intel.clusters > 0 and intel.ram_cap == 0.0:
            logger.warning(
                "DC %s: VMware %d cluster bildiriyor ancak ram_cap=0 — "
                "datacenter_metrics verisini doğrula (total_memory_capacity_gb).",
                dc_name,
                intel.clusters,
            )

        return detail
