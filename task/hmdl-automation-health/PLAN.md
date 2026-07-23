# TASK-69 — HMDL Kontrolü (Automation Health)

Datalake konfigürasyon verilerini dağıtan/monitor eden HMDL otomasyonlarının
**schedule ve veri kontrolü**. İki faz: (1) canlı operasyonel kontrol + rapor,
(2) GUI'ye kalıcı schedule/staleness monitoring yüzeyi.

Branch: `worktree-hmdl-automation-health` · Repo: Datalake-Platform-GUI

---

## Phase 1 — Operasyonel kontrol bulguları (2026-07-23 12:17 UTC, canlı `hmdl` şeması)

Kaynak: `bulutistan-hmdl-api` container → `bulutlake @ 10.134.16.6:5000`, `hmdl` şeması.

| Otomasyon | Beklenen cadence | Son prod çalışma | Yaş | Durum |
|---|---|---|---|---|
| `db_to_zabbix_sync` (NetBox→Zabbix) | ~8 sa | 07-23 12:10 | 0.1 sa | 🟢 sağlıklı |
| `datalake_collector_sync` (config dağıtım) | günlük 02:00 | 07-21 02:01 | 58 sa | 🔴 gecikmiş + kapsam çökük |
| `run_basic_checks` (reachability/coverage_target) | collector_sync ile | 07-16 02:12 | 178 sa | 🔴 7 gün ölü |
| `vm_reconciliation` (monitoring_*) | ~günlük (tarihsel) | 06-09 | ~44 gün | 🔴 durmuş |

**Kritik bulgular (ekibe operasyonel aksiyon — AWX tarafı, buradan yapılamaz):**
- **A) Collector-sync kapsam çöküşü (07-17):** 07-16'ya kadar 23 proxy/106 satır; 07-17'den beri
  yalnız 4 proxy (AZ11×2, DC13-NIFI1, DC14-NIFI1). 19 proxy/10 DC (DC11, DC12, DC14-NIFI2, DC15,
  DC16, DC17, DC18, ICT11, ICT21, UZ11) `proxy_node.last_seen` 07-16'da donmuş. `NiFi_Prod_Envanter`
  ya da `proxy_filter` daralmış olmalı.
- **B) Schedule durdu (07-21 sonrası):** günlük 02:00 job'u 07-22/07-23 tetiklenmedi. AWX schedule
  paused/disabled olabilir.
- **C) run_basic_checks 7 gün ölü:** reachability 07-16 02:12'den beri yok → coverage `is_live` ve
  not_ok sayıları bayat, DC14'ün 07-23 toparlanmasını yansıtmıyor.
- **D) vm_reconciliation ~44 gün durmuş:** monitoring_* 06-09'dan kalma.
- **E) Kalıcı veri boşlukları (07-21 coverage):** IBM 8 host eksik, VMware 4 cluster, Nutanix 1.

**En önemli GUI çıkarımı:** GUI bugün `last_prod_run_id`'yi düz string gösteriyor — hiçbir
tazelik/staleness sinyali yok. B/C/D haftalarca görünmeden durabildi. Phase 2 bu boşluğu kapatır.

---

## Phase 2 — GUI: HMDL Automation Health (#3 = adanmış sayfa + global alert)

Tek yeni backend endpoint her şeyi besler; GUI 3 yerde tüketir. Hepsi read-only.

### Backend (hmdl-api)
- `config.py`: otomasyon başına `warn_hours`/`dead_hours` eşikleri (env-override).
- `schemas.py`: `AutomationHealthResponse` + alt modeller.
- `app/db/queries/automation_health.py`: `build_automation_health()` + saf `classify(age, warn, dead)`.
- `collectors.py`: `GET /collectors/automation-health`.

### Frontend (GUI)
- `api_client.get_hmdl_automation_health()` (hata → `{}`).
- `hmdl_sync_ui.py`: `relative_age()`, `automation_status()`, `freshness_badge()`.
- yeni sayfa `hmdl_automation_health.py`: KPI + 4 otomasyon kartı (mini run timeline) +
  proxy coverage matrisi (23×last-seen) + veri boşlukları paneli.
- routing/nav: `shell.py` (import, HMDL_TABS, _PAGE_BUILDERS, code listeleri), `permission_catalog.py`
  (`page:settings_hmdl_automation_health`), `sidebar.py` (SETTINGS_ENTRY_CODES).
- **Banner** (`hmdl_overview.py`): stale+dead>0 iken kırmızı Alert + link.
- **Sidebar rozeti** (`shell.py _sub_nav`): HMDL / Automation Health tab'ında kırmızı sayı.

### Eşik varsayılanları
collector_sync 26/50h · zabbix 12/24h · checks 26/50h · reconciliation 48/120h (warn/dead).

### Testler (TDD)
- hmdl-api: `test_automation_health.py` — `classify` fresh/stale/dead sınırları.
- GUI: `test_hmdl_automation_health_page.py` — render + banner (stale) + nav tab.

### Uygulama sırası
1. classify (test-first) → 2. query orchestration → 3. schema+route → 4. api_client →
5. ui helpers → 6. page → 7. nav/perm wiring → 8. banner → 9. badge → 10. page/render tests → verify.
