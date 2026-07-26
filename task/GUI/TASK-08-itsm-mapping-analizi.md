# TASK-08 — ITSM Mapping Analizi

**Tip:** Analiz · **Efor:** ? · **Durum: NETLEŞTİRİLECEK** — kapsam belirsiz, önce istek toplama

## Hedef (bilinen kadarıyla)
ITSM mapping analizi süreci gözden geçirilecek. Kapsam ve beklentiler netleştirilmeli.

## Toplantıda sorulacaklar

1. Çıktı ne? **Rapor** mu, **otomatik eşleştirme** mi, **ekran** mı?
2. Hangi eşleştirme kastediliyor?
   - ITSM kullanıcısı → müşteri (bugün e-posta domain zinciri ile, ADR-0009)
   - ITSM ticket → CRM hizmet kalemi / ürün
   - ITSM ticket → altyapı varlığı (VM/host)
3. Başarı ölçütü ne — eşleşme oranı mı, SLA raporu mu?
4. Kim kullanacak (operasyon / müşteri / yönetim)?

## Mevcut durum — ITSM tarafında ne var

| Katman | Yer |
|---|---|
| Tablolar | `discovery_servicecore_users`, `discovery_servicecore_incidents`, `discovery_servicecore_servicerequests` |
| Sorgular | `services/customer-api/app/db/queries/itsm.py` |
| Servis | `services/customer-api/app/services/itsm_service.py` |
| Router | `services/customer-api/app/routers/itsm.py` |
| Eşleştirme | `data_source='itsm_servicecore'` (`gui_crm_customer_source_mapping`) |
| Mimari karar | **ADR-0009 — ServiceCore customer resolution: e-posta domain zinciri** |
| Önceki iş | `task/customer-itsm/sprint_1.md` |
| Doküman | `task/query-map/10-customer-crm.md` (ITSM bölümü) |

Kolonlar:
- `discovery_servicecore_incidents`: `ticket_id`, `org_user_id`, `subject`, `state_text`, `status_name`,
  `priority_name`, `category_name`, `created_date`, `target_resolution_date`, `closed_and_done_date`, `is_deleted`
- `discovery_servicecore_users`: `user_id`, `full_name`, `email`, `is_enabled`, `soft_deleted`

## Ön analiz (toplantıdan önce çalıştırılabilir — tartışmayı somutlaştırır)

```sql
-- 1) ITSM hacmi ve dağılımı
SELECT date_trunc('month', created_date) AS ay,
       COUNT(*) FILTER (WHERE NOT is_deleted) AS incident,
       COUNT(DISTINCT org_user_id)            AS tekil_kullanici
FROM   public.discovery_servicecore_incidents
WHERE  created_date > now() - interval '12 months'
GROUP  BY 1 ORDER BY 1;

-- 2) Eşleşme oranı: ticket -> kullanıcı -> e-posta domaini
SELECT COUNT(*) AS toplam_ticket,
       COUNT(u.user_id) AS kullanici_bulundu,
       COUNT(NULLIF(split_part(u.email,'@',2),'')) AS domain_var,
       ROUND(100.0*COUNT(NULLIF(split_part(u.email,'@',2),''))/NULLIF(COUNT(*),0),1) AS domain_orani_pct
FROM   public.discovery_servicecore_incidents i
LEFT   JOIN public.discovery_servicecore_users u ON u.user_id = i.org_user_id
WHERE  i.created_date > now() - interval '6 months' AND NOT i.is_deleted;

-- 3) En çok ticket üreten domainler (müşteri eşleşmesi kurulacak aday liste)
SELECT lower(split_part(u.email,'@',2)) AS domain, COUNT(*) AS ticket
FROM   public.discovery_servicecore_incidents i
JOIN   public.discovery_servicecore_users u ON u.user_id = i.org_user_id
WHERE  i.created_date > now() - interval '6 months' AND NOT i.is_deleted
GROUP  BY 1 ORDER BY 2 DESC LIMIT 50;

-- 4) Bu domainlerin kaçının tanımlı kuralı var (bulutwebui)
SELECT match_value, COUNT(*) FROM gui_crm_customer_source_mapping
WHERE data_source = 'itsm_servicecore' GROUP BY 1 ORDER BY 2 DESC;

-- 5) Kategori dağılımı (ticket -> hizmet kalemi eşlemesi için hammadde)
SELECT category_name, COUNT(*) FROM public.discovery_servicecore_incidents
WHERE created_date > now() - interval '6 months' AND NOT is_deleted
GROUP BY 1 ORDER BY 2 DESC LIMIT 40;
```

## Öneri: bu haftaki iş = analiz raporu, kod değil

- [ ] Yukarıdaki 5 sorguyu çalıştırıp **eşleşme oranı raporu** üret
- [ ] Eşleşmeyen domainleri "aksiyon listesi" olarak çıkar (hangi müşterilere bağlanmalı)
- [ ] `category_name` dağılımını CRM ürün aileleriyle yan yana koy → ticket↔hizmet eşlemesi mümkün mü göster
- [ ] Bulguları toplantıya götür, kapsamı orada kilitle, sonra TASK-08b olarak uygulama planı yaz

## Cursor / Claude Code prompt (analiz fazı)

```
Bağlam: task/GUI/00-ortam-ve-dogrulama-rehberi.md, task/query-map/10-customer-crm.md,
datalake-platform-knowledge-base/adrs/ADR-0009-servicecore-customer-resolution-email-domain-chain.md,
services/customer-api/app/db/queries/itsm.py, task/customer-itsm/sprint_1.md

Görev: ITSM mapping'in mevcut durumunu ölç ve rapor üret. KOD DEĞİŞİKLİĞİ YAPMA.

scripts/analyze_itsm_mapping.py yaz:
1. Son 6/12 aylık incident + service request hacmi
2. ticket -> user -> email domain zincirinin her adımındaki kayıp oranı (funnel)
3. Eşleşmeyen top 50 domain ve ticket sayıları
4. gui_crm_customer_source_mapping'te itsm_servicecore kuralı olan/olmayan müşteriler
5. category_name dağılımı ile CRM ürün aileleri (shared/matching/product_matching_registry.yaml)
   arasında olası eşleşme önerisi (isim benzerliği, sadece öneri listesi)

Çıktı: task/GUI/reports/itsm-mapping-analizi.md (markdown tablolar + funnel + aksiyon listesi).
Rapor sonunda "netleştirilmesi gereken sorular" bölümü olsun.
```
