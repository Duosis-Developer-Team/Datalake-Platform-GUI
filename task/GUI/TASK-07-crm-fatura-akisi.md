# TASK-07 — CRM Fatura Görüntüleme ve Güncelleme Akışı

**Tip:** Feature · **Efor:** L · **Öncelik:** Orta-Yüksek

## Hedef
Müşteriler CRM faturalarını görebilsin. Şu an proje geldiğinde otomatik proje güncellemesi olmadığı için,
kullanıcıların **manuel olarak güncellemeyi seçip** faturayı görebileceği bir yapı kurulacak.

## ✅ KARAR VERİLDİ — [K-04](KARARLAR.md#k-04--crm-fatura-ekranı-sales-order)

Ekran **sales order** üzerine kurulacak, UI'da **"Sales Orders / Siparişler"** olarak adlandırılacak.
"Fatura" denmeyecek. Gerçek `invoice` entity'si için CRM collector genişletmesi **backlog'da**.

---

## Arka plan: neden sales order

Elimizdeki CRM discovery tabloları:
`discovery_crm_accounts`, `discovery_crm_products`, `discovery_crm_salesorders`,
`discovery_crm_salesorderdetails`, `discovery_crm_pricelevels`, `discovery_crm_productpricelevels`

> **`invoice` entity'si toplanmıyor.** Bu yüzden ekran sipariş üzerine kuruluyor (K-04).
> `invoice` + `invoicedetail` toplanması istenirse ayrı bir collector işi açılacak.

Mevcut kapsam kuralı: **ADR-0010 — CRM realized sales only**. Müşteri metrikleri yalnızca
`PRJ-*` proje siparişlerini topluyor (`crm_sales.py` başındaki not).

## Mevcut durum

| Katman | Yer |
|---|---|
| Sorgular | `services/customer-api/app/db/queries/crm_sales.py` (`SALES_SUMMARY`, sipariş satırları, aktif siparişler) |
| Servis | `services/customer-api/app/services/sales_service.py` |
| Router | `services/customer-api/app/routers/sales.py` |
| Mevcut endpoint'ler | `/customers/{name}/sales/summary`, `/sales/items`, `/sales/efficiency`, `/sales/efficiency-by-category`, `/sales/catalog-valuation` |
| UI | `src/pages/customer_view.py` (CRM YTD satış bloğu), `src/pages/customers_list.py` |
| Ölçüler | `ytd_order_count`, `active_order_count`, `active_order_value`, `lifetime_order_count` |

Kolonlar (`discovery_crm_salesorders`): `salesorderid`, `ordernumber`, `customerid`, `statecode`,
`statecode_text`, `totalamount`, `submitdate`, `fulfilldate`, `createdon`, `modifiedon`,
`transactioncurrency_text`

## Tasarım — "manuel güncelle" akışı

Otomatik proje güncellemesi yok; kullanıcı tetikleyecek:

```
Customer View › "Faturalar / Siparişler" sekmesi
  ├─ Liste: ordernumber · tarih · durum · tutar · para birimi · satır sayısı
  ├─ [Güncelle] butonu  → POST /api/v1/customers/{name}/sales/refresh
  │     - crm-engine / customer-api ilgili müşterinin CRM cache'ini invalide eder
  │     - discovery_crm_* tablolarından yeniden okur
  │     - "son güncelleme" zaman damgasını gui tablosuna yazar
  └─ Satır tıklanınca: sipariş detayı (salesorderdetails satırları, ürün, miktar, birim, tutar)
```

Ek olarak **"son senkron zamanı"** rozeti: `discovery_crm_salesorders.collection_time`'ın maksimumu.
Kullanıcı verinin ne kadar taze olduğunu görmeli.

## Yapılacaklar

- [x] ~~Karar: invoice mı sales order mı~~ → **K-04: sales order**
- [ ] Backend: `GET /customers/{name}/sales/orders` (liste) ve `GET /customers/{name}/sales/orders/{id}` (detay)
- [ ] Backend: `POST /customers/{name}/sales/refresh` — müşteri bazlı cache invalidation + yeniden hesap
      (mevcut `mapping_cache_invalidator.py` / `admin_cache.py` desenini kullanın; **global refresh çağırmayın**)
- [ ] Frontend: Customer View'a "Faturalar" sekmesi + tablo + detay drawer + Güncelle butonu
- [ ] Yetki: `permission_catalog.py`'ye `sec:customer:invoices` düğümü; müşteri rolü için görünürlük kararı
      (**TASK-13 ile birlikte** — müşteri kendi faturasını görecek, altyapısını görmeyecek)
- [ ] "Son güncelleme" ve "son CRM senkronu" göstergeleri
- [ ] Rate limit: Güncelle butonu müşteri başına örn. 60 sn'de bir (buton disable + geri sayım)
- [ ] Loading UX: buton spinner (full-page skeleton **değil** — `docs/LOADING_UX_DESIGN.md` §2)

## Doğrulama SQL'leri

```sql
-- 1) invoice entity'si var mı? (karar için kritik)
SELECT table_name FROM information_schema.tables
WHERE table_schema='public' AND table_name ILIKE '%crm%' ORDER BY 1;

-- 2) Bir müşterinin siparişleri (accountid ile)
SELECT so.ordernumber, so.statecode_text, so.totalamount, so.transactioncurrency_text,
       so.submitdate, so.fulfilldate, so.modifiedon,
       COUNT(d.salesorderdetailid) AS satir_sayisi
FROM   discovery_crm_salesorders so
LEFT   JOIN discovery_crm_salesorderdetails d ON d.salesorderid = so.salesorderid
WHERE  so.customerid = :accountid
GROUP  BY 1,2,3,4,5,6,7
ORDER  BY so.submitdate DESC NULLS LAST;

-- 3) Sipariş detayı
SELECT p.productnumber, p.name AS urun, d.quantity, d.uomid_name,
       d.priceperunit, d.extendedamount
FROM   discovery_crm_salesorderdetails d
LEFT   JOIN discovery_crm_products p ON p.productid = d.productid
WHERE  d.salesorderid = :salesorderid
ORDER  BY d.extendedamount DESC;

-- 4) Veri tazeliği
SELECT MAX(collection_time) AS son_crm_senkron,
       now() - MAX(collection_time) AS gecikme
FROM   discovery_crm_salesorders;

-- 5) PRJ-* kapsamı dışında sipariş var mı (ADR-0010 kapsam kontrolü)
SELECT CASE WHEN ordernumber LIKE 'PRJ-%' THEN 'PRJ' ELSE 'diger' END AS tip,
       COUNT(*), SUM(totalamount)
FROM   discovery_crm_salesorders WHERE statecode = 0 GROUP BY 1;
```

## Kabul kriterleri
- [x] "Fatura" tanımı karara bağlanmış (K-04)
- [ ] Müşteri kendi sipariş/fatura listesini görebiliyor; başka müşterininkini göremiyor (yetki testi)
- [ ] Güncelle butonu yalnızca o müşterinin cache'ini yeniliyor (global refresh tetiklenmiyor — log ile kanıt)
- [ ] Liste toplamı = doğrulama SQL toplamı
- [ ] "Son güncelleme" ve "son CRM senkronu" ekranda görünüyor
- [ ] Buton spam'i engelleniyor

## Cursor / Claude Code prompt

```
Bağlam: task/GUI/00-ortam-ve-dogrulama-rehberi.md, task/query-map/10-customer-crm.md,
datalake-platform-knowledge-base/adrs/ADR-0010-crm-realized-sales-only-scope.md,
services/customer-api/app/db/queries/crm_sales.py, services/customer-api/app/routers/sales.py,
services/customer-api/app/services/{sales_service.py,mapping_cache_invalidator.py},
src/pages/customer_view.py, docs/LOADING_UX_DESIGN.md

Görev: Müşterilerin CRM faturalarını (sipariş) görebileceği ve manuel güncelleyebileceği akış.

KARAR K-04: Ekran sales order üzerine kurulacak, UI'da "Sales Orders" olarak adlandırılacak.
"Invoice"/"Fatura" kelimesini UI'da kullanma. Yine de bir kez information_schema ile
discovery_crm_invoice* var mı doğrula ve raporla (varsa haber ver, yine de sales order ile devam et).

1. Backend:
   - GET /api/v1/customers/{customer_name}/sales/orders  (liste: ordernumber, tarih, durum,
     tutar, para birimi, satır sayısı; sayfalama destekli)
   - GET /api/v1/customers/{customer_name}/sales/orders/{salesorderid} (satır detayı)
   - POST /api/v1/customers/{customer_name}/sales/refresh
     -> SADECE o müşterinin cache anahtarlarını invalide eder (mapping_cache_invalidator desenini kullan),
        global admin/cache/refresh'i ÇAĞIRMA. Son güncelleme zamanını döner.
2. Frontend: customer_view.py'ye "Invoices / Orders" sekmesi. Tablo + satır tıklayınca detay drawer.
   Sağ üstte [Refresh] butonu (spinner, 60 sn cooldown) ve "Last synced: X ago" rozeti.
3. Yetki: src/auth/permission_catalog.py'ye sec:customer:invoices düğümü ekle.
4. tests/: yetki izolasyonu (müşteri A, müşteri B'nin siparişini göremez) ve refresh'in
   yalnızca hedef anahtarları sildiği için unit/integration test.

Kısıt: ADR-0010 kapsamı (PRJ-* realized sales) korunacak; kapsam değişikliği yapılacaksa ayrı ADR gerekir.
```
