"""
infrastructure.py — Datacenter kimlik ve güç bilgileri.

Bu modüldeki tipler, tek bir DC'ye ait "kim olduğu" bilgilerini taşır:
meta veriler (isim, konum) ve IBM Power (HMC) kaynaklı güç-altyapı sayımları.
"""

from pydantic import BaseModel, Field


class DCMeta(BaseModel):
    """Datacenter kimlik bilgileri."""

    name: str = Field(description="DC kodu, örn: DC11")
    location: str = Field(description="İnsan okunur konum adı, örn: Istanbul")

    model_config = {"frozen": True}


class PowerInfo(BaseModel):
    """IBM Power (HMC) kaynaklı altyapı sayımları."""

    hosts: int = Field(default=0, ge=0, description="IBM fiziksel sunucu sayısı")
    vms:   int = Field(default=0, ge=0, description="IBM LPAR / sanal makine sayısı")
    cpu:   int = Field(default=0, ge=0, description="IBM CPU (rezerv, ileride kullanılacak)")
    ram:   int = Field(default=0, ge=0, description="IBM RAM GB (rezerv, ileride kullanılacak)")
