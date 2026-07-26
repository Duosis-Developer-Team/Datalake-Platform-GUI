# TASK-09 — VMware / Zerto Alanlarının (Sarı Renkli) Çevrimi

**Tip:** Entegrasyon · **Efor:** M · **Öncelik:** Orta

## Hedef
Ekrandaki sarı ile işaretli alanların altyapı çalışmaları tamamlandı; bu verilerin çevrim/entegrasyon
işlemi GUI tarafından yapılacak.

> **Not:** "Sarı renkli alanlar" referansı **All Products-Operation** Excel'indeki renk kodlamasıdır
> (`datalake-platform-knowledge-base/wiki/CRM-Inventory-Infra-Matching.md`, kaynak dosya:
> `All Products-Operation 6-29-2026 2-06-03 PM.xlsx`). Git geçmişinde
> `0d16748a fix(qa): yellow-group findings` / `d0f6819c fix(qa): green-group verification findings`
> commit'leri aynı renk gruplarına atıf yapıyor.
> **İlk iş: hangi satırların "sarı" olduğunu Excel'den teyit edip listeye dökmek.**

## Mevcut durum — VMware ve Zerto tarafında ne var

### Zerto
| Öğe | Yer |
|---|---|
| Tablolar | `raw_zerto_vpg_metrics` (VPG/DR), `raw_zerto_license_metrics` (lisans), site metrikleri |
| Sorgular | `services/datacenter-api/app/db/queries/backup.py` (`get_dc_zerto_sites`, `get_dc_zerto_jobs`) |
| Endpoint | `/datacenters/{dc}/backup/zerto`, `/backup/zerto/license`, `/backup/zerto/jobs` |
| UI | `src/components/backup_panel.py`, `dc_view.py` / `customer_view.py` Backup & Replication sekmesi |
| Kategori | ADR-0025: Replication = Veeam + Zerto (vendor değil kategori bazlı UI) |
| CRM | Registry'de `family: backup_zerto`; `000BLT-169 Zerto Enterprise Cloud Edition License` → `match_status: sold_noted_customer_phase` |

### VMware
| Öğe | Yer |
|---|---|
| Tablolar | `vm_metrics`, `cluster_metrics`, `datacenter_metrics`, `vmhost_metrics`, `vmware_datastore` |
| Sorgular | `src/queries/vmware.py`, `services/datacenter-api/app/db/queries/{vmware.py,vmware_datastore.py}` |
| Klasik ayrımı | `cluster ILIKE '%KM%'` = Classic, aksi = Hyperconverged |
| CRM | `000BLT-58/64/60/201` (Klasik Mimari CPU/RAM/Disk) → `virt_classic_*` |

## "Çevrim" ne demek — üç olasılık, birini seçin

| Yorum | İş |
|---|---|
| **A. CRM ↔ altyapı eşleşmesi** | `product_matching_registry.yaml`'de `match_status: documented` / `sold_noted_customer_phase` olan VMware/Zerto SKU'larını `capacity`'ye taşımak, panel_key + infra_tables bağlamak |
| **B. Birim çevrimi** | Ham metrik biriminden faturalama birimine dönüşüm (MB→GB→TB, VPG→VM sayısı) `gui_unit_conversion` üzerinden |
| **C. Ekran entegrasyonu** | Altyapı ekibinin hazırladığı yeni tablo/kolonların panele bağlanması |

En olası: **A + B birlikte** (registry'de bu SKU'lar hâlâ `documented`/`sold_noted_customer_phase`).

## Yapılacaklar

- [ ] **Sarı satır listesini çıkar:** Excel'i aç, sarı işaretli `productnumber`'ları listele →
      `task/GUI/reports/sari-alanlar.md`
- [ ] Her SKU için: registry'de var mı? `match_status` ne? `panel_key` ve `infra_tables` doğru mu?
- [ ] Altyapı tarafında karşılığı olan tabloları doğrula (aşağıdaki SQL'ler)
- [ ] `shared/matching/product_matching_registry.yaml`'i güncelle: `documented` → `capacity`,
      `panel_key` ve `infra_tables` doldur
- [ ] `config/crm_service_mapping.yaml` + seed SQL yeniden üret:
      `python shared/service_mapping/generate_seed_sql.py`
- [ ] Migration ekle (`<repo-kök>/datalake/SQL/CRM/migrations/` deseninde, idempotent)
- [ ] Gerekiyorsa `gui_unit_conversion` kayıtlarını ekle
- [ ] Inventory ekranında yeni satırların doğru Total/Used/Free/Birim Fiyat ile geldiğini doğrula
- [ ] Audit sorgusunu çalıştır: `datalake/SQL/CRM/audit_crm_service_mapping_gaps.sql`

## Doğrulama SQL'leri

```sql
-- 1) Zerto: VPG ve korunan VM sayısı (latest snapshot)
WITH latest AS (
  SELECT DISTINCT ON (id) id, name, vmscount, provisioned_storage_mb, collection_timestamp
  FROM public.raw_zerto_vpg_metrics ORDER BY id, collection_timestamp DESC
)
SELECT COUNT(*) AS vpg, SUM(vmscount) AS korunan_vm,
       ROUND(SUM(provisioned_storage_mb)/1024.0, 2) AS provisioned_gb,
       MAX(collection_timestamp) AS son_veri
FROM latest;

-- 2) Zerto lisans
SELECT * FROM public.raw_zerto_license_metrics ORDER BY collection_timestamp DESC LIMIT 5;

-- 3) VMware Klasik (KM) kapasite — CRM ile karşılaştırılacak taban
SELECT COUNT(DISTINCT vmname) AS vm,
       SUM(number_of_cpus) AS vcpu,
       ROUND(SUM(total_memory_capacity_gb)::numeric, 2) AS ram_gb,
       ROUND(SUM(provisioned_space_gb)::numeric/1024, 2) AS provisioned_tb
FROM   public.vm_metrics
WHERE  "timestamp" > now() - interval '1 day'
  AND  cluster ILIKE '%KM%'
  AND  LEFT(vmname,1) <> '_' AND vmname NOT ILIKE '%silinecek%';

-- 4) CRM tarafı: bu SKU'lar ne kadar satılmış
SELECT p.productnumber, p.name, d.uomid_name, SUM(d.quantity) AS miktar, SUM(d.extendedamount) AS tl
FROM   discovery_crm_salesorderdetails d
JOIN   discovery_crm_salesorders so ON so.salesorderid = d.salesorderid
JOIN   discovery_crm_products p ON p.productid = d.productid
WHERE  so.statecode = 0 AND p.productnumber = ANY(:sari_sku_listesi)
GROUP  BY 1,2,3 ORDER BY 1;

-- 5) Eşleşme boşluk denetimi (bulutwebui)
--    datalake/SQL/CRM/audit_crm_service_mapping_gaps.sql dosyasını çalıştır
```

## Kabul kriterleri
- [ ] Sarı SKU listesi yazılı ve onaylı
- [ ] Her sarı SKU registry'de `capacity` statüsünde, `panel_key` + `infra_tables` dolu
- [ ] Seed SQL yeniden üretilmiş, migration test ortamında uygulanmış (idempotent)
- [ ] Inventory ekranında bu satırlar Total/Used/Free ile geliyor, "unmapped" bandında değil
- [ ] Audit sorgusunda bu SKU'lar için boşluk yok

## Cursor / Claude Code prompt

```
Bağlam: task/GUI/00-ortam-ve-dogrulama-rehberi.md,
datalake-platform-knowledge-base/wiki/CRM-Inventory-Infra-Matching.md,
datalake-platform-knowledge-base/adrs/{ADR-0024-crm-inventory-infra-matching.md,ADR-0025-policy-based-backup-replication-ui.md},
shared/matching/product_matching_registry.yaml, config/crm_service_mapping.yaml,
shared/service_mapping/generate_seed_sql.py, task/query-map/{01-vmware.md,06-backup-dr.md}

Görev: VMware ve Zerto ile ilgili "sarı" CRM kalemlerini documented'tan capacity'ye taşı.

ADIM 0: Sarı SKU listesi bana verilmediyse DURUp iste. Tahmin etme.

1. Verilen her productnumber için:
   - registry'de var mı, match_status ne, panel_key/infra_tables dolu mu → tablo halinde raporla
   - altyapı tarafında karşılık gelen tabloyu information_schema ile doğrula ve son veri yaşını yaz
2. Eşleşme kurulabilenleri registry'de match_status: capacity yap, panel_key + infra_tables doldur.
   Kurulamayanları gerekçesiyle documented bırak.
3. config/crm_service_mapping.yaml'i güncelle ve
   python shared/service_mapping/generate_seed_sql.py ile seed SQL'i yeniden üret.
4. <repo-kök>/datalake/SQL/CRM/migrations/ altına idempotent migration ekle (mevcut dosya isimlendirmesine uy).
5. Birim uyuşmazlığı varsa gui_unit_conversion kaydı ekle (MB->GB->TB, VPG->VM).
6. datalake/SQL/CRM/audit_crm_service_mapping_gaps.sql'i çalıştır, öncesi/sonrası boşluk sayısını raporla.
7. tests/: yeni panel_key'lerin inventory çıktısında Total/Used/Free ürettiğini doğrulayan test.

Kısıt: Mevcut virt_classic / backup_zerto satırlarında regresyon olmamalı.
```
