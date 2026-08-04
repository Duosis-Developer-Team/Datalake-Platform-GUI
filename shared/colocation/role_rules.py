"""Hangi Loki rack rolünün sellable colocation envanteri sayıldığı --
DB bilmeyen, değişmez bir değer nesnesi.

Bu kural eskiden allocation.py'deki NON_SELLABLE_ROLE_IDS sabitiydi, yani
deploy anında verilen bir karardı. Artık operatörler Administration ->
Integrations -> NetBox / Loki -> Colocation Configuration ekranından
düzenliyor; bu modül o kararın taşındığı şekil.

Burada bilerek DB erişimi yok: allocation.py saf kalmalı ve kural seti ona
düz bir argüman olarak geçebilmeli, ki bir isteğin ürettiği sayı ile o
isteğin cache anahtarı aynı nesneden hesaplansın.

Bkz. docs/superpowers/specs/2026-08-04-colocation-rack-role-config-design.md
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import blake2s
from typing import Any, Mapping, Sequence

# Bugün canlıda olan davranış (commit 7cd4c9e2): NETWORK (1), NON-STANDART (3)
# ve CUSTOMER (4) hariç, HOST (2) sellable. Migration 047 tam olarak bunu
# seed eder, böylece deploy hiçbir sayıyı oynatmaz.
DEFAULT_SELLABLE: Mapping[str, bool] = {
    "1": False,
    "2": True,
    "3": False,
    "4": False,
}


@dataclass(frozen=True)
class RoleRules:
    """role_id -> sellable eşlemesi, tek ve global."""

    sellable: Mapping[str, bool]

    def is_sellable(self, role_id: Any) -> bool:
        """Bu roldeki bir kabinin boş U'su satılabilir mi?

        Kaydı olmayan, boş veya None rol SELLABLE sayılır -- allocation.py'nin
        eski is_sellable_rack() davranışının aynısı. role_id 100% dolu bir
        kolon; buraya rolsüz gelen tek çağıran, hiç rol verisi taşımayan
        informational aggregate'ler (Floor Map occupancy özeti). Onları
        satılamaz saymak boş U'larını sıfırlar.

        role_id string olarak çözülür: discovery_loki_rack.role_id bir
        VARCHAR, int geldiği garanti değil.
        """
        if role_id is None:
            return True
        key = str(role_id).strip()
        if key not in self.sellable:
            return True
        return bool(self.sellable[key])

    @property
    def etag(self) -> str:
        """Kural setinin 8 haneli parmak izi; cache anahtarına girer.

        Sayaç değil hash: DB'ye elle müdahale edilse bile kendini toparlar,
        satır sırasından etkilenmez, ve ayar eski hâline döndürülünce eski
        cache girdileri tekrar kullanılabilir hale gelir.
        """
        canonical = ";".join(
            f"{rid}={'1' if flag else '0'}"
            for rid, flag in sorted(self.sellable.items())
        )
        return blake2s(canonical.encode("utf-8"), digest_size=4).hexdigest()

    @classmethod
    def from_rows(cls, rows: Sequence[Mapping[str, Any]] | None) -> "RoleRules":
        """gui_colocation_role_rule satırlarından kural seti kur.

        Hiç satır yoksa DEFAULT_RULES döner. Boş sonucu "kural yok, her şey
        satılabilir" diye yorumlamak sellable U'yu sessizce şişirirdi; tablo
        boşsa doğru cevap "henüz seed edilmemiş, bugünkü davranış geçerli".
        """
        mapping: dict[str, bool] = {}
        for row in rows or []:
            raw = row.get("role_id")
            if raw is None:
                continue
            key = str(raw).strip()
            if not key:
                continue
            mapping[key] = bool(row.get("sellable"))
        if not mapping:
            return DEFAULT_RULES
        return cls(mapping)


DEFAULT_RULES = RoleRules(dict(DEFAULT_SELLABLE))
