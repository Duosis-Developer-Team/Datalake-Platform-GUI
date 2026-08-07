# TASK-99 — CRM Inventory kolon standardizasyonu

## Purpose

CRM Inventory Overview (`/crm/inventory-overview`) ekranında ortak kolonlar her
hizmet grubunda farklı konumda duruyor; flat tablo grouped görünümdeki sekiz
kolonu göstermiyor; Excel/PDF çıktısı ekrandaki tabloyla ilgisiz ham bir döküm
veriyor. Bu plan üçünü tek bir kanonik kolon omurgasına bağlar ve yol üstünde
bulunan bir ölü kolon hatasını (`Δ Used vs CRM`) düzeltir. Hedef kullanıcı, bu
ekranı kullanan ve çıktısını rapor olarak alan Bulutistan tarafı.

## Plan Classification

- **Level:** 2 Standard
- **Complexity:** medium
- **Risk:** low
- **Current phase:** implementation
- **Current sprint:** n/a — L2'de sprint kavramı yok
- **Status:** `approved` — 2026-08-07, Arca
- **Created:** 2026-08-07
- **Last updated:** 2026-08-07
- **Classification gerekçesi:** Taban 4-15 dosya / 2 katman (GUI sunum +
  export) = L2. Yükselticiler L2 tabanını aşmıyor: bir mimari karar var
  (`ADR-001`), gruba özel kolonlar export contract'ını genişletiyor, RBAC
  mekanizması **kullanılıyor ama değiştirilmiyor**, performans etkisi kolon
  genişliğiyle sınırlı. Migration yok, tek modül, tek sprint, geri dönüşü zor
  karar yok — L3'e çıkacak neden bulunmuyor.

## Start Here

| Role or Agent | Read First |
|---|---|
| Implementation Agent (`ccode`) | `implementation-plan.md` §3 (adımlar) → `decisions.md` `ADR-001` → `testing-plan.md` |
| Test Agent | `testing-plan.md` — her testin yanında hangi bozulmayı yakaladığı yazılı |
| Review Agent | `spec.md` §9 (acceptance criteria) → `decisions.md` |

## Source of Truth

| Information | Canonical document |
|---|---|
| Product requirements | `spec.md` §4-5 (`REQ-F-*`, `REQ-NF-*`) |
| Acceptance criteria | `spec.md` §9 (`AC-001`–`AC-009`) |
| Scope / out of scope | `spec.md` §6-7 |
| Decisions | `decisions.md` (`ADR-001`) |
| Mevcut kod durumu | `implementation-plan.md` §1 — dosya yolları ve satır numaralarıyla doğrulanmış |
| Değişiklik noktaları ve adım sırası | `implementation-plan.md` §2-3 |
| Fonksiyon imzaları ve export sayfa sözleşmesi | `implementation-plan.md` §4 |
| Test stratejisi ve rollback | `testing-plan.md` |
| Current blockers | `status.md` — bugün blocker yok |

Delivery pipeline satırı **gerekmedi**: iş tek repo, tek dal, dc13 docker compose
ile standart deploy; ayrı bir teslim hattı kararı yok (`testing-plan.md` §6).

## Reading Order

1. `README.md` (bu dosya) — kapsam ve seviye
2. `spec.md` — ne yapılacak, hangi kabul kriteriyle
3. `decisions.md` — omurga kararı ve reddedilen iki alternatif
4. `implementation-plan.md` — mevcut durum, değişiklik noktaları, adımlar
5. `testing-plan.md` — doğrulama ve rollback
6. `status.md` — güncel durum

## Current Status

Planlama tamamlandı. Current-state analizi dosyalar okunarak doğrulandı;
`crm_inventory_report.py` içindeki 12 kolon sabiti, 9 efektif profil ve export
akışı satır numaralarıyla belgelendi. Test baseline'ı ölçüldü: **58 test yeşil**.
Spec, ADR ve test planı yazıldı; plan `draft` durumunda ve kullanıcı incelemesi
bekliyor.

## Active Blockers

**Yok.** Blocking unknown bulunmuyor (`spec.md` §10). İki açık uç var ama ikisi de
uygulamayı bloklamıyor; `status.md` sonunda kayıtlı.

## Next Action

Implementation agent (`ccode`) `implementation-plan.md` §3 **Adım 1**'den başlar
(`delta_fmt` üretimi / `BUG-001`). Adım sırası bağımlılığa göre kilitlidir.

## Update Rules

- `spec.md`, `decisions.md`, `implementation-plan.md` yalnız planlama turunda ve
  kullanıcı onayıyla değişir. Uygulama agent'ı bunlara dokunmaz.
- `status.md` her uygulama turundan sonra implementation agent tarafından
  güncellenir; plandan sapma olursa **Deviations** bölümüne yazılır, eski karar
  sessizce üstüne yazılmaz.
- `testing-plan.md`'ye yeni test eklenebilir; var olan bir testin **hangi
  bozulmayı yakaladığı** cümlesi silinemez.

## Escalation Rules

Şu durumlarda uygulama **durur** ve kullanıcıya sorulur:

- Bir profilin omurgadan sapması için özel bir `if` dalı gerekmesi — bu `ADR-001`'e
  aykırıdır ve kararın yeniden değerlendirilmesini gerektirir.
- `REQ-F-005`'teki slot yeniden kullanım listesine yeni bir eşleme eklenmesi
  gerekmesi (liste kapalıdır, yeni eşleme yeni ADR ister).
- Backend, API veya `sellable` hesabına dokunma ihtiyacı doğması — `REQ-NF-001`
  bunu dışarıda tutuyor.
- Sonradan somut bir alan listesi çıkması — `spec.md` §8'deki varsayım düşer ve
  `REQ-F-006` genişler.
- Bir testin yeni sözleşmeye uydurulamayıp silinmesi gerekmesi (`AC-009`).
