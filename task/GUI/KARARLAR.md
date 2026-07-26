# Kararlar Kütüğü (Decision Log)

Bu dosya, plan üzerinde alınan bağlayıcı kararları ve gerekçelerini tutar.
Bir madde üzerinde çalışırken **önce buraya bakın** — kapsam tartışması burada kapanmıştır.

---

## K-01 · NetBackup faturalama tabanı: ÖNCE MUTABAKAT

**Tarih:** 2026-07-26 · **Durum:** Analiz bekliyor → [TASK-B1](TASK-B1-netbackup-fatura-tabani.md)

Pre-dedup mu post-dedup mu faturalandığı **bilinmiyor**. Karar vermeden önce mevcut CRM
satışları ile her iki hesabı yan yana koyan mutabakat raporu üretilecek; hangisine yakın
olduğuna bakılarak taban belirlenecek.

> **Kod yazmadan önce bu rapor çıkmalı.** Yanlış taban seçimi 3–10× fatura hatasıdır.

---

## K-02 · Veeam/Zerto replikasyon: HİBRİT YÖNTEM

**Tarih:** 2026-07-26 · **Durum:** Uygulanacak → [TASK-B3](TASK-B3-veeam-zerto-replikasyon.md)

VM düzeyinde vendor ataması için **isim deseni + vendor sayacı mutabakatı** kullanılacak.

**Gerekçe:** `raw_zerto_vpg_metrics` ve `raw_veeam_jobs_states` **VM adı listesi taşımıyor**
(sadece `vmscount` / `objects_count`). Kesin yöntem collector genişletmesi gerektiriyor
(project-zabake + NiFi deploy, 1–2 hafta). Hibrit yöntem DC ve müşteri düzeyinde doğru
toplam verir; VM düzeyinde vendor ataması yaklaşıktır ve fark raporlanır.

**Sonuç:** Collector genişletmesi backlog'a alınır, gelince kesin yönteme geçilir.

---

## K-03 · Monitoring önceliği: M1 — INGEST FRESHNESS

**Tarih:** 2026-07-26 · **Durum:** Uygulanacak → [TASK-M1](TASK-M1-ingest-freshness.md)

Monitoring zincirinin 4. halkası (**veri geliyor mu**) önce kapatılacak.
M2 (vCenter rollup), M3 (dual-proxy), M4 (backup coverage) sonraki sırada.

**Gerekçe:** 1–3. halkalar (beklenen / konfigüre / erişilebilir) zaten çalışıyor.
"Erişim var ama veri gelmiyor" kör noktası hem DC11 backup sorununu (TASK-05) hem de
backup faturalandırmasının güvenilirliğini doğrudan etkiliyor.

---

## K-04 · CRM fatura ekranı: SALES ORDER

**Tarih:** 2026-07-26 · **Durum:** Uygulanacak → [TASK-07](TASK-07-crm-fatura-akisi.md)

Ekran `discovery_crm_salesorders` + `discovery_crm_salesorderdetails` üzerine kurulacak.
UI'da **"Sales Orders / Siparişler"** olarak adlandırılacak — "Fatura" denmeyecek.

**Gerekçe:** Dynamics CRM'den `invoice` / `invoicedetail` entity'leri toplanmıyor.
Gerçek fatura ihtiyacı netleşirse CRM collector'ı genişletilir ve aynı ekran invoice'a bağlanır (backlog).

---

## K-05 · Power: KALDIRMA DEĞİL, FEATURE-FLAG

**Tarih:** 2026-07-26 · **Durum:** Uygulanacak → [TASK-03](TASK-03-power-sekmesi-kaldirma.md)

`FEATURE_POWER_ENABLED=false` ile UI'dan gizlenecek; hesap/sellable/permission katmanına dokunulmayacak.

**Gerekçe:** `virt_power` / `virt_power_hana` sellable zincirine (ADR-0022), permission ağacına ve
inventory ailelerine gömülü. Silmek DC/Customer sayfalarını kırar. Bayrak `true` yapıldığında eski davranış birebir döner.

---

## K-06 · Hassas alanlar: BACKEND'DE KESİLİR

**Tarih:** 2026-07-26 · **Durum:** Uygulanacak → [TASK-13](TASK-13-customer-altyapi-gizleme.md)

Müşteri rolünde gizlenecek alanlar **response modelinden çıkarılır**, frontend'de gizlenmez.
Export (Excel/PDF) ve chatbot/MCP katmanı da aynı maskelemeye tabidir.

---

## Açık kalan kararlar

| # | Konu | Kime | Blokladığı iş |
|---|------|------|---------------|
| A-01 | Zerto disk = hedef disk mi, journal dahil mi? | Altyapı / Satış | TASK-B3 |
| A-02 | Replika VM'ler billable sanallaştırmadan düşülüyor mu (bugünkü faturada)? | Satış | TASK-B3 (çift faturalama) |
| A-03 | Nutanix backup: `000BLT-45` ve `000BLT-221` ayrı mı hesaplanacak? | Satış | TASK-B4 |
| A-04 | "Veri gelmiyor" eşiği collector başına ne olmalı? | Can | TASK-M1 |
| A-05 | Monitoring ekranı hangi repoya — GUI mi project-zabake mi? | Can | TASK-M1 |
| A-06 | Alarm/e-posta istenecek mi, yoksa sadece ekran mı? | Can / Murat Bey | TASK-M1 |
| A-07 | ITSM mapping çıktısı: rapor mu, otomatik eşleştirme mi? | ? | TASK-08 |
| A-08 | Backup internet: hangi metrik, hangi birim, hangi SKU? | ? | TASK-12 |
| A-09 | Müşteriden gizlenecek alanların tam listesi | Can / Sezgin Bey | TASK-13 |
| A-10 | USB Port SKU'su açılacak mı? | Satış / CRM | TASK-19 |
| A-11 | Excel'deki "sarı" satırların listesi | ? | TASK-09 |
