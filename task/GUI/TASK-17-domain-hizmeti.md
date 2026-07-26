# TASK-17 — Domain Hizmeti Hesaplama Altyapısı

**Tip:** Feature (hizmet kalemi ↔ altyapı hesabı) · **Efor:** M · **Öncelik:** Orta

## Hedef
Domain hizmeti için hizmet kalemi ↔ altyapı verisi hesaplama altyapısının hazırlanması.

## Mevcut durum — CRM kataloğunda ne var

CRM ürün snapshot'ında (`discovery_crm_products`, 222 ürün) domain ile ilgili kalemler:

| SKU | Ürün | Birim | Registry'de |
|---|---|---|---|
| `000BLT-14` | **Cloud DNS Hizmeti** | **per Domain** | ❌ yok |
| `000BLT-80` | Plesk Web Admin Edition VPS (10 Domains) | Adet | ❌ yok |
| `000BLT-81` | Plesk Web Host Edition VPS (Unlimited Domains) | Adet | ❌ yok |
| `000BLT-82` | Plesk Web Pro Edition VPS (30 Domains) | Adet | ❌ yok |

> **"Domain Hizmeti" muhtemelen `000BLT-14 Cloud DNS Hizmeti` (birim: per Domain).**
> Ancak elimizdeki CRM snapshot'ı **2026-05-04** tarihli — canlı katalogda ayrı bir
> "Alan Adı / Domain Kayıt" ürünü olabilir. **İlk iş canlı katalogdan doğrulamak.**

## Altyapı tarafı — zorluk

Domain/DNS için **bulutlake'te bir kaynak tablo yok**:
- IPAM tablosu yok (registry'de `000BLT-91 Public IPv4` için not düşülmüş: *"No IPAM table in bulutlake yet"*)
- DNS zone/kayıt toplayan bir collector görünmüyor

⇒ Bu madde iki fazlı:

| Faz | İş |
|---|---|
| **Faz 1 (bu hafta)** | CRM tarafını tanımla: registry'ye ekle, `match_status: documented`, panel oluştur, satılan miktar/TL göster. Altyapı karşılaştırması **yok**. |
| **Faz 2 (sonraki)** | Bir DNS/domain veri kaynağı bağlanınca (NetBox IPAM, DNS collector, kayıt firması API'si) `capacity` statüsüne taşı. |

## Yapılacaklar (Faz 1)

- [ ] **Canlı CRM kataloğunu sorgula:** gerçekten hangi SKU "Domain Hizmeti"? (aşağıdaki SQL 1)
- [ ] `shared/matching/product_matching_registry.yaml`'e ekle:
  ```yaml
  "000BLT-14":
    name: Cloud DNS Hizmeti
    usage_source: ""            # henüz veri kaynağı yok
    matching_rule: CRM satılan domain adedi (altyapı kaynağı bekleniyor)
    match_status: documented
    family: domain
    infra_tables: []
    notes: No DNS/IPAM source table in bulutlake yet - Phase 2
  ```
- [ ] `gui_crm_service_pages`'e `page_key: domain_dns` kaydı (`resource_unit: Domain`)
- [ ] `config/crm_service_mapping.yaml` güncelle + `shared/service_mapping/generate_seed_sql.py` ile seed üret
- [ ] Idempotent migration (`<repo-kök>/datalake/SQL/CRM/migrations/`)
- [ ] Inventory ekranında "Domain / DNS" ailesi: CRM Sold + TL, Total/Used **"—"** (kaynak yok bilgisiyle)
- [ ] Plesk ürünlerini (`000BLT-80/81/82`) ayrı bir `managed_hosting` ailesine ekleyip eklememeyi değerlendir

## Doğrulama SQL'leri

```sql
-- 1) Canlı katalogda domain ile ilgili tüm ürünler (SNAPSHOT DEĞİL, CANLI)
SELECT productnumber, name, defaultuomid_name, statecode_text, blt_productgroup_text
FROM   public.discovery_crm_products
WHERE  name ILIKE '%domain%' OR name ILIKE '%alan ad%' OR name ILIKE '%dns%'
       OR defaultuomid_name ILIKE '%domain%'
ORDER  BY productnumber;

-- 2) Bu SKU'lar ne kadar satılmış
SELECT p.productnumber, p.name, d.uomid_name,
       SUM(d.quantity) AS miktar, SUM(d.extendedamount) AS tl,
       COUNT(DISTINCT so.customerid) AS musteri,
       ROUND(SUM(d.extendedamount)/NULLIF(SUM(d.quantity),0),2) AS ima_edilen_fiyat
FROM   discovery_crm_salesorderdetails d
JOIN   discovery_crm_salesorders so ON so.salesorderid = d.salesorderid
JOIN   discovery_crm_products p ON p.productid = d.productid
WHERE  so.statecode = 0
  AND (p.name ILIKE '%domain%' OR p.name ILIKE '%dns%')
GROUP  BY 1,2,3 ORDER BY tl DESC;

-- 3) Altyapı tarafında DNS/domain kaynağı var mı (muhtemelen yok - doğrula)
SELECT table_name FROM information_schema.tables
WHERE table_schema='public'
  AND (table_name ILIKE '%dns%' OR table_name ILIKE '%domain%' OR table_name ILIKE '%ipam%')
ORDER BY 1;

-- 4) NetBox'ta IPAM/prefix tabloları geldi mi
SELECT table_name FROM information_schema.tables
WHERE table_schema='public' AND table_name ILIKE 'discovery_netbox%' ORDER BY 1;
```

## Kabul kriterleri
- [ ] "Domain Hizmeti"nin hangi SKU olduğu canlı katalogdan doğrulanmış ve yazılı
- [ ] SKU registry + `gui_crm_service_pages`'te tanımlı; seed SQL üretilmiş; migration uygulanmış
- [ ] Inventory'de "Domain" satırı CRM Sold + TL ile görünüyor
- [ ] Altyapı kaynağı olmadığı ekranda açıkça belirtiliyor (boş 0 değil, "kaynak yok" etiketi)
- [ ] Faz 2 için gereken veri kaynağı talebi yazılı (kime, ne isteniyor)

## Cursor / Claude Code prompt

```
Bağlam: task/GUI/00-ortam-ve-dogrulama-rehberi.md, docs/CRM_SERVICE_MAPPING.md,
datalake-platform-knowledge-base/adrs/ADR-0024-crm-inventory-infra-matching.md,
shared/matching/product_matching_registry.yaml, config/crm_service_mapping.yaml,
shared/service_mapping/generate_seed_sql.py

Görev: Domain hizmeti için CRM tarafı hesaplama altyapısını kur (Faz 1 - altyapı kaynağı yok).

1. ÖNCE canlı discovery_crm_products'ı sorgula: domain/dns/alan adı geçen tüm ürünleri listele.
   Elimizdeki 2026-05-04 snapshot'ında sadece 000BLT-14 (Cloud DNS, per Domain) ve
   Plesk ürünleri var; canlıda başka SKU çıkarsa raporla ve bana sor.
2. product_matching_registry.yaml'e ekle: family: domain, match_status: documented,
   infra_tables: [] ve "no DNS/IPAM source in bulutlake yet" notu.
3. gui_crm_service_pages'e page_key domain_dns (resource_unit: Domain) kaydı;
   config/crm_service_mapping.yaml güncelle; generate_seed_sql.py ile seed üret;
   <repo-kök>/datalake/SQL/CRM/migrations/ altına idempotent migration.
4. inventory_overview_service.py + crm_inventory_report.py: "Domain" ailesi görünsün.
   Total/Used kolonlarında sayı yerine "no infra source" etiketi göster - 0 GÖSTERME.
5. information_schema ile DNS/IPAM tablosu var mı doğrula; varsa Faz 2 planını dosyaya yaz.
6. tests/: domain ailesinin inventory çıktısında CRM Sold ile göründüğü, Total/Used'un
   sayı değil etiket döndüğü.

Kısıt: Olmayan bir altyapı kaynağı uydurma. Kaynak yoksa açıkça "kaynak yok" göster.
```
