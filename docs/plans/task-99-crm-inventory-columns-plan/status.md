# Status

**Current status:** `draft`
**Last updated:** 2026-08-07
**Hermes:** `TASK-99` — `in_progress`, due 2026-08-07, priority `urgent`

## Completed

- Classification: **L2 (standard)** — 15 soru cevaplandı, gerekçe `README.md`'de
- Current-state analizi (`implementation-plan.md` §1) — dosyalar okunarak doğrulandı
- Spec (`spec.md`) — 10 functional + 6 non-functional requirement, 9 acceptance criteria
- `ADR-001` (`decisions.md`) — kanonik omurga + silme yasağı, 2 alternatif değerlendirildi
- Değişiklik noktaları, 8 adım, interfaces (`implementation-plan.md` §2-4)
- Test planı (`testing-plan.md`) — baseline **58 test yeşil** olarak ölçüldü

## In progress

—

## Blockers

**Yok.** Blocking unknown bulunmuyor (`spec.md` §10).

## Deviations from plan

—

## Next action

Plan `draft`. İki şey bekliyor:

1. **Kullanıcı incelemesi** — özellikle `ADR-001`'deki "ilgisiz kolon silinmez,
   `—` ile durur" kararı ve `spec.md` §8'deki varsayım (somut alan listesi
   verilmediği kabulü).
2. Onay sonrası durum `approved` olur ve uygulama `ccode` profiline devredilir.
   Uygulama `implementation-plan.md` §3 Adım 1'den başlar.

## Açık uçlar (bloklamıyor)

- Canlıda `comparison_only` profilinde satır var mı? Local'de doğrulanamadı;
  `AC-007` sentetik satırla test edilecek.
- `comparison_only`'ye omurga gereği eklenen `Free`/`Unsold` anlamlı değer
  gösterecek mi? Anlamsız çıkarsa düzeltme yeri `prepare_service_row`'dur ve
  ayrı bir iştir (`spec.md` §10).
