"""
providers/ibm.py — IBM Power (HMC) adaptörü

Kaynak tablolar:
  ibm_server_general → PowerInfo.hosts (COUNT DISTINCT server_details_servername)
  ibm_server_power   → EnergyMetrics.total_kw'a IBM katkısı

query_logic.md'den taşınan iş bilgisi:
  - HOST_COUNT: COUNT(DISTINCT server_details_servername) WHERE LIKE %dc_code%
  - BATCH_HOST_COUNT: GROUP BY server_details_servername ile toplu sayım

Bilinen sorun (docs/lessons.md — Phase 2 düzeltme listesi):
  ibm_server_power tablosunda timestamp filtresi YOK.
  Enerji değerleri geçmiş tüm kayıtların toplamını içerebilir → anormal yüksek görünür.
  Düzeltme: db-service SQL'e AND timestamp >= NOW() - INTERVAL '4 hours' eklenmesi gerekiyor.

PowerInfo alan haritası:
  hosts → IBM fiziksel Power sunucu sayısı
  vms   → IBM LPAR sayısı (şu an 0; ibm_server_general'dan ileride okunacak)
  cpu   → Rezerv (ileride kullanılacak)
  ram   → Rezerv (ileride kullanılacak)
"""

import logging

from shared.schemas.responses import DCDetail
from src.providers.base import BaseProvider

logger = logging.getLogger(__name__)

IBM_ENERGY_CAVEAT = (
    "ibm_server_power'da timestamp filtresi yok — "
    "enerji toplam değerleri geçmiş verileri içerebilir (anormal yüksek)."
)


class IBMProvider(BaseProvider):
    """IBM Power (HMC) veri kaynağı adaptörü."""

    def enrich_detail(self, detail: DCDetail) -> DCDetail:
        """
        IBM-specific validasyon:
          - IBM host varsa enerji caveat'ını debug log'a yaz
          - IBM host > 0 ama energy == 0 → veri tutarsızlığı uyarısı
        """
        power = detail.power
        energy = detail.energy
        dc_name = detail.meta.name

        if power.hosts > 0:
            logger.debug(
                "DC %s: IBM Power hosts=%d — %s",
                dc_name,
                power.hosts,
                IBM_ENERGY_CAVEAT,
            )

        if power.hosts > 0 and energy.total_kw == 0.0:
            logger.warning(
                "DC %s: IBM Power %d host bildiriyor ancak energy.total_kw=0 — "
                "ibm_server_power verisini ve ILIKE pattern'ini doğrula.",
                dc_name,
                power.hosts,
            )

        return detail
