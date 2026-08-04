# Colocation Rack Role Config Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Operatörler, sellable colocation U hesabına hangi Loki rack rolünün gireceğini Administration ekranından ayarlayabilsin; bugünkü davranış varsayılan olarak korunsun.

**Architecture:** Kural seti `bulutwebui`'deki yeni `gui_colocation_role_rule` tablosunda tutulur, `RoleRules` adlı DB-bilmeyen frozen bir değer nesnesine dönüştürülür ve saf `shared/colocation/allocation.py` fonksiyonlarına **parametre olarak** geçirilir. Aynı nesnenin `etag`'i customer-api cache anahtarlarına girer, böylece ayar değişince bayat sayı servis edilemez.

**Tech Stack:** Python 3.11, FastAPI (customer-api), psycopg2 + PostgreSQL (bulutwebui), Dash + dash-mantine-components (GUI), pytest.

**Spec:** `docs/superpowers/specs/2026-08-04-colocation-rack-role-config-design.md`

## Global Constraints

- **Ayar globaldir.** DC bazlı istisna kapsam dışı — `dc` kolonu, `UNIQUE (dc, role_id)`, per-DC endpoint veya per-DC UI **yazılmayacak**.
- `discovery_loki_rack.role_id` bir **VARCHAR**'dır. Rol id'leri her yerde **string** olarak karşılaştırılır; int'e coerce edilmez.
- Bilinmeyen, kayıtsız veya `None` rol → **sellable** sayılır. Bugünkü `is_sellable_rack()` davranışı budur ve korunur.
- Config okunamıyorsa (webui kapalı) veya tablo boşsa → `DEFAULT_RULES`. **Asla** "her şey sellable" varsayılmaz.
- Varsayılan kural seti: `{"1": False, "2": True, "3": False, "4": False}` (NETWORK/NON-STANDART/CUSTOMER excluded, HOST sellable).
- `COLOCATION_ROLE_IDS`, `is_colocation_rack()`, `is_network_rack()` **değişmez** — müşteri atfı bu işin konusu değil.
- Mevcut public imzalar geriye uyumlu kalır: `is_sellable_rack(role_id)` ve `NON_SELLABLE_ROLE_IDS` silinmez.
- Test disiplini: her test, yakaladığı somut bozulmayı bir cümleyle söyleyebilmeli. Plandaki testler bu kapıdan geçmiştir; **plana ek test yazmayın** — bir boşluk görürseniz önce onu bildirin.
- Her task kendi commit'ini alır ve **hemen pushlanır** (`git push origin worktree-sellable-u-role-filter`).

### İki tüketici, iki ayrı process

Bu ayarı okuyan iki kod yolu **farklı container'larda** çalışır:

| | Colocation kartı | CRM Sellable paneli |
|---|---|---|
| Servis | **customer-api** | **crm-engine** (`:8070`) |
| Sınıf | `ColocationMatchingService` | `SellableService` |
| Nerede kurulur | `services/customer-api/app/routers/colocation.py:11-14`, **istek başına** | `services/crm-engine/app/main.py:201`, uygulama ömrü boyunca tek |
| Cache | customer-api Redis, `colocation:{dc}` | crm-engine Redis **DB 2**, `sellable:panels:...` |

`services/crm-engine/Dockerfile:27` **`services/customer-api/app/` dizinini crm-engine imajına kopyalar**, sonra satır 29 crm-engine'in kendi `app/`'ini üstüne yazar. Yani:

- `app/services/sellable_service.py`, `app/services/colocation_role_rule_service.py`, `app/db/queries/colocation_config.py` **tek dosyadır** — customer-api altında bir kez düzenlenir, crm-engine otomatik alır. Kopyalamayın.
- Ama **kurulum (wiring) iki yerdedir**: `routers/colocation.py` (customer-api) ve `crm-engine/app/main.py`.

**Cross-service cache invalidation YOKTUR ve gerekmez.** customer-api'deki PUT, crm-engine'in Redis'ine erişemez. Doğruluk cache anahtarındaki etag'den gelir: crm-engine kuralı aynı webui tablosundan 30 saniyelik memo ile okur, kural değişince yeni etag → yeni anahtar → yeniden hesap. **Yayılma süresi ≤30 sn.** customer-api'nin PUT'u yalnızca *kendi* `colocation:` prefix'ini temizler. crm-engine'e HTTP çağrısı eklemeyin; oradaki tek invalidation ucu `POST /admin/cache/refresh`, o da bütün snapshot'ları yeniden hesaplayan ağır bir iştir — bir ayar kaydına bağlanmaz.

**Test komutları (doğrulandı 2026-08-04):**

```bash
# GUI + shared testleri — worktree kökünden
cd /Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI/.claude/worktrees/sellable-u-role-filter
.venv/bin/python -m pytest tests/test_colocation_allocation.py -q

# customer-api testleri — services/customer-api içinden, kökteki venv ile
cd services/customer-api
../../.venv/bin/python -m pytest tests/test_colocation_sellable_totals.py -q
```

Sistem `python3`'ü 3.9'dur ve testleri bozar; **daima `.venv/bin/python` kullanın.**

## File Structure

| Dosya | Sorumluluk | Task |
|---|---|---|
| `shared/colocation/role_rules.py` | **Yeni.** `RoleRules` değer nesnesi, `DEFAULT_RULES`, `etag` | 1 |
| `tests/test_colocation_role_rules.py` | **Yeni.** Task 1 testleri | 1 |
| `shared/colocation/allocation.py` | `rules` parametresi eklenir; `is_sellable_rack` `DEFAULT_RULES`'a delege eder | 2 |
| `tests/test_colocation_allocation_rules.py` | **Yeni.** Task 2 testleri | 2 |
| `shared/colocation/occupancy.py` | `role_catalog(cursor)` eklenir (canlı `discovery_loki_rack` rol kataloğu) | 3 |
| `services/customer-api/migrations/webui/047_colocation_role_rule.sql` | **Yeni.** Tablo + seed | 3 |
| `services/customer-api/app/db/queries/colocation_config.py` | **Yeni.** LIST / UPSERT SQL | 3 |
| `services/customer-api/app/services/colocation_role_rule_service.py` | **Yeni.** webui CRUD + `load_rules()` + 30s memo | 3 |
| `services/customer-api/app/models/schemas.py` | `ColocationRoleRule*` pydantic modelleri | 3 |
| `services/customer-api/app/routers/colocation_config.py` | **Yeni.** GET / PUT `/colocation/role-rules` | 3 |
| `services/customer-api/app/main.py` | Router kaydı | 3 |
| `services/customer-api/tests/test_colocation_role_rule_service.py` | **Yeni.** Task 3 testleri | 3 |
| `services/customer-api/app/services/sellable_service.py` | `_query_colocation_totals` kuralı geçirir; cache key'e etag (crm-engine'in de kullandığı **paylaşık** dosya) | 4 |
| `services/customer-api/app/services/colocation_matching_service.py` | `_fetch_colocation` kuralı geçirir; cache key'e etag | 4 |
| `services/customer-api/app/routers/colocation.py` | Kural servisini istek başına değil app-scoped verir | 4 |
| `services/crm-engine/app/main.py` | `SellableService`'e `role_rules_service` enjekte eder | 4 |
| `services/customer-api/tests/test_colocation_rules_wiring.py` | **Yeni.** Task 4 testleri | 4 |
| `src/services/api_client.py` | `get_colocation_role_rules` / `put_colocation_role_rules` + invalidation | 5 |
| `tests/test_api_client_colocation_role_rules.py` | **Yeni.** Task 5 testleri | 5 |
| `src/utils/colocation_config_ui.py` | **Yeni.** Saf tablo/önizleme yardımcıları | 6 |
| `src/pages/settings/integrations/colocation_config.py` | **Yeni.** Sayfa layout'u | 6 |
| `src/pages/settings/integrations/colocation_config_callbacks.py` | **Yeni.** Save / preview / modal callback'leri | 6 |
| `src/pages/settings/shell.py` | `NETBOX_TABS`, `_PAGE_BUILDERS`, `_sub_nav`, `_breadcrumb` | 6 |
| `src/auth/permission_catalog.py`, `src/auth/permission_service.py` | Yeni permission kodu + route eşlemesi | 6 |
| `app.py` | Callback modülü import'u | 6 |
| `tests/test_colocation_config_page.py` | **Yeni.** Task 6 testleri | 6 |

---

### Task 1: `RoleRules` değer nesnesi

**Files:**
- Create: `shared/colocation/role_rules.py`
- Test: `tests/test_colocation_role_rules.py`

**Interfaces:**
- Consumes: hiçbir şey (yeni, bağımsız modül).
- Produces:
  - `RoleRules(sellable: Mapping[str, bool])` — frozen dataclass
  - `RoleRules.is_sellable(role_id: Any) -> bool`
  - `RoleRules.etag -> str` (property, 8 hex hane)
  - `RoleRules.from_rows(rows: Sequence[Mapping[str, Any]] | None) -> RoleRules` (classmethod)
  - `DEFAULT_RULES: RoleRules`
  - `DEFAULT_SELLABLE: Mapping[str, bool]`

- [ ] **Step 1: Testi yaz**

`tests/test_colocation_role_rules.py`:

```python
"""RoleRules — kural çözümü ve etag davranışı."""

from shared.colocation.role_rules import DEFAULT_RULES, RoleRules


def test_unknown_and_missing_roles_are_sellable():
    """Rol taşımayan satırlar (Floor Map occupancy özeti) sellable kalmalı.

    Yakaladığı bozulma: bilinmeyen rolü 'satılamaz' saymak, rol bilgisi
    olmayan aggregate'lerin boş U'sunu sessizce sıfırlar.
    """
    rules = RoleRules({"1": False, "2": True})
    assert rules.is_sellable(None) is True
    assert rules.is_sellable("") is True
    assert rules.is_sellable("99") is True
    assert rules.is_sellable(" 2 ") is True   # varchar, trimlenir
    assert rules.is_sellable(1) is False      # int gelse de string gibi çözülür


def test_empty_rows_fall_back_to_default_rules():
    """Tablo boşsa/okunamıyorsa bugünkü kural seti geçerli olmalı.

    Yakaladığı bozulma: boş sonucu 'hiç kural yok, her şey sellable' diye
    yorumlamak sellable U'yu 3.503'ten platform toplamına şişirir.
    """
    assert RoleRules.from_rows([]) == DEFAULT_RULES
    assert RoleRules.from_rows(None) == DEFAULT_RULES


def test_etag_is_order_independent():
    """Aynı kural seti, satırlar farklı sırada okunduğunda aynı etag vermeli.

    Yakaladığı bozulma: sıraya duyarlı etag her istekte yeni cache anahtarı
    üretir, 6 saatlik colocation cache'i tamamen etkisiz kalır.
    """
    a = RoleRules.from_rows([{"role_id": "1", "sellable": False},
                             {"role_id": "2", "sellable": True}])
    b = RoleRules.from_rows([{"role_id": "2", "sellable": True},
                             {"role_id": "1", "sellable": False}])
    assert a.etag == b.etag


def test_etag_changes_when_a_rule_changes():
    """Bir rol sellable yapılınca etag değişmeli.

    Yakaladığı bozulma: etag sabit kalırsa operatör ayarı kaydeder, cache
    eski anahtarla eski sayıyı servis etmeye devam eder -- 'kaydettim ama
    ekran değişmedi' şikâyetinin ta kendisi.
    """
    before = RoleRules({"1": False, "2": True})
    after = RoleRules({"1": True, "2": True})
    assert before.etag != after.etag
    assert len(before.etag) == 8
```

- [ ] **Step 2: Testi çalıştır, kırmızı olduğunu gör**

```bash
.venv/bin/python -m pytest tests/test_colocation_role_rules.py -q
```

Beklenen: `ModuleNotFoundError: No module named 'shared.colocation.role_rules'`

- [ ] **Step 3: Modülü yaz**

`shared/colocation/role_rules.py`:

```python
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
```

- [ ] **Step 4: Testi çalıştır, yeşil olduğunu gör**

```bash
.venv/bin/python -m pytest tests/test_colocation_role_rules.py -q
```

Beklenen: `4 passed`

- [ ] **Step 5: Commit ve push**

```bash
git add shared/colocation/role_rules.py tests/test_colocation_role_rules.py
git commit -m "feat(colocation): RoleRules değer nesnesi ve varsayılan kural seti"
git push origin worktree-sellable-u-role-filter
```

---

### Task 2: `allocation.py` kural setini parametre olarak alsın

**Files:**
- Modify: `shared/colocation/allocation.py:108-141` (`is_sellable_rack`, `sellable_rack_totals`), `:270-390` (`aggregate_rack_allocations`)
- Test: `tests/test_colocation_allocation_rules.py`

**Interfaces:**
- Consumes: `RoleRules`, `DEFAULT_RULES` (Task 1).
- Produces:
  - `sellable_rack_totals(rows, rules: RoleRules = DEFAULT_RULES) -> tuple[float, float]`
  - `aggregate_rack_allocations(rows, rules: RoleRules = DEFAULT_RULES) -> dict`
  - `is_sellable_rack(role_id)` ve `NON_SELLABLE_ROLE_IDS` **imzasız değişmeden** kalır.

- [ ] **Step 1: Testi yaz**

`tests/test_colocation_allocation_rules.py`:

```python
"""allocation.py'nin kural setini parametre olarak alması."""

from shared.colocation.allocation import (
    aggregate_rack_allocations,
    sellable_rack_totals,
)
from shared.colocation.role_rules import RoleRules

# Dört rolden birer kabin. free_u değerleri bilerek farklı, ki hangi rolün
# havuza girdiği toplamdan okunabilsin.
ROWS = [
    {"rack_name": "N1", "role_id": "1", "capacity_u": 40, "used_u": 10, "free_u": 30},
    {"rack_name": "H1", "role_id": "2", "capacity_u": 40, "used_u": 15, "free_u": 25},
    {"rack_name": "S1", "role_id": "3", "capacity_u": 40, "used_u": 20, "free_u": 20},
    {"rack_name": "C1", "role_id": "4", "capacity_u": 40, "used_u": 25, "free_u": 15},
]


def test_default_rules_reproduce_todays_numbers():
    """rules verilmezse bugünkü davranış birebir çıkmalı: yalnız HOST sellable.

    Yakaladığı bozulma: varsayılan kayarsa canlı sellable U deploy anında
    kimse dokunmadan değişir -- 8. şikâyette düzeltilen sayı geri bozulur.
    """
    assert sellable_rack_totals(ROWS) == (40.0, 15.0)
    assert aggregate_rack_allocations(ROWS)["sellable_free_u"] == 25


def test_making_customer_racks_sellable_moves_their_free_u_into_the_pool():
    """CUSTOMER (4) sellable yapılınca free U'su havuza girmeli ve breakdown
    bayrağı da dönmeli.

    Yakaladığı bozulma: kural okunuyor ama toplamaya uygulanmıyorsa ekran
    ayarı kaydeder, sayı değişmez; ya da toplam değişir ama kartın legend'ı
    hâlâ 'satılamaz' der -- ikisi birbiriyle çelişir.
    """
    rules = RoleRules({"1": False, "2": True, "3": False, "4": True})

    assert sellable_rack_totals(ROWS, rules) == (80.0, 40.0)

    agg = aggregate_rack_allocations(ROWS, rules)
    assert agg["sellable_free_u"] == 40           # 25 (HOST) + 15 (CUSTOMER)
    assert agg["colocation_allocated_u"] == 80    # müşteri atfı DEĞİŞMEDİ
    bucket = next(b for b in agg["role_breakdown"] if b["role_id"] == "4")
    assert bucket["sellable"] is True
```

- [ ] **Step 2: Testi çalıştır, kırmızı olduğunu gör**

```bash
.venv/bin/python -m pytest tests/test_colocation_allocation_rules.py -q
```

Beklenen: `TypeError: sellable_rack_totals() takes 1 positional argument but 2 were given`

- [ ] **Step 3: `allocation.py`'yi değiştir**

Dosyanın başındaki import'lara ekle:

```python
from shared.colocation.role_rules import DEFAULT_RULES, RoleRules
```

`NON_SELLABLE_ROLE_IDS` tanımının hemen altına yorum ekle (sabit **silinmiyor**):

```python
NETWORK_ROLE_IDS = frozenset({"1"})
NON_SELLABLE_ROLE_IDS = COLOCATION_ROLE_IDS | NETWORK_ROLE_IDS
# NON_SELLABLE_ROLE_IDS artık VARSAYILANI anlatır, tek gerçeği değil: kural
# seti 2026-08-04'ten beri operatörün ayarladığı bir şey (role_rules.py).
# Sabit, kural taşımayan eski çağıranlar ve is_sellable_rack() için duruyor.
```

`is_sellable_rack`'in gövdesini `DEFAULT_RULES`'a delege et (docstring'e ek cümle):

```python
def is_sellable_rack(role_id: Any) -> bool:
    """True when free U in this rack can be sold to a new customer.

    False for roles 1/3/4 (see NON_SELLABLE_ROLE_IDS). An absent or
    unrecognised role is treated as SELLABLE, not as network: role_id is 100%
    populated in discovery_loki_rack, so the only callers that reach here
    without one are the informational aggregates that carry no role data at
    all (the Floor Map occupancy summary). Defaulting those to non-sellable
    would silently zero their free U instead of leaving it unclassified.

    Bu fonksiyon VARSAYILAN kural setini uygular. Operatörün ayarını
    hesaba katması gereken çağıranlar sellable_rack_totals /
    aggregate_rack_allocations'a ``rules`` geçmelidir.
    """
    return DEFAULT_RULES.is_sellable(role_id)
```

`sellable_rack_totals` imzasını ve filtresini değiştir:

```python
def sellable_rack_totals(
    rows: Sequence[dict], rules: RoleRules = DEFAULT_RULES
) -> tuple[float, float]:
    """``(capacity_u, used_u)`` summed over sellable racks only.

    ... (mevcut docstring aynen kalır) ...

    ``rules`` verilmezse varsayılan kural seti uygulanır, yani bu fonksiyonun
    eski çağıranları hiç değişmeden aynı sayıyı almaya devam eder.
    """
    capacity = 0
    used = 0
    for row in rows or []:
        if not rules.is_sellable(row.get("role_id")):
            continue
        capacity += int(row.get("capacity_u") or 0)
        used += int(row.get("used_u") or 0)
    return float(capacity), float(used)
```

`aggregate_rack_allocations` imzasını değiştir ve içindeki **üç** `is_sellable_rack(role_id)` çağrısını `rules.is_sellable(role_id)` yap:

```python
def aggregate_rack_allocations(
    rows: Sequence[dict], rules: RoleRules = DEFAULT_RULES
) -> dict:
```

```python
            bucket = {
                "role_id": role_key,
                "role_name": ROLE_NAMES.get(role_key, "UNKNOWN"),
                "sellable": rules.is_sellable(role_id),
                "rack_count": 0, "capacity_u": 0, "used_u": 0, "free_u": 0,
            }
```

```python
        if rules.is_sellable(role_id):
            sellable_free_u += free
            sellable_capacity_u += capacity
            sellable_used_u += used
        elif is_network_rack(role_id):
            network_free_u += free
            network_capacity_u += capacity
            network_rack_count += 1
```

`is_colocation_rack(role_id)` çağrısına **dokunma** — müşteri atfı kural setinden bağımsız.

- [ ] **Step 4: Yeni ve mevcut testleri çalıştır**

```bash
.venv/bin/python -m pytest tests/test_colocation_allocation_rules.py tests/test_colocation_allocation.py tests/test_colocation_matching.py tests/test_colocation_occupancy.py -q
```

Beklenen: hepsi PASS (`test_colocation_allocation.py` 54 test dahil).

- [ ] **Step 5: Commit ve push**

```bash
git add shared/colocation/allocation.py tests/test_colocation_allocation_rules.py
git commit -m "feat(colocation): allocation fonksiyonları kural setini parametre olarak alsın"
git push origin worktree-sellable-u-role-filter
```

---

### Task 3: webui tablosu, config servisi ve API uçları

**Files:**
- Create: `services/customer-api/migrations/webui/047_colocation_role_rule.sql`
- Create: `services/customer-api/app/db/queries/colocation_config.py`
- Create: `services/customer-api/app/services/colocation_role_rule_service.py`
- Create: `services/customer-api/app/routers/colocation_config.py`
- Modify: `shared/colocation/occupancy.py` (sona `role_catalog` eklenir)
- Modify: `services/customer-api/app/models/schemas.py:341` civarı (NetboxVizExclusionUpsert'ün ardına)
- Modify: `services/customer-api/app/main.py:134-144` (router kaydı)
- Test: `services/customer-api/tests/test_colocation_role_rule_service.py`

**Interfaces:**
- Consumes: `RoleRules`, `DEFAULT_RULES` (Task 1).
- Produces:
  - `ColocationRoleRuleService(webui, customer_service=None)`
  - `.list_rules() -> list[dict]` — `{role_id, sellable, notes, updated_by, updated_at}`
  - `.load_rules() -> RoleRules` (30 sn memo'lu)
  - `.save_rules(rules: Sequence[Mapping], *, notes=None, updated_by=None) -> RoleRules`
  - `.role_catalog() -> list[dict]` — `{role_id, role_name, rack_rows}`
  - `.invalidate_memo() -> None`
  - `get_role_rule_service(app) -> ColocationRoleRuleService` — modül düzeyi, app-scoped tekil erişimci
  - HTTP: `GET /api/v1/colocation/role-rules`, `PUT /api/v1/colocation/role-rules`
  - `shared.colocation.occupancy.role_catalog(cursor) -> list[dict]`

**Dikkat:** bu dosyalar `services/customer-api/app/` altında oluşturulur ama crm-engine imajına da kopyalanır (Global Constraints'teki tabloya bakın). İkinci bir kopya çıkarmayın.

- [ ] **Step 1: Migration'ı yaz**

`services/customer-api/migrations/webui/047_colocation_role_rule.sql`:

```sql
-- Colocation sellable rack-role rules (global -- one row per Loki rack role).
--
-- Which rack roles count as sellable colocation inventory used to be the
-- module constant NON_SELLABLE_ROLE_IDS in shared/colocation/allocation.py,
-- i.e. a deploy-time decision. Operators now own it from Administration ->
-- Integrations -> NetBox / Loki -> Colocation Configuration.
--
-- The seed below is TODAY'S SHIPPED BEHAVIOUR (commit 7cd4c9e2), so applying
-- this migration moves no number: DC13 reads 272 sellable free U before and
-- after. ON CONFLICT DO NOTHING keeps a re-run from overwriting an operator's
-- edit.
--
-- Global on purpose: no dc column. See
-- docs/superpowers/specs/2026-08-04-colocation-rack-role-config-design.md §3.

CREATE TABLE IF NOT EXISTS gui_colocation_role_rule (
    role_id    TEXT PRIMARY KEY,
    sellable   BOOLEAN NOT NULL,
    notes      TEXT,
    updated_by TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO gui_colocation_role_rule (role_id, sellable, notes, updated_by)
VALUES
    ('1', FALSE, 'NETWORK RACK - switching gear, cannot be rented out', 'migration-047'),
    ('2', TRUE,  'HOST RACK - the sellable base', 'migration-047'),
    ('3', FALSE, 'NON-STANDART RACK - allocated to a colocation customer', 'migration-047'),
    ('4', FALSE, 'CUSTOMER RACK - allocated to a colocation customer', 'migration-047')
ON CONFLICT (role_id) DO NOTHING;
```

- [ ] **Step 2: SQL modülünü yaz**

`services/customer-api/app/db/queries/colocation_config.py`:

```python
"""SQL for colocation sellable rack-role rules (webui-db)."""

LIST_ROLE_RULES = """
SELECT role_id,
       sellable,
       notes,
       updated_by,
       updated_at
FROM   gui_colocation_role_rule
ORDER BY role_id;
"""

UPSERT_ROLE_RULE = """
INSERT INTO gui_colocation_role_rule
    (role_id, sellable, notes, updated_by, updated_at)
VALUES (%s, %s, %s, %s, NOW())
ON CONFLICT (role_id) DO UPDATE SET
    sellable   = EXCLUDED.sellable,
    notes      = COALESCE(EXCLUDED.notes, gui_colocation_role_rule.notes),
    updated_by = EXCLUDED.updated_by,
    updated_at = NOW();
"""
```

- [ ] **Step 3: Rol kataloğu sorgusunu `occupancy.py`'ye ekle**

`shared/colocation/occupancy.py` dosyasının **sonuna**:

```python
# --- Loki rack role catalogue ------------------------------------------------
# The Colocation Configuration screen lists the roles that actually exist in the
# live data, so a 5th role added in Loki shows up on the screen by itself
# instead of silently joining the sellable pool as an unconfigured role.
#
# Source is discovery_loki_rack, NOT loki_racks: the loki_* timeseries stopped
# collecting on 2026-04-12 (see this module's docstring) and would show a role
# set that is nearly four months stale. discovery_loki_rack carries no
# role_name, so the display name comes from allocation.ROLE_NAMES and unknown
# ids fall back to "UNKNOWN" -- which is exactly the signal the operator needs.
ROLE_CATALOG_SQL = """
SELECT role_id::text AS role_id,
       COUNT(*)      AS rack_rows
FROM   discovery_loki_rack
WHERE  role_id IS NOT NULL
GROUP BY role_id
ORDER BY role_id
"""


def role_catalog(cursor) -> list[dict]:
    """``[{role_id, role_name, rack_rows}]`` for every role present in the data.

    role_id is cast to text for the same reason allocation.py compares it as a
    string: discovery_loki_rack.role_id is a varchar and the two sides must
    agree, or a rule keyed "4" never matches a catalogue entry of 4.

    ``rack_rows`` counts RAW rows, not de-duplicated physical racks -- it is
    only here so a role with zero live racks is visibly distinguishable from
    one that carries inventory. Do not display it as a rack count; the screen
    takes its rack/capacity/free numbers from the aggregate's role_breakdown,
    which is post-dedupe.

    Builds its dicts inline rather than through row_to_dict(): that helper maps
    tuples POSITIONALLY onto OCCUPANCY_COLUMNS, so a two-column result would
    come back labelled rack_id/rack_name.
    """
    cursor.execute(ROLE_CATALOG_SQL)
    out: list[dict] = []
    for row in cursor.fetchall() or []:
        role_key = str(row[0] or "").strip()
        if not role_key:
            continue
        out.append({
            "role_id": role_key,
            "role_name": ROLE_NAMES.get(role_key, "UNKNOWN"),
            "rack_rows": int(row[1] or 0),
        })
    return out
```

`ROLE_NAMES` bu modülde import edilmiş değil — dosyanın başındaki
`from shared.colocation.allocation import (...)` bloğuna ekleyin.

- [ ] **Step 4: Servisin testini yaz**

`services/customer-api/tests/test_colocation_role_rule_service.py`:

```python
"""Colocation rack-role rule service — webui CRUD ve DEFAULT'a düşme."""

from shared.colocation.role_rules import DEFAULT_RULES
from app.services.colocation_role_rule_service import ColocationRoleRuleService


class _FakeWebui:
    def __init__(self, rows=None, available=True):
        self.is_available = available
        self._rows = rows or []
        self.executed = []

    def run_rows(self, sql, params=None):
        return list(self._rows)

    def execute(self, sql, params=None):
        self.executed.append(params)
        return 1


def test_unavailable_webui_falls_back_to_default_rules():
    """webui kapalıyken bugünkü kural seti uygulanmalı.

    Yakaladığı bozulma: config okunamayınca boş kural seti dönerse her rol
    'kayıtsız' olur, kayıtsız rol sellable sayılır ve sellable U bir DB
    kesintisi yüzünden platform toplamına fırlar.
    """
    svc = ColocationRoleRuleService(_FakeWebui(available=False))
    assert svc.load_rules() == DEFAULT_RULES


def test_saved_rules_are_written_for_every_role_and_reload():
    """Kaydetme dört rolü de yazmalı ve sonraki okuma yeni kuralı vermeli.

    Yakaladığı bozulma: kısmi yazım (yalnız değişen rol) ekranda görülen hâl
    ile DB'deki hâli ayrıştırır; memo temizlenmezse kaydetme 30 saniye
    boyunca hiçbir şeyi değiştirmez.
    """
    webui = _FakeWebui(rows=[{"role_id": "1", "sellable": False},
                             {"role_id": "2", "sellable": True}])
    svc = ColocationRoleRuleService(webui)
    assert svc.load_rules().is_sellable("1") is False

    webui._rows = [{"role_id": "1", "sellable": True},
                   {"role_id": "2", "sellable": True}]
    rules = svc.save_rules([{"role_id": "1", "sellable": True},
                            {"role_id": "2", "sellable": True}],
                           updated_by="tester")

    assert len(webui.executed) == 2
    assert rules.is_sellable("1") is True
    assert svc.load_rules().is_sellable("1") is True
```

- [ ] **Step 5: Testi çalıştır, kırmızı olduğunu gör**

```bash
cd services/customer-api && ../../.venv/bin/python -m pytest tests/test_colocation_role_rule_service.py -q
```

Beklenen: `ModuleNotFoundError: No module named 'app.services.colocation_role_rule_service'`

- [ ] **Step 6: Servisi yaz**

`services/customer-api/app/services/colocation_role_rule_service.py`:

```python
"""Colocation sellable rack-role rules — webui-db CRUD + RoleRules loader."""
from __future__ import annotations

import logging
import time
from typing import Any, Mapping, Sequence

from shared.colocation.occupancy import role_catalog as _role_catalog
from shared.colocation.role_rules import DEFAULT_RULES, RoleRules
from app.db.queries import colocation_config as cq
from app.services.webui_db import WebuiPool

logger = logging.getLogger(__name__)

# load_rules() is called on the read path of every colocation/sellable
# request (its etag goes into the cache key), so it must not be a webui
# round-trip each time. 30s is short enough that an operator's save shows up
# on its own even if an explicit invalidate is missed, and long enough that a
# burst of requests costs one query.
_MEMO_TTL_SECONDS = 30.0


class ColocationRoleRuleService:
    def __init__(self, webui: WebuiPool, customer_service: Any = None) -> None:
        self._webui = webui
        self._svc = customer_service
        self._memo: tuple[float, RoleRules] | None = None

    @property
    def is_available(self) -> bool:
        return self._webui is not None and getattr(self._webui, "is_available", False)

    def list_rules(self) -> list[dict[str, Any]]:
        if not self.is_available:
            return []
        try:
            return self._webui.run_rows(cq.LIST_ROLE_RULES)
        except Exception as exc:  # noqa: BLE001
            logger.warning("colocation role rules load failed: %s", exc)
            return []

    def load_rules(self) -> RoleRules:
        """Current rule set, memoised for _MEMO_TTL_SECONDS.

        Returns DEFAULT_RULES when webui is unreachable or the table is empty
        -- never an empty rule set, which every consumer would read as
        "no role is configured, therefore everything is sellable".
        """
        now = time.monotonic()
        if self._memo is not None and now < self._memo[0]:
            return self._memo[1]
        if not self.is_available:
            return DEFAULT_RULES
        rules = RoleRules.from_rows(self.list_rules())
        self._memo = (now + _MEMO_TTL_SECONDS, rules)
        return rules

    def invalidate_memo(self) -> None:
        self._memo = None

    def save_rules(
        self,
        rules: Sequence[Mapping[str, Any]],
        *,
        notes: str | None = None,
        updated_by: str | None = None,
    ) -> RoleRules:
        """Write the FULL rule set (one row per role) and drop the memo.

        Full-set writes, not per-role: a partial write leaves roles the screen
        showed as "off" absent from the table, and an absent role reads back
        as sellable -- the saved state would not match what the operator saw.
        """
        if not self.is_available:
            raise RuntimeError("WebUI configuration DB not available")
        seen: set[str] = set()
        for item in rules or []:
            raw = item.get("role_id")
            key = "" if raw is None else str(raw).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            self._webui.execute(
                cq.UPSERT_ROLE_RULE,
                (key, bool(item.get("sellable")), notes, updated_by or "api"),
            )
        self.invalidate_memo()
        return self.load_rules()

    def role_catalog(self) -> list[dict[str, Any]]:
        """Live rack-role catalogue; empty list if the datalake is unreachable."""
        if self._svc is None:
            return []
        try:
            with self._svc._get_connection() as conn:
                with conn.cursor() as cur:
                    return _role_catalog(cur)
        except Exception as exc:  # noqa: BLE001
            logger.warning("loki role catalog query failed: %s", exc)
            return []


def get_role_rule_service(app) -> ColocationRoleRuleService:
    """App-scoped singleton, created on first use.

    Must be a singleton: the 30s memo lives on the instance, and
    ColocationMatchingService is built PER REQUEST
    (routers/colocation.py). A fresh rule service per request would mean a
    webui round-trip on every colocation call, which is the read path this
    memo exists to protect.
    """
    svc = getattr(app.state, "colocation_role_rules", None)
    if svc is None:
        svc = ColocationRoleRuleService(
            getattr(app.state, "webui", None), getattr(app.state, "db", None)
        )
        app.state.colocation_role_rules = svc
    return svc
```

- [ ] **Step 7: Testi çalıştır, yeşil olduğunu gör**

```bash
cd services/customer-api && ../../.venv/bin/python -m pytest tests/test_colocation_role_rule_service.py -q
```

Beklenen: `2 passed`

- [ ] **Step 8: Pydantic modellerini ekle**

`services/customer-api/app/models/schemas.py` — `NetboxVizExclusionUpsert` sınıfının hemen altına:

```python
class ColocationRoleRuleItem(BaseModel):
    role_id: str
    sellable: bool


class ColocationRoleRulesUpdate(BaseModel):
    rules: List[ColocationRoleRuleItem]
    notes: Optional[str] = None
```

`List` zaten `typing`'den import edilmiş değilse dosyanın başındaki import satırına ekleyin.

- [ ] **Step 9: Router'ı yaz**

`services/customer-api/app/routers/colocation_config.py`:

```python
"""Colocation sellable rack-role rule endpoints (webui-db)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.models.schemas import ColocationRoleRulesUpdate
from app.services.colocation_role_rule_service import (
    ColocationRoleRuleService,
    get_role_rule_service,
)

router = APIRouter()


def _service(request: Request) -> ColocationRoleRuleService:
    """Reuse the app-scoped instance so its 30s memo is shared, not per-request."""
    return get_role_rule_service(request.app)


@router.get("/colocation/role-rules", response_model=dict)
def get_role_rules(request: Request):
    svc = _service(request)
    rules = svc.load_rules()
    return {
        "rules": [
            {"role_id": rid, "sellable": flag}
            for rid, flag in sorted(rules.sellable.items())
        ],
        "catalog": svc.role_catalog(),
        "etag": rules.etag,
        # degraded=True means these numbers come from the built-in default,
        # not from the operator's saved config. The screen shows a banner and
        # disables saving rather than letting someone overwrite config they
        # cannot currently see.
        "degraded": not svc.is_available,
    }


@router.put("/colocation/role-rules", response_model=dict)
def put_role_rules(body: ColocationRoleRulesUpdate, request: Request):
    svc = _service(request)
    if not svc.is_available:
        raise HTTPException(status_code=503, detail="WebUI configuration DB not available")
    if not body.rules:
        raise HTTPException(status_code=400, detail="rules must not be empty")
    rules = svc.save_rules(
        [r.model_dump() for r in body.rules],
        notes=body.notes,
        updated_by="settings-ui",
    )
    return {"status": "ok", "etag": rules.etag}
```

- [ ] **Step 10: Router'ı kaydet**

`services/customer-api/app/main.py` — import satırına `colocation_config` ekleyin (`netbox_config`'in yanına), ve `colocation.router` kaydının hemen ardına:

```python
app.include_router(
    colocation_config.router,
    prefix="/api/v1",
    tags=["colocation-config"],
    dependencies=[Depends(verify_api_user)],
)
```

- [ ] **Step 11: customer-api test paketinin tamamını çalıştır**

```bash
cd services/customer-api && ../../.venv/bin/python -m pytest tests/ -q 2>&1 | tail -5
```

Beklenen: yeni 2 test PASS; **mevcut 6 pre-existing failure dışında yeni kırık yok** (baseline: bu daldaki `main` ile aynı sayı).

- [ ] **Step 12: Commit ve push**

```bash
git add services/customer-api/migrations/webui/047_colocation_role_rule.sql \
        services/customer-api/app/db/queries/colocation_config.py \
        services/customer-api/app/services/colocation_role_rule_service.py \
        services/customer-api/app/routers/colocation_config.py \
        services/customer-api/app/models/schemas.py \
        services/customer-api/app/main.py \
        services/customer-api/tests/test_colocation_role_rule_service.py \
        shared/colocation/occupancy.py
git commit -m "feat(customer-api): colocation rack rolü kural tablosu, servisi ve API uçları"
git push origin worktree-sellable-u-role-filter
```

---

### Task 4: Kuralı iki tüketiciye bağla ve etag'i cache anahtarına koy

**Files:**
- Modify: `services/customer-api/app/services/sellable_service.py:1589-1615` (`_query_colocation_totals`), `:4113-4122` (`_result_cache_key`)
- Modify: `services/customer-api/app/services/colocation_matching_service.py:118-208` (`_fetch_colocation`, `get_colocation`)
- Modify: `services/customer-api/app/routers/colocation.py:11-14` (`_colocation_service`)
- Modify: `services/crm-engine/app/main.py:201-209` (`SellableService(...)` kurulumu)
- Test: `services/customer-api/tests/test_colocation_rules_wiring.py`

**Interfaces:**
- Consumes: `ColocationRoleRuleService.load_rules()` (Task 3), `sellable_rack_totals(rows, rules)` / `aggregate_rack_allocations(rows, rules)` (Task 2).
- Produces: cache anahtarları `colocation:{dc}:{etag}` ve `sellable:panels:{dc}:{family}:{clusters}:{etag}`.

- [ ] **Step 1: Testi yaz**

`services/customer-api/tests/test_colocation_rules_wiring.py`:

```python
"""Kural setinin colocation cache anahtarına ve hesabına bağlanması."""

from shared.colocation.role_rules import RoleRules
from app.services.colocation_matching_service import ColocationMatchingService
from app.services.sellable_service import SellableService


def test_colocation_cache_key_carries_the_rule_etag(monkeypatch):
    """İki farklı kural seti aynı cache anahtarını paylaşmamalı.

    Yakaladığı bozulma: etag anahtarda değilse operatör ayarı değiştirir,
    Redis'teki eski payload aynı anahtar altında durmaya devam eder ve
    6 saat boyunca eski sayı servis edilir.
    """
    a = RoleRules({"1": False, "2": True})
    b = RoleRules({"1": True, "2": True})
    assert ColocationMatchingService._cache_key("DC13", a) != \
           ColocationMatchingService._cache_key("DC13", b)
    assert ColocationMatchingService._cache_key("DC13", a).startswith("colocation:DC13:")


def test_sellable_result_cache_key_carries_the_rule_etag():
    """sellable:panels anahtarı da kural setine bağlı olmalı.

    Yakaladığı bozulma: colocation kartı yeni sayıyı gösterirken CRM
    sellable paneli eskisini gösterir -- iki ekran birbiriyle çelişir.
    """
    a = RoleRules({"1": False, "2": True})
    b = RoleRules({"1": True, "2": True})
    key_a = SellableService._result_cache_key("DC13", None, None, rules_etag=a.etag)
    key_b = SellableService._result_cache_key("DC13", None, None, rules_etag=b.etag)
    assert key_a != key_b
    assert key_a.startswith("sellable:panels:DC13:")
```

- [ ] **Step 2: Testi çalıştır, kırmızı olduğunu gör**

```bash
cd services/customer-api && ../../.venv/bin/python -m pytest tests/test_colocation_rules_wiring.py -q
```

Beklenen: `AttributeError: type object 'ColocationMatchingService' has no attribute '_cache_key'`

- [ ] **Step 3: `colocation_matching_service.py`'yi değiştir**

Import ekle:

```python
from shared.colocation.role_rules import DEFAULT_RULES, RoleRules
from app.services.colocation_role_rule_service import ColocationRoleRuleService
```

`__init__`'e kural servisi ekle:

```python
    def __init__(self, customer_service, webui, role_rules_service=None):
        self._svc = customer_service
        self._webui = webui
        # Injected by the router from app.state so the 30s memo survives across
        # requests -- this service itself is built PER REQUEST, so a memo owned
        # here would be born empty on every call.
        self._rules_svc = role_rules_service or ColocationRoleRuleService(
            webui, customer_service
        )
```

Cache anahtarı üreticisini ekle:

```python
    @staticmethod
    def _cache_key(dc_code: str, rules: RoleRules) -> str:
        """Cache key including the rule-set etag.

        The etag is in the KEY, not just flushed on write, because
        cache_backend.cache_get backfills Redis from a worker's in-process
        memory tier with nx=True: one worker's flush can be undone by another
        worker's stale copy. A key that no longer exists is never asked for,
        so it can never be resurrected.
        """
        return f"colocation:{dc_code}:{rules.etag}"
```

`_fetch_colocation` (satır 118) imzasına `rules` ekle. Gövdede **tek** satır değişir — satır 147'deki `aggregate_rack_allocations` çağrısı; geri kalanına dokunma:

```python
    # satır 118 — imza
    def _fetch_colocation(self, dc_code: str, rules: RoleRules = DEFAULT_RULES) -> dict:

    # satır 147 — tek değişen gövde satırı
        allocation = aggregate_rack_allocations(rows, rules)
```

`get_colocation`'ı değiştir:

```python
    def get_colocation(self, dc_code: str) -> dict:
        rules = self._rules_svc.load_rules()
        cache_key = self._cache_key(dc_code, rules)
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val
        try:
            return cache.run_singleflight(
                cache_key,
                lambda: self._fetch_colocation(dc_code, rules),
                ttl=_CACHE_TTL_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("colocation occupancy query failed for %s: %s", dc_code, exc)
            return self._empty_payload()
```

`_CACHE_TTL_SECONDS` yorumunun altına ekle:

```python
# The cache key now carries the rack-role rule etag (see _cache_key), so a
# config change moves every DC onto fresh keys instead of waiting out this TTL.
```

- [ ] **Step 4: `sellable_service.py`'yi değiştir**

Import ekle:

```python
from shared.colocation.role_rules import DEFAULT_RULES, RoleRules
```

`__init__`'e kural servisi parametresi ekle (varsayılan `None`, `main.py` enjekte eder):

```python
        role_rules_service=None,
```

```python
        self._rules_svc = role_rules_service
```

Kural yükleyici yardımcı:

```python
    def _role_rules(self) -> RoleRules:
        """Operator-configured sellable rack roles, or the built-in default.

        Never raises: a colocation panel must still compute if the config
        service is missing, and DEFAULT_RULES is exactly today's behaviour.
        """
        if self._rules_svc is None:
            return DEFAULT_RULES
        try:
            return self._rules_svc.load_rules()
        except Exception:  # noqa: BLE001
            logger.warning("role rules load failed; using defaults", exc_info=True)
            return DEFAULT_RULES
```

`_query_colocation_totals`'ın son satırını değiştir:

```python
        return coloc_alloc.sellable_rack_totals(rows, self._role_rules())
```

`_result_cache_key`'e etag parametresi ekle:

```python
    @staticmethod
    def _result_cache_key(
        dc_code: str,
        selected_clusters: list[str] | None,
        family: str | None,
        rules_etag: str = "",
    ) -> str:
        clusters_part = ""
        if selected_clusters:
            clusters_part = ",".join(sorted(c for c in selected_clusters if c))
        base = f"sellable:panels:{dc_code or '*'}:{family or '*'}:{clusters_part}"
        # Rack-role rules change what dc_hosting_u totals mean, so they are part
        # of the key's identity -- see ColocationMatchingService._cache_key for
        # why an etag beats flushing alone.
        return f"{base}:{rules_etag}" if rules_etag else base
```

`_result_cache_key` çağrılarını bulun ve `rules_etag=self._role_rules().etag` geçirin:

```bash
grep -n "_result_cache_key(" services/customer-api/app/services/sellable_service.py
```

`invalidate_result_cache`'in `pattern`'ı `sellable:panels:{dc}:*` olduğu için etag'li anahtarları da kapsar; **değiştirmeyin**.

- [ ] **Step 5: İki kurulum noktasını bağla**

**(a) customer-api — `services/customer-api/app/routers/colocation.py`:**

```python
from app.services.colocation_role_rule_service import get_role_rule_service


def _colocation_service(request: Request) -> ColocationMatchingService:
    svc = request.app.state.db
    webui = request.app.state.webui
    return ColocationMatchingService(
        customer_service=svc,
        webui=webui,
        # App-scoped, not per-request: this factory runs on every colocation
        # call and the rule service owns a 30s memo.
        role_rules_service=get_role_rule_service(request.app),
    )
```

**(b) crm-engine — `services/crm-engine/app/main.py:201`:** `SellableService(...)` çağrısına parametre ekleyin. Import satırını da ekleyin (`from app.services.colocation_role_rule_service import ColocationRoleRuleService`).

```python
    sellable_svc = SellableService(
        customer_service=svc,
        webui=webui,
        config_service=config_svc,
        currency_service=currency_svc,
        tagging_service=tagging_svc,
        datacenter_redis=dc_redis,
        datacenter_api_url=_DATACENTER_API_URL,
        crm_redis=crm_redis,
        # Same webui table customer-api writes; crm-engine picks up an operator's
        # change within the service's 30s memo window. There is no cross-service
        # invalidation call -- the rule etag in the cache key does that work.
        role_rules_service=ColocationRoleRuleService(webui, svc),
    )
```

- [ ] **Step 6: Yazma sonrası cache invalidation'ı router'a ekle**

`services/customer-api/app/routers/colocation_config.py` içindeki `put_role_rules`'a, `save_rules` çağrısının ardına:

```python
    # Correctness comes from the etag in the cache key; this flush is only for
    # immediacy, so the colocation card moves now instead of after its 6h TTL.
    #
    # Only customer-api's OWN cache is flushed here. The sellable panel's cache
    # lives in the crm-engine process on a different Redis DB and is
    # unreachable from this endpoint -- it corrects itself within 30s when
    # crm-engine's memo expires and its etag changes. Do not add an HTTP call
    # to crm-engine for this.
    try:
        from app.services import cache_service as cache

        cache.delete_prefix("colocation:")
    except Exception:  # noqa: BLE001
        logger.warning("cache invalidation after role-rule save failed", exc_info=True)
    return {"status": "ok", "etag": rules.etag}
```

Dosyanın başına `import logging` ve `logger = logging.getLogger(__name__)` ekleyin.

- [ ] **Step 7: Testleri çalıştır**

```bash
cd services/customer-api && ../../.venv/bin/python -m pytest tests/ -q 2>&1 | tail -5
```

Beklenen: yeni 2 test PASS, baseline dışında yeni kırık yok.

- [ ] **Step 8: Commit ve push**

```bash
git add services/customer-api/app/services/sellable_service.py \
        services/customer-api/app/services/colocation_matching_service.py \
        services/customer-api/app/routers/colocation.py \
        services/customer-api/app/routers/colocation_config.py \
        services/crm-engine/app/main.py \
        services/customer-api/tests/test_colocation_rules_wiring.py
git commit -m "feat(customer-api): sellable ve colocation hesaplarını kural setine bağla, etag'i cache anahtarına koy"
git push origin worktree-sellable-u-role-filter
```

---

### Task 5: GUI api_client fonksiyonları

**Files:**
- Modify: `src/services/api_client.py:3129` civarı (`_invalidate_netbox_viz_caches`'in ardına)
- Test: `tests/test_api_client_colocation_role_rules.py`

**Interfaces:**
- Consumes: `GET/PUT /api/v1/colocation/role-rules` (Task 3).
- Produces:
  - `get_colocation_role_rules() -> dict` — `{rules, catalog, etag, degraded}`
  - `put_colocation_role_rules(rules: list[dict], notes: str | None = None) -> dict`

- [ ] **Step 1: Testi yaz**

`tests/test_api_client_colocation_role_rules.py`:

```python
"""api_client — colocation rack rolü kuralları."""

from unittest.mock import patch

from src.services import api_client as api


def test_put_invalidates_the_colocation_and_sellable_caches():
    """Kaydetme, etkilenen GUI cache prefix'lerini temizlemeli.

    Yakaladığı bozulma: prefix temizlenmezse operatör Kaydet'e basar, DC
    Colocation kartı ve CRM sellable paneli GUI cache'inden eski sayıyı
    servis etmeye devam eder -- customer-api tarafı doğru olsa bile.
    """
    cleared: list[str] = []
    with patch.object(api, "_put_json", return_value={"status": "ok", "etag": "abcd1234"}), \
         patch.object(api._api_response_cache, "delete_prefix", side_effect=cleared.append):
        out = api.put_colocation_role_rules([{"role_id": "1", "sellable": True}])

    assert out["etag"] == "abcd1234"
    assert "api:colocation_role_rules" in cleared
    assert any(p.startswith("api:colocation") for p in cleared)
    assert any(p.startswith("api:sellable_summary") for p in cleared)
```

- [ ] **Step 2: Testi çalıştır, kırmızı olduğunu gör**

```bash
.venv/bin/python -m pytest tests/test_api_client_colocation_role_rules.py -q
```

Beklenen: `AttributeError: module 'src.services.api_client' has no attribute 'put_colocation_role_rules'`

- [ ] **Step 3: Fonksiyonları yaz**

`src/services/api_client.py` — `_invalidate_netbox_viz_caches` fonksiyonunun hemen ardına:

```python
# ---------------------------------------------------------------------------
# Colocation sellable rack-role rules
# ---------------------------------------------------------------------------


def get_colocation_role_rules() -> dict[str, Any]:
    def fetch() -> dict[str, Any]:
        data = _get_json(_get_client_cust(), "/api/v1/colocation/role-rules")
        return data if isinstance(data, dict) else {}

    return _api_cache_get_with_stale("api:colocation_role_rules", fetch, {})


def put_colocation_role_rules(
    rules: list[dict[str, Any]], notes: Optional[str] = None
) -> dict[str, Any]:
    body: dict[str, Any] = {"rules": rules}
    if notes is not None:
        body["notes"] = notes
    out = _put_json(_get_client_cust(), "/api/v1/colocation/role-rules", body)
    _invalidate_colocation_rule_caches()
    return out if isinstance(out, dict) else {}


def _invalidate_colocation_rule_caches() -> None:
    """Drop every GUI-cached number the rack-role rules feed.

    The customer-api side is already correct on its own (the rule etag is part
    of its cache keys), but the GUI keeps its own response cache in front of
    it -- without this the screen keeps serving the pre-save number.
    """
    for prefix in (
        "api:colocation_role_rules",
        "api:colocation",
        "api:dc_racks_",
        "api:sellable_summary:",
        "api:sellable_by_panel:",
        "api:sellable_by_family:",
    ):
        try:
            _api_response_cache.delete_prefix(prefix)
        except Exception:
            pass
```

`api:dc_racks_` / `api:colocation` prefix adlarını doğrulayın:

```bash
grep -n "api:colocation\|api:dc_racks" src/services/api_client.py
```

Gerçek prefix farklıysa listeyi ona göre düzeltin — uydurmayın.

- [ ] **Step 4: Testi çalıştır, yeşil olduğunu gör**

```bash
.venv/bin/python -m pytest tests/test_api_client_colocation_role_rules.py tests/test_api_client_colocation.py -q
```

Beklenen: hepsi PASS.

- [ ] **Step 5: Commit ve push**

```bash
git add src/services/api_client.py tests/test_api_client_colocation_role_rules.py
git commit -m "feat(gui): colocation rack rolü kuralları için api_client fonksiyonları"
git push origin worktree-sellable-u-role-filter
```

---

### Task 6: Colocation Configuration sayfası, navigasyon ve yetki

**Files:**
- Create: `src/utils/colocation_config_ui.py`
- Create: `src/pages/settings/integrations/colocation_config.py`
- Create: `src/pages/settings/integrations/colocation_config_callbacks.py`
- Modify: `src/pages/settings/shell.py:33` (import), `:57-65` (`INT_TABS` etiketi), `:79` sonrası (`NETBOX_TABS`), `:153-156` (`_PAGE_BUILDERS`), `:488-519` (`_sub_nav`), `:560-564` (`_breadcrumb`), `:181-194` (`has_any_settings_access`)
- Modify: `src/auth/permission_catalog.py:352-358`, `src/auth/permission_service.py:137-138`
- Modify: `app.py:199` civarı
- Test: `tests/test_colocation_config_page.py`

**Interfaces:**
- Consumes: `api.get_colocation_role_rules()`, `api.put_colocation_role_rules()` (Task 5); `api.get_colocation(dc_code)` — `role_breakdown` için mevcut fonksiyon.
- Produces:
  - `src/utils/colocation_config_ui.py`: `merge_rules_with_catalog(rules, catalog, breakdown) -> list[dict]`, `preview_sellable_free_u(merged, overrides) -> int`, `build_role_table(merged) -> dmc.Table`
  - `page:settings_colocation_config` permission kodu
  - `/administration/integrations/netbox/colocation` route'u

- [ ] **Step 1: Saf yardımcıların testini yaz**

`tests/test_colocation_config_page.py`:

```python
"""Colocation Configuration sayfası — birleştirme, önizleme, layout, RBAC."""

from unittest.mock import patch

from src.pages.settings import shell
from src.pages.settings.integrations import colocation_config as page
from src.utils.colocation_config_ui import (
    merge_rules_with_catalog,
    preview_sellable_free_u,
)

CATALOG = [
    {"role_id": "1", "role_name": "NETWORK RACK"},
    {"role_id": "2", "role_name": "HOST RACK"},
    {"role_id": "5", "role_name": "YENI ROL"},
]
RULES = [
    {"role_id": "1", "sellable": False},
    {"role_id": "2", "sellable": True},
]
BREAKDOWN = [
    {"role_id": "1", "rack_count": 42, "capacity_u": 1930, "free_u": 900},
    {"role_id": "2", "rack_count": 139, "capacity_u": 6408, "free_u": 3503},
]


def _walk(node):
    yield node
    children = getattr(node, "children", None)
    if children is None:
        return
    if not isinstance(children, (list, tuple)):
        children = [children]
    for c in children:
        yield from _walk(c)


def _ids(layout):
    return [getattr(n, "id", None) for n in _walk(layout) if getattr(n, "id", None)]


def test_role_without_a_rule_is_shown_as_new_and_sellable():
    """Katalogda olup kuralı olmayan rol, sellable ve 'yeni' işaretli gelmeli.

    Yakaladığı bozulma: Loki'ye 5. rol eklendiğinde ekran onu ya hiç
    göstermez (operatör sellable U'nun neden büyüdüğünü bulamaz) ya da
    hesaptan farklı olarak 'kapalı' gösterir -- ekran ile motor ayrışır.
    """
    merged = merge_rules_with_catalog(RULES, CATALOG, BREAKDOWN)
    new_role = next(r for r in merged if r["role_id"] == "5")
    assert new_role["sellable"] is True
    assert new_role["is_new"] is True
    assert new_role["free_u"] == 0


def test_preview_reflects_pending_switch_state_not_saved_state():
    """Önizleme, kaydedilmemiş switch durumuna göre hesaplamalı.

    Yakaladığı bozulma: önizleme kaydedilmiş kuralı gösterirse operatör
    'kaydedince ne olacak' sorusunun cevabını göremez; NETWORK'ü açıp
    3.503 görmeye devam eder, sonra kaydedip 4.403 ile karşılaşır.
    """
    merged = merge_rules_with_catalog(RULES, CATALOG, BREAKDOWN)
    assert preview_sellable_free_u(merged, {}) == 3503
    assert preview_sellable_free_u(merged, {"1": True}) == 4403
    assert preview_sellable_free_u(merged, {"2": False}) == 0


def test_layout_builds_with_switch_per_catalog_role():
    """Sayfa, katalogdaki her rol için bir switch üretmeli.

    Yakaladığı bozulma: layout kayıtlı kural listesi üzerinden kurulursa
    kuralı olmayan rol ekrana hiç gelmez ve ayarlanamaz.
    """
    payload = {"rules": RULES, "catalog": CATALOG, "etag": "abcd1234", "degraded": False}
    with patch.object(page.api, "get_colocation_role_rules", return_value=payload), \
         patch.object(page.api, "get_colocation", return_value={"aggregate": {"role_breakdown": BREAKDOWN}}):
        layout = page.build_layout()

    ids = _ids(layout)
    for role_id in ("1", "2", "5"):
        assert {"type": "coloc-cfg-switch", "role": role_id} in ids
    assert "coloc-cfg-save" in ids


def test_page_is_denied_by_its_own_permission_code():
    """Administration'a erişebilen ama BU kodu olmayan kullanıcı reddedilmeli.

    Yakaladığı bozulma: sayfa _PAGE_BUILDERS'a eklenip kendi permission
    koduna bağlanmazsa, sellable U'yu platform genelinde değiştirebilen bir
    ekran Administration'a erişebilen herkese açılır.

    can_view SADECE yeni kod için False döner; tümden False yapmak testi
    tautolojik yapardı, çünkü has_any_settings_access zaten daha kapıda
    reddeder ve kod hiç bağlanmasa da test geçerdi.
    """
    def _can_view(_user_id, code):
        return code != "page:settings_colocation_config"

    with patch("src.auth.permission_service.can_view", side_effect=_can_view):
        out = shell.build_settings_page(
            "/administration/integrations/netbox/colocation", user_id=999
        )
    assert "denied" in str(out).lower()


def test_netbox_sub_nav_lists_both_tabs():
    """NetBox/Loki altında iki sekme de görünmeli.

    Yakaladığı bozulma: sub-nav bloğu eklenmezse yeni sayfaya hiçbir yerden
    link olmaz, yalnızca URL'i bilen ulaşır.
    """
    with patch("src.auth.permission_service.can_view", return_value=True):
        nav = shell._sub_nav(1, "/administration/integrations/netbox/colocation")
    text = str(nav)
    assert "Filters" in text
    assert "Colocation Configuration" in text
```

- [ ] **Step 2: Testi çalıştır, kırmızı olduğunu gör**

```bash
.venv/bin/python -m pytest tests/test_colocation_config_page.py -q
```

Beklenen: `ModuleNotFoundError: No module named 'src.utils.colocation_config_ui'`

- [ ] **Step 3: Saf yardımcıları yaz**

`src/utils/colocation_config_ui.py`:

```python
"""Colocation Configuration ekranı için saf yardımcılar (Dash callback'i yok)."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import dash_mantine_components as dmc
from dash import html


def merge_rules_with_catalog(
    rules: Sequence[Mapping[str, Any]] | None,
    catalog: Sequence[Mapping[str, Any]] | None,
    breakdown: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Katalog + kayıtlı kural + canlı rack sayılarını tek satır listesine indir.

    Katalog otoritedir: kuralı olmayan bir rol de listelenir ve ``sellable``
    True + ``is_new`` True ile gelir -- motorun kayıtsız rolü sellable sayma
    kuralının ekrandaki karşılığı. Ters yönde (kuralı olup katalogda olmayan
    rol) satır yine gösterilir, aksi hâlde silinemeyen görünmez bir kural
    kalırdı.
    """
    by_rule = {str(r.get("role_id")).strip(): bool(r.get("sellable")) for r in rules or []}
    by_break = {str(b.get("role_id")).strip(): b for b in breakdown or []}
    names = {str(c.get("role_id")).strip(): (c.get("role_name") or "") for c in catalog or []}

    out: list[dict[str, Any]] = []
    for role_id in sorted(set(names) | set(by_rule)):
        stats = by_break.get(role_id) or {}
        out.append({
            "role_id": role_id,
            "role_name": names.get(role_id) or "UNKNOWN",
            "sellable": by_rule.get(role_id, True),
            "is_new": role_id not in by_rule,
            "rack_count": int(stats.get("rack_count") or 0),
            "capacity_u": int(stats.get("capacity_u") or 0),
            "free_u": int(stats.get("free_u") or 0),
        })
    return out


def preview_sellable_free_u(
    merged: Sequence[Mapping[str, Any]],
    overrides: Mapping[str, bool] | None = None,
) -> int:
    """Verilen switch durumuyla sellable free U ne olurdu?

    ``overrides`` kaydedilmemiş ekran durumudur; boşsa kayıtlı kural geçerli.
    """
    ov = overrides or {}
    total = 0
    for row in merged:
        role_id = str(row.get("role_id"))
        sellable = ov.get(role_id, bool(row.get("sellable")))
        if sellable:
            total += int(row.get("free_u") or 0)
    return total


def build_role_table(merged: Sequence[Mapping[str, Any]]) -> dmc.Table:
    """Rol tablosu; her satırda pattern-matching id taşıyan bir Switch."""
    head = html.Thead(html.Tr([
        html.Th("Role"), html.Th("Racks"), html.Th("Capacity U"),
        html.Th("Free U"), html.Th("Sellable?"),
    ]))
    rows = []
    for row in merged:
        label = f"{row['role_name']} ({row['role_id']})"
        cells = [
            html.Td(dmc.Group(gap=6, children=[
                dmc.Text(label, size="sm"),
                dmc.Badge("yeni — karar verilmedi", color="orange", variant="light", size="xs")
                if row.get("is_new") else None,
            ])),
            html.Td(f"{row['rack_count']:,}".replace(",", ".")),
            html.Td(f"{row['capacity_u']:,}".replace(",", ".")),
            html.Td(f"{row['free_u']:,}".replace(",", ".")),
            html.Td(dmc.Switch(
                id={"type": "coloc-cfg-switch", "role": row["role_id"]},
                checked=bool(row["sellable"]),
                size="sm",
                color="indigo",
            )),
        ]
        rows.append(html.Tr(cells))
    return dmc.Table(children=[head, html.Tbody(rows)], striped=True, highlightOnHover=True)
```

- [ ] **Step 4: Sayfayı yaz**

`src/pages/settings/integrations/colocation_config.py`:

```python
"""Integrations — Colocation Configuration (gui_colocation_role_rule).

Hangi Loki rack rolünün sellable colocation U hesabına gireceğini operatör
buradan ayarlar. Ayar GLOBAL'dir; DC bazlı istisna kapsam dışı (spec §3).
"""

from __future__ import annotations

from dash import dcc, html
import dash_mantine_components as dmc
from dash_iconify import DashIconify

from src.services import api_client as api
from src.utils.colocation_config_ui import (
    build_role_table,
    merge_rules_with_catalog,
    preview_sellable_free_u,
)
from src.utils.ui_tokens import card_style, section_header, settings_page_shell

# Roles that also mean "allocated to a colocation customer"
# (shared.colocation.allocation.COLOCATION_ROLE_IDS). Making one of these
# sellable double-counts the same U as both allocated and for sale, which is
# the bug fixed in commit 7cd4c9e2 -- so the save path warns first.
COLOCATION_ROLE_IDS = ("3", "4")


def _impact_card() -> dmc.Alert:
    return dmc.Alert(
        color="indigo",
        variant="light",
        icon=DashIconify(icon="solar:info-circle-bold-duotone", width=20),
        title="Bu ayar neyi değiştirir?",
        children=dmc.Stack(gap=4, children=[
            dmc.Text("• DC Colocation kartındaki Sellable Free U ve TL potansiyeli", size="sm"),
            dmc.Text("• CRM Sellable Potential panelindeki dc_hosting_u", size="sm"),
            dmc.Text(
                "Fiziksel Total / Used / Free U tile'ları ETKİLENMEZ — onlar "
                "kabinlerin fiziksel gerçeği, satılabilirlik değil.",
                size="sm", fw=600,
            ),
        ]),
        mb="md",
    )


def build_layout(search: str | None = None) -> html.Div:
    _ = search
    payload = api.get_colocation_role_rules() or {}
    coloc = api.get_colocation("*") or {}
    breakdown = (coloc.get("aggregate") or {}).get("role_breakdown") or []
    merged = merge_rules_with_catalog(
        payload.get("rules"), payload.get("catalog"), breakdown
    )
    degraded = bool(payload.get("degraded"))
    current = preview_sellable_free_u(merged, {})

    banner = dmc.Alert(
        "Ayar veritabanına ulaşılamıyor. Gösterilen kurallar yerleşik "
        "varsayılan, kaydedilmiş ayar değil — kaydetme kapalı.",
        color="red", variant="light", mb="md",
    ) if degraded else None

    return html.Div(settings_page_shell([
        dcc.Store(id="coloc-cfg-store", data={"merged": merged, "etag": payload.get("etag")}),
        section_header(
            "Colocation Configuration",
            "Sellable colocation U hesabına hangi rack rolleri girsin? "
            "Ayar platform genelinde geçerlidir.",
            icon="solar:server-square-cloud-bold-duotone",
        ),
        banner if banner else html.Div(),
        _impact_card(),
        dmc.Paper(
            children=[
                html.Div(id="coloc-cfg-table", children=build_role_table(merged)),
                dmc.Group(justify="space-between", align="center", mt="md", children=[
                    dmc.Text(id="coloc-cfg-preview", size="sm", fw=600,
                             children=f"Sellable free U: {current:,}".replace(",", ".")),
                    dmc.Button(
                        "Kaydet",
                        id="coloc-cfg-save",
                        disabled=degraded,
                        variant="gradient",
                        gradient={"from": "indigo", "to": "violet", "deg": 105},
                        leftSection=DashIconify(icon="solar:diskette-bold-duotone", width=18),
                    ),
                ]),
                html.Div(id="coloc-cfg-msg", style={"marginTop": "8px"}),
            ],
            **card_style(),
        ),
        dmc.Modal(
            id="coloc-cfg-confirm",
            title="Emin misiniz?",
            opened=False,
            children=[
                dmc.Text(id="coloc-cfg-confirm-body", size="sm"),
                dmc.Group(justify="flex-end", gap="sm", mt="md", children=[
                    dmc.Button("Vazgeç", id="coloc-cfg-confirm-cancel",
                               variant="subtle", color="gray"),
                    dmc.Button("Yine de kaydet", id="coloc-cfg-confirm-ok", color="red"),
                ]),
            ],
        ),
    ]))
```

- [ ] **Step 5: Callback'leri yaz**

`src/pages/settings/integrations/colocation_config_callbacks.py`:

```python
"""Dash callbacks for the Colocation Configuration settings page."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, callback, ctx, no_update
from dash.exceptions import PreventUpdate

from src.pages.settings.integrations.colocation_config import COLOCATION_ROLE_IDS
from src.services import api_client as api
from src.utils.colocation_config_ui import preview_sellable_free_u


def _overrides(ids, values) -> dict[str, bool]:
    return {str(i["role"]): bool(v) for i, v in zip(ids or [], values or [])}


def _fmt(n: int) -> str:
    return f"{n:,}".replace(",", ".")


@callback(
    Output("coloc-cfg-preview", "children"),
    Input({"type": "coloc-cfg-switch", "role": ALL}, "checked"),
    State({"type": "coloc-cfg-switch", "role": ALL}, "id"),
    State("coloc-cfg-store", "data"),
    prevent_initial_call=True,
)
def preview(values, ids, store):
    merged = (store or {}).get("merged") or []
    ov = _overrides(ids, values)
    saved = preview_sellable_free_u(merged, {})
    pending = preview_sellable_free_u(merged, ov)
    if pending == saved:
        return f"Sellable free U: {_fmt(saved)}"
    return f"Sellable free U: {_fmt(saved)}  →  kaydedince: {_fmt(pending)}"


@callback(
    Output("coloc-cfg-confirm", "opened"),
    Output("coloc-cfg-confirm-body", "children"),
    Output("coloc-cfg-msg", "children"),
    Input("coloc-cfg-save", "n_clicks"),
    State({"type": "coloc-cfg-switch", "role": ALL}, "checked"),
    State({"type": "coloc-cfg-switch", "role": ALL}, "id"),
    State("coloc-cfg-store", "data"),
    prevent_initial_call=True,
)
def guard(n_clicks, values, ids, store):
    """İki riskli kombinasyonda önce onay modalı aç, aksi hâlde doğrudan kaydet."""
    if not n_clicks:
        raise PreventUpdate
    merged = (store or {}).get("merged") or []
    ov = _overrides(ids, values)

    newly_sellable_colocation = [
        r for r in COLOCATION_ROLE_IDS
        if ov.get(r) and not next((m["sellable"] for m in merged if m["role_id"] == r), False)
    ]
    if newly_sellable_colocation:
        delta = sum(
            int(m.get("free_u") or 0) for m in merged
            if m["role_id"] in newly_sellable_colocation
        )
        return True, (
            "Bu rol müşteriye tahsisli kabinleri işaretliyor. Sellable yaparsan "
            f"aynı U hem tahsisli hem satılabilir sayılacak (+{_fmt(delta)} U)."
        ), no_update

    if not any(ov.values()):
        return True, (
            "Bütün roller hariç tutuluyor. Sellable U platform genelinde 0 olacak, "
            "TL potansiyeli sıfırlanacak."
        ), no_update

    return False, "", _save(ov, merged)


@callback(
    Output("coloc-cfg-msg", "children", allow_duplicate=True),
    Output("coloc-cfg-confirm", "opened", allow_duplicate=True),
    Input("coloc-cfg-confirm-ok", "n_clicks"),
    State({"type": "coloc-cfg-switch", "role": ALL}, "checked"),
    State({"type": "coloc-cfg-switch", "role": ALL}, "id"),
    State("coloc-cfg-store", "data"),
    prevent_initial_call=True,
)
def confirm_save(n_clicks, values, ids, store):
    if not n_clicks:
        raise PreventUpdate
    merged = (store or {}).get("merged") or []
    return _save(_overrides(ids, values), merged), False


@callback(
    Output("coloc-cfg-confirm", "opened", allow_duplicate=True),
    Input("coloc-cfg-confirm-cancel", "n_clicks"),
    prevent_initial_call=True,
)
def cancel(n_clicks):
    if not n_clicks:
        raise PreventUpdate
    return False


def _save(overrides: dict[str, bool], merged: list[dict]):
    """Tam kural setini yaz. Kısmi yazım ekran ile DB'yi ayrıştırır."""
    rules = [
        {"role_id": m["role_id"], "sellable": overrides.get(m["role_id"], bool(m["sellable"]))}
        for m in merged
    ]
    try:
        api.put_colocation_role_rules(rules)
    except Exception as exc:  # noqa: BLE001
        return dmc.Alert(f"Kaydedilemedi: {exc}", color="red", variant="light")
    return dmc.Alert(
        "Kaydedildi. Colocation kartı ve Sellable paneli yeni kurala göre hesaplanacak.",
        color="green", variant="light",
    )
```

- [ ] **Step 6: `shell.py`'yi güncelle**

Import ekle (satır 33 civarı):

```python
from src.pages.settings.integrations import colocation_config as colocation_config_page
```

`INT_TABS` içindeki NetBox satırının etiketi zaten "NetBox / Loki" — **değiştirmeyin**.

`HMDL_TABS`'in ardına ekleyin:

```python
NETBOX_TABS: list[tuple[str, str, str]] = [
    (f"{_A}/integrations/netbox/visualization", "Filters", "page:settings_netbox_visualization"),
    (f"{_A}/integrations/netbox/colocation", "Colocation Configuration", "page:settings_colocation_config"),
]
```

`_PAGE_BUILDERS`'a ekleyin:

```python
    f"{_A}/integrations/netbox/colocation": (
        "page:settings_colocation_config",
        colocation_config_page.build_layout,
    ),
```

`has_any_settings_access` içindeki `codes` listesine `+ [c for _, _, c in NETBOX_TABS]` ekleyin.

`_sub_nav`'da HMDL bloğunun ardına (satır 519 civarı, `return html.Div(children=blocks)`'dan önce):

```python
        if current_path.startswith(f"{_A}/integrations/netbox"):
            nbx_links = []
            for href, label, code in NETBOX_TABS:
                if not can_view(user_id, code):
                    continue
                active = current_path.rstrip("/") == href.rstrip("/")
                nbx_links.append(
                    dmc.Anchor(
                        dmc.Button(
                            label,
                            variant="subtle" if not active else "light",
                            color="indigo",
                            size="xs",
                            style={
                                "borderBottom": "2px solid #552cf8" if active else "2px solid transparent",
                                "borderRadius": 0,
                            },
                        ),
                        href=href,
                        underline=False,
                    )
                )
            if nbx_links:
                blocks.append(
                    html.Div(
                        style={"borderBottom": "1px solid #eef1f4", "paddingBottom": "8px", "marginBottom": "16px"},
                        children=[dmc.Group(gap="xs", children=nbx_links)],
                    )
                )
```

`_breadcrumb`'ın integrations dalına HMDL satırının ardına:

```python
        if current_path.startswith(f"{_A}/integrations/netbox"):
            return "Administration › Integrations › NetBox / Loki"
```

- [ ] **Step 7: Yetkiyi tanımla**

`src/auth/permission_catalog.py` — `page:settings_netbox_visualization` düğümünün hemen ardına:

```python
            _n(
                "page:settings_colocation_config",
                "Colocation sellable rack role configuration",
                "config",
                route_pattern="/administration/integrations/netbox/colocation",
                sort_order=58,
            ),
```

`sort_order=58`'in o bloktaki başka bir düğümle çakışmadığını doğrulayın:

```bash
grep -n "sort_order=5[6-9]" src/auth/permission_catalog.py
```

`src/auth/permission_service.py` — satır 137'deki `visualization` kontrolünün **öncesine** (daha spesifik yol önce gelmeli):

```python
        if admin_p.startswith("/administration/integrations/netbox/colocation"):
            return "page:settings_colocation_config"
```

- [ ] **Step 8: Callback modülünü kaydet**

`app.py` — satır 199 civarındaki `netbox_visualization_callbacks` import'unun ardına:

```python
from src.pages.settings.integrations import colocation_config_callbacks  # noqa: F401 — Colocation config
```

- [ ] **Step 9: Testleri çalıştır**

```bash
.venv/bin/python -m pytest tests/test_colocation_config_page.py tests/test_administration_routing.py tests/test_permission_catalog_colocation.py -q
```

Beklenen: hepsi PASS.

- [ ] **Step 10: Tüm GUI paketini çalıştır**

```bash
.venv/bin/python -m pytest tests/ -q 2>&1 | tail -5
```

Beklenen: yeni kırık yok.

- [ ] **Step 11: Commit ve push**

```bash
git add src/utils/colocation_config_ui.py \
        src/pages/settings/integrations/colocation_config.py \
        src/pages/settings/integrations/colocation_config_callbacks.py \
        src/pages/settings/shell.py src/auth/permission_catalog.py \
        src/auth/permission_service.py app.py \
        tests/test_colocation_config_page.py
git commit -m "feat(gui): Colocation Configuration ayar sayfası, NetBox/Loki sub-nav ve yetki kodu"
git push origin worktree-sellable-u-role-filter
```

---

### Task 7: Canlı doğrulama

**Files:** kod değişikliği yok — ölçüm ve rapor.

**Interfaces:**
- Consumes: Task 1-6.
- Produces: doğrulama notu (aşağıdaki tablo doldurulmuş hâlde) ve gerekirse takip commit'i.

- [ ] **Step 1: Migration'ı local webui'ye uygula**

`docker-entrypoint-initdb.d` yalnızca **boş** bir volume'da çalışır; mevcut DB'ye elle uygulayın:

```bash
docker exec -i bulutistan-webui-db psql -U webuiadmin -d bulutwebui \
  < services/customer-api/migrations/webui/047_colocation_role_rule.sql
docker exec -i bulutistan-webui-db psql -U webuiadmin -d bulutwebui \
  -c "SELECT role_id, sellable FROM gui_colocation_role_rule ORDER BY role_id;"
```

Beklenen: 4 satır — `1|f`, `2|t`, `3|f`, `4|f`.

- [ ] **Step 2: Servisleri yeniden kur ve deploy öncesi/sonrası sayıyı karşılaştır**

customer-api host'ta **:8001**, crm-engine **:8070**, GUI **:8050**. `sellable_service.py` değiştiği için crm-engine de yeniden build edilmeli — o dosya imaja customer-api'den kopyalanıyor.

```bash
docker compose up -d --build customer-api crm-engine gui
sleep 25
curl -s "http://localhost:8001/api/v1/crm/colocation/DC13" | python3 -c \
  "import json,sys; a=json.load(sys.stdin)['aggregate']; print('sellable_free_u', a['sellable_free_u'])"
```

Beklenen: **272** — seed bugünkü kuralı yazdığı için sayı deploy'dan etkilenmemeli. Farklıysa DURUN ve bildirin; muhtemel sebep kuralın hesaba yanlış geçirilmesi.

(`API_AUTH_REQUIRED` local'de `false`, o yüzden curl'e Authorization başlığı gerekmiyor. `true` ise 401 alırsınız — bu bir hata değil, header ekleyin.)

- [ ] **Step 3: Ayar değişikliğinin anında yansıdığını ölç**

```bash
curl -s -X PUT "http://localhost:8001/api/v1/colocation/role-rules" \
  -H 'Content-Type: application/json' \
  -d '{"rules":[{"role_id":"1","sellable":false},{"role_id":"2","sellable":true},{"role_id":"3","sellable":true},{"role_id":"4","sellable":false}]}'
curl -s "http://localhost:8001/api/v1/crm/colocation/*" | python3 -c \
  "import json,sys; a=json.load(sys.stdin)['aggregate']; print('sellable_free_u', a['sellable_free_u'])"
```

Beklenen: **3.800** (rol 3 havuza girdi, +297). Eski değer (3.503) dönüyorsa cache etag'i anahtara girmemiş demektir.

- [ ] **Step 4: crm-engine tarafının da kaydığını doğrula (≤30 sn)**

crm-engine ayrı process ve ayrı Redis DB'si; kuralı kendi memo'su dolduğunda alır. Bu adım o yayılmayı ölçer.

```bash
sleep 35
curl -s "http://localhost:8070/api/v1/crm/sellable-potential/by-panel?dc_code=DC13" | python3 -c \
  "import json,sys; rows=json.load(sys.stdin); print([(r.get('panel_key'), r.get('potential_tl')) for r in rows if 'colocation' in str(r.get('panel_key','')).lower()])"
```

Beklenen: colocation panelinin TL potansiyeli Step 3 öncesine göre **artmış** olmalı. Değişmediyse `role_rules_service` crm-engine'de bağlanmamış demektir (Task 4 Step 5b).

- [ ] **Step 5: Eski hâline döndür ve sayının geri geldiğini doğrula**

```bash
curl -s -X PUT "http://localhost:8001/api/v1/colocation/role-rules" \
  -H 'Content-Type: application/json' \
  -d '{"rules":[{"role_id":"1","sellable":false},{"role_id":"2","sellable":true},{"role_id":"3","sellable":false},{"role_id":"4","sellable":false}]}'
curl -s "http://localhost:8001/api/v1/crm/colocation/*" | python3 -c \
  "import json,sys; a=json.load(sys.stdin)['aggregate']; print('sellable_free_u', a['sellable_free_u'])"
```

Beklenen: **3.503**.

- [ ] **Step 6: Ekranı gözle doğrula**

`http://localhost:8050/administration/integrations/netbox/colocation` — dört rol listeleniyor mu, switch'ler `1/3/4 kapalı, 2 açık` mı, rol 3'ü açınca önizleme `3.503 → 3.800` diyor mu, Kaydet'e basınca uyarı modalı çıkıyor mu.

- [ ] **Step 7: Sonucu raporla**

| Ölçüm | Beklenen | Gerçekleşen |
|---|---|---|
| DC13 sellable free U (deploy sonrası) | 272 | |
| Global sellable free U (varsayılan) | 3.503 | |
| Global sellable free U (rol 3 açık) | 3.800 | |
| crm-engine colocation TL (rol 3 açık, ≤30 sn) | artmış | |
| Geri alınca | 3.503 | |

Tabloyu doldurup kullanıcıya bildirin. Sapma varsa commit **atmayın**, önce sebebi araştırın.

---

## Notlar

- **Migration numarası çakışması:** commit'lemeden önce `ls services/customer-api/migrations/webui/ | tail -3` ile 047'nin hâlâ boşta olduğunu doğrulayın; başka bir session 047'yi almışsa dosyayı 048'e yeniden adlandırın (bu repoda daha önce yaşandı).
- **`.env`'e dokunmayın** — `.gitignore`'da yazmasına rağmen git'te takipli. Local secret gerekirse `.env.local`.
- **Worktree'de `git stash` kullanmayın** — stash yığını diğer checkout'larla paylaşılıyor.
