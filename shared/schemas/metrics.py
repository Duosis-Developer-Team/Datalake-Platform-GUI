"""
metrics.py — Datacenter kaynak ve enerji metrikleri.

Birim sözleşmesi (tüm servisler bu birimleri kullanmak zorundadır):
  CPU     : GHz
  Memory  : GB
  Storage : TB
  Energy  : kW
  Yüzde   : 0.0 – 100.0 (%)
"""

from pydantic import BaseModel, Field, model_validator
from typing import Self


class IntelMetrics(BaseModel):
    """
    VMware + Nutanix toplamından elde edilen hesaplanmış kaynak metrikleri.

    Tüm kapasite/kullanım çiftleri aynı birimi taşır.
    DB'den gelen ham veriler database_service._aggregate_dc() içinde normalize edilir;
    bu model normalize edilmiş değerleri alır.
    """

    clusters:     int   = Field(default=0, ge=0, description="Cluster sayısı")
    hosts:        int   = Field(default=0, ge=0, description="Fiziksel sunucu sayısı (Nutanix + VMware)")
    vms:          int   = Field(default=0, ge=0, description="Sanal makine sayısı")

    cpu_cap:      float = Field(default=0.0, ge=0, description="Toplam CPU kapasitesi (GHz)")
    cpu_used:     float = Field(default=0.0, ge=0, description="Kullanılan CPU (GHz)")
    ram_cap:      float = Field(default=0.0, ge=0, description="Toplam bellek kapasitesi (GB)")
    ram_used:     float = Field(default=0.0, ge=0, description="Kullanılan bellek (GB)")
    storage_cap:  float = Field(default=0.0, ge=0, description="Toplam depolama kapasitesi (TB)")
    storage_used: float = Field(default=0.0, ge=0, description="Kullanılan depolama (TB)")

    @model_validator(mode="after")
    def used_within_cap(self) -> Self:
        """
        Kullanım değeri kapasiteyi geçemez.
        DB gecikmesinden kaynaklanan geçici tutarsızlıklarda sert hata yerine
        değeri kapasite ile sınırlar (soft-clamp).
        """
        if self.cpu_cap > 0 and self.cpu_used > self.cpu_cap:
            object.__setattr__(self, "cpu_used", self.cpu_cap)
        if self.ram_cap > 0 and self.ram_used > self.ram_cap:
            object.__setattr__(self, "ram_used", self.ram_cap)
        if self.storage_cap > 0 and self.storage_used > self.storage_cap:
            object.__setattr__(self, "storage_used", self.storage_cap)
        return self


class EnergyMetrics(BaseModel):
    """Raf + IBM + vCenter kaynaklarından hesaplanan toplam enerji tüketimi."""

    total_kw: float = Field(default=0.0, ge=0, description="Toplam güç tüketimi (kW)")


class DCStats(BaseModel):
    """
    GUI katmanına sunulan, insan okunur formatlı özet metrikler.
    Yüzde alanları 0–100 arasında tutulur.
    """

    total_cpu:          str   = Field(description="Örn: '1234 / 5000 GHz'")
    used_cpu_pct:       float = Field(ge=0, le=100, description="CPU kullanım yüzdesi")

    total_ram:          str   = Field(description="Örn: '2048 / 4096 GB'")
    used_ram_pct:       float = Field(ge=0, le=100, description="Bellek kullanım yüzdesi")

    total_storage:      str   = Field(description="Örn: '50 / 200 TB'")
    used_storage_pct:   float = Field(ge=0, le=100, description="Depolama kullanım yüzdesi")

    last_updated:       str   = Field(description="'Live' veya ISO timestamp")
    total_energy_kw:    float = Field(ge=0, description="Toplam enerji tüketimi (kW)")
