# Kararlar Kütüğü (Decision Log)

Bu dosya, plan üzerinde alınan bağlayıcı kararları ve gerekçelerini tutar.
Bir madde üzerinde çalışırken **önce buraya bakın** — kapsam tartışması burada kapanmıştır.

---

## K-01 · NetBackup dual basis (PreDedup + PostDedup)

**Tarih:** 2026-07-31 · **Durum:** Accepted · supersedes 2026-07-26 “önce mutabakat / tek taban” framing

| Surface | Metric | Meaning |
|---|---|---|
| Customer sold / used / CRM sold qty | **PreDedupSize** | What the customer bought / transferred |
| Datacenter / real cost | **PostDedupSize** | What it costs us on disk |
| CRM Inventory | **Both** | Sold (pre) vs cost (post) + dedup margin |
| Customer perspective | Pre only | Never show PostDedup (K-06 backend strip) |
| Manager perspective | Pre + Post + margin | Profit from compression |

TASK-B1 remains a **validation** report (CRM sold ≈ pre; post ≈ pool used), not a single-basis choice.
Report: [reports/netbackup-fatura-tabani-mutabakat.md](reports/netbackup-fatura-tabani-mutabakat.md)

---

## K-02 · Veeam/Zerto replication: HİBRİT YÖNTEM

**Tarih:** 2026-07-26 · **Durum:** Uygulanacak → [TASK-B3](TASK-B3-veeam-zerto-replikasyon.md)

VM resources come from `vm_metrics` / `nutanix_vm_metrics` after name-pattern classification.
Vendor tables supply **counts only** (`objects_count` / `vmscount`) for reconciliation.
Platform Backup Mapping holds Veeam/Zerto separators.

**Gerekçe:** `raw_zerto_vpg_metrics` ve `raw_veeam_jobs_states` **VM adı listesi taşımıyor**.
Collector genişletmesi backlog; hibrit yöntem DC/müşteri toplamı verir.

---

## K-03 · License compliance on Summary + Backup

**Tarih:** 2026-07-31 · **Durum:** Accepted

If customer has Veeam/Zerto jobs/VPGs, matching license must exist on active sales order details.
OK (green) vs NO. Also flag capacity **unsold usage**. Surfaces: **Summary** and **Backup** only — not Billing.

(Note: earlier K-03 was Monitoring M1 ingest freshness — see K-07.)

---

## K-04 · Platform Backup Mapping

**Tarih:** 2026-07-31 · **Durum:** Implemented (UI seed; DB persist later)

**Administration → Platform → Backup Mapping** (`/administration/platform/backup-mapping`).
Tabs: Image/Application, Veeam/Zerto separators, Nutanix multipliers.
Legacy CRM Backup route redirects; `page:settings_crm_backup` aliases to the new path.

(Note: earlier K-04 was CRM Sales Order screen — see K-08.)

---

## K-05 · Power: KALDIRMA DEĞİL, FEATURE-FLAG

**Tarih:** 2026-07-26 · **Durum:** Uygulanacak → [TASK-03](TASK-03-power-sekmesi-kaldirma.md)

`FEATURE_POWER_ENABLED=false` ile UI'dan gizlenecek; hesap/sellable/permission katmanına dokunulmayacak.

---

## K-06 · Hassas alanlar: BACKEND'DE KESİLİR

**Tarih:** 2026-07-26 · **Durum:** Uygulanacak → [TASK-13](TASK-13-customer-altyapi-gizleme.md)

Müşteri rolünde gizlenecek alanlar **response modelinden çıkarılır**, frontend'de gizlenmez.

---

## K-07 · Monitoring önceliği: M1 — INGEST FRESHNESS

**Tarih:** 2026-07-26 · **Durum:** Uygulanacak → [TASK-M1](TASK-M1-ingest-freshness.md)

Monitoring zincirinin 4. halkası (**veri geliyor mu**) önce kapatılacak.

---

## K-08 · CRM fatura ekranı: SALES ORDER

**Tarih:** 2026-07-26 · **Durum:** Uygulanacak → [TASK-07](TASK-07-crm-fatura-akisi.md)

Ekran `discovery_crm_salesorders` + details. UI'da **"Sales Orders / Siparişler"** — "Fatura" denmeyecek.

---

## Açık kalan kararlar

| # | Konu | Kime | Blokladığı iş |
|---|------|------|---------------|
| A-01 | Zerto disk = hedef disk mi, journal dahil mi? | Altyapı / Satış | TASK-B3 |
| A-02 | Replika VM'ler billable sanallaştırmadan düşülüyor mu? | Satış | TASK-B3 |
| A-03 | Nutanix backup: `000BLT-45` ve `000BLT-221` ayrı mı? | Satış | TASK-B4 |
| A-04 | "Veri gelmiyor" eşiği collector başına ne olmalı? | Can | TASK-M1 |
| A-05 | Monitoring ekranı hangi repoya? | Can | TASK-M1 |
| A-06 | Alarm/e-posta istenecek mi? | Can / Murat Bey | TASK-M1 |
| A-07 | ITSM mapping çıktısı | ? | TASK-08 |
| A-08 | Backup internet metrik/SKU | ? | TASK-12 |
| A-09 | Müşteriden gizlenecek alanların tam listesi | Can / Sezgin Bey | TASK-13 |
| A-10 | USB Port SKU'su açılacak mı? | Satış / CRM | TASK-19 |
| A-11 | Excel'deki "sarı" satırların listesi | ? | TASK-09 |
