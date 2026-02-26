"""
responses.py — API sözleşmesi (Data Transfer Objects).

Bu dosyadaki modeller, servisler arasında akan JSON yapılarını tanımlar.
Tüm FastAPI endpoint'leri response_model olarak bu tipleri kullanmak zorundadır.

Bağımlılık zinciri:
  infrastructure.py → metrics.py → responses.py
"""

from pydantic import BaseModel, Field

from shared.schemas.infrastructure import DCMeta, PowerInfo
from shared.schemas.metrics import DCStats, EnergyMetrics, IntelMetrics


class DCSummary(BaseModel):
    """
    GET /datacenters/summary yanıtındaki her DC satırı.
    GUI katmanı kart ve tablo bileşenleri için optimize edilmiştir.
    """

    id:            str  = Field(description="DC kodu (primary key), örn: DC11")
    name:          str  = Field(description="Görüntü adı")
    location:      str  = Field(description="İnsan okunur konum")
    status:        str  = Field(description="'Healthy' | 'Degraded' | 'Unreachable'")
    cluster_count: int  = Field(ge=0)
    host_count:    int  = Field(ge=0)
    vm_count:      int  = Field(ge=0)
    stats:         DCStats


class DCDetail(BaseModel):
    """
    GET /datacenters/{dc_code} yanıtı — tek DC'nin tam metrik profili.
    query-service bu modeli dc_view sayfasına iletir.
    """

    meta:   DCMeta
    intel:  IntelMetrics
    power:  PowerInfo
    energy: EnergyMetrics


class GlobalOverview(BaseModel):
    """
    GET /overview yanıtı — platform geneli özet.
    GUI ana (home) sayfasındaki KPI kartları bu modeli tüketir.
    """

    total_hosts:     int   = Field(ge=0, description="Tüm DC'lerdeki fiziksel + IBM sunucu sayısı")
    total_vms:       int   = Field(ge=0, description="Tüm DC'lerdeki VM sayısı")
    total_energy_kw: float = Field(ge=0, description="Platform toplam enerji tüketimi (kW)")
    dc_count:        int   = Field(ge=0, description="Aktif datacenter sayısı")


class TrendSeries(BaseModel):
    """
    Tek bir metriğe ait zaman serisi.
    Her eleman çifti (labels[i], values[i]) bir ölçüm noktasını temsil eder.
    """

    labels: list[str]   = Field(description="ISO-8601 timestamp dizisi (en eskiden en yeniye)")
    values: list[float] = Field(description="Ölçüm değerleri — labels ile eş boyutlu")


class OverviewTrends(BaseModel):
    """
    GET /overview/trends yanıtı — 3 Sparkline grafiği için zaman serileri.

    Redis'teki sliding window (LPUSH + LTRIM, max 30 nokta) verilerini
    kronolojik sıraya çevirerek döndürür.

    Veri kaynakları:
      cpu_pct   → /datacenters/summary ağırlıksız ortalama CPU
      ram_pct   → /datacenters/summary ağırlıksız ortalama RAM
      energy_kw → /overview total_energy_kw
    """

    cpu_pct:   TrendSeries = Field(description="Platform geneli CPU kullanım yüzdesi (0-100)")
    ram_pct:   TrendSeries = Field(description="Platform geneli RAM kullanım yüzdesi (0-100)")
    energy_kw: TrendSeries = Field(description="Platform toplam enerji tüketimi (kW)")
