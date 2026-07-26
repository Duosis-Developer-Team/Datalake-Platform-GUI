# TASK-19 — USB Port Hizmetinin Eklenmesi

**Tip:** Feature · **Efor:** S · **Durum: NETLEŞTİRİLECEK**

## Hedef
USB Port hizmetinin eklenmesi.

## ⚠️ Kritik tespit: CRM kataloğunda USB ürünü YOK

Elimizdeki CRM ürün snapshot'ı (`discovery_crm_products`, **222 ürün**, 2026-05-04) tarandı:
`usb`, `USB Port`, `Port Hizmeti` desenleriyle arama yapıldı.

Bulunan port ürünleri:
- `000BLT-67` Data Switch Port ve SFP Hizmeti (Adet)
- `000BLT-68` Management Switch Port Hizmeti (Adet)
- `000BLT-20` Cross Connection Port Hizmeti (Adet)

**USB ile ilgili hiçbir ürün yok.**

⇒ İki senaryo:

| Senaryo | Aksiyon |
|---|---|
| **A.** Ürün CRM'de yeni açılmış (snapshot bayat) | Canlı `discovery_crm_products`'ı sorgula (SQL 1) |
| **B.** Ürün henüz CRM'de açılmamış | **Satış/CRM ekibinden SKU açılması istenecek** — SKU olmadan hesaplama altyapısı kurulamaz |

## Toplantıda sorulacaklar

1. USB Port hizmetinin CRM SKU'su var mı? Varsa `productnumber` nedir?
2. Birim ne — port adedi mi, cihaz adedi mi?
3. Altyapı tarafında nasıl tespit edilecek?
   - NetBox'ta USB cihazı/port'u envanterde var mı?
   - Yoksa tamamen manuel/CRM-only bir kalem mi olacak?
4. Hangi ekranda görünecek — Inventory, DC View, Customer View?

## Ön kontrol (toplantı öncesi)

```sql
-- 1) Canlı katalogda USB ürünü var mı
SELECT productnumber, name, defaultuomid_name, statecode_text, createdon
FROM   public.discovery_crm_products
WHERE  name ILIKE '%usb%'
ORDER  BY createdon DESC;

-- 2) Genel olarak "Port" geçen tüm ürünler
SELECT productnumber, name, defaultuomid_name, statecode_text
FROM   public.discovery_crm_products
WHERE  name ILIKE '%port%' ORDER BY productnumber;

-- 3) Kataloğun tazeliği (snapshot ne kadar eski)
SELECT COUNT(*) AS urun, MAX(collection_time) AS son_senkron,
       now() - MAX(collection_time) AS gecikme
FROM   public.discovery_crm_products;

-- 4) Son 90 günde eklenen yeni ürünler (yeni SKU'lar burada görünür)
SELECT productnumber, name, defaultuomid_name, createdon
FROM   public.discovery_crm_products
WHERE  createdon > now() - interval '90 days' ORDER BY createdon DESC;

-- 5) NetBox'ta USB ile ilgili bir şey var mı (altyapı kaynağı arayışı)
SELECT column_name FROM information_schema.columns
WHERE table_schema='public' AND table_name='discovery_netbox_inventory_device'
  AND column_name ILIKE '%port%';
```

## Yapılacaklar

- [ ] Yukarıdaki 5 sorguyu çalıştır, sonucu dosyaya yaz
- [ ] SKU **varsa** → TASK-10/17/18 ile aynı akış:
      registry'ye ekle → `gui_crm_service_pages` → seed SQL → migration → inventory ailesi
- [ ] SKU **yoksa** → CRM/satış ekibine SKU açma talebi; bu madde bloke olarak işaretlenir
- [ ] Altyapı kaynağı yoksa `match_status: documented` ile CRM-only kalem olarak tanımla
      (TASK-17'deki Domain deseninin aynısı)

## Kabul kriterleri
- [ ] "USB Port hizmeti CRM'de var mı" sorusu kanıtla cevaplanmış
- [ ] SKU varsa: registry + service_pages + migration tamam, Inventory'de görünüyor
- [ ] SKU yoksa: talep yazılı olarak iletilmiş, madde bloke işaretli, beklenen çıktı tanımlı

## Cursor / Claude Code prompt

```
Bağlam: task/GUI/00-ortam-ve-dogrulama-rehberi.md, task/GUI/TASK-17-domain-hizmeti.md,
shared/matching/product_matching_registry.yaml, config/crm_service_mapping.yaml

Görev: USB Port hizmeti için CRM ve altyapı durumunu tespit et.

ADIM 0 (zorunlu, kod yazmadan): canlı discovery_crm_products'ta 'usb' ve 'port' geçen tüm
ürünleri listele. Kataloğun son senkron zamanını da yaz.
- USB SKU'su BULUNAMAZSA: DUR. "CRM'de USB Port SKU'su yok, satış ekibinden talep edilmeli"
  raporunu yaz ve bitir. Ürün uydurma, tahmini SKU ile registry'ye kayıt EKLEME.
- BULUNURSA: TASK-17'deki Domain akışının aynısını uygula (registry -> gui_crm_service_pages ->
  config/crm_service_mapping.yaml -> generate_seed_sql.py -> idempotent migration ->
  inventory ailesi). Altyapı kaynağı yoksa match_status: documented ve Total/Used yerine
  "no infra source" etiketi.

Çıktı: task/GUI/reports/usb-port-tespit.md
```
