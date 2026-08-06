# Tanım Soruları — Offsite Disk (S3), Backup ve Yönetim Hizmetleri

**Tarih:** 06.08.2026 · **İş:** TASK-94 · **Hazırlayan:** Datalake ekibi
**Muhatap:** Bulutistan ürün/satış tarafı · **Cevap beklenen tarih:** 13.08.2026

## Bu doküman nasıl okunur

CRM'deki bazı ürünlerin **envanterde ne anlama geldiği** tanımlı değil. Bu yüzden
GUI'de aynı ürün bazı ekranlarda Storage, bazı ekranlarda Backup sayılıyor; bazı
hizmet bedelleri ise kapasitenin içine toplanıyor.

Her soruda dört şey var:

1. **Bugün ne yapıyoruz** — mevcut sistemin davranışı,
2. **Veri ne diyor** — CRM'den ölçülen gerçek ağırlık,
3. **Önerimiz** — cevap gelmezse uygulayacağımız varsayılan,
4. **Cevap farklıysa ne değişir.**

Önerileri yazmamızın sebebi: **cevap gecikirse iş durmasın.** 13.08'e kadar cevap
gelmeyen sorularda önerdiğimiz varsayılanı uygulayıp ekranı öyle kuracağız.

## Veri temeli

Kaynak: `bulutlake` CRM tabloları (`discovery_crm_products`,
`discovery_crm_salesorderdetails`, `discovery_crm_salesorders`), veri tazeliği
**06.08.2026 13:59**.

> **Önemli kapsam uyarısı:** CRM'den bize akan veride **474 siparişin tamamı
> `Active`** durumda; iptal/kapanmış sipariş ve sipariş tarihi (`submitdate`)
> kaydı gelmiyor. Bu yüzden aşağıdaki "0" değerleri **"bugün aktif hiçbir
> siparişte yok"** demektir, "hiç satılmadı" değil. Katalogdaki 275 üründen
> yalnız 99'u aktif siparişlerde görünüyor.

### Ölçüm — sorulara konu ürünler

| Ürün | No | Birim | Satır | Miktar | Müşteri |
|---|---|---|---:|---:|---:|
| Hyperconverged İmaj Yedekleme Hizmeti | 000BLT-45 | GB | 418 | **1.673.782** | **315** |
| Klasik Mimari İmaj Yedekleme (Veritas NetBackup) | 000BLT-203 | GB | 16 | 56.275 | 15 |
| Uygulama Yedekleme Hizmeti (NetBackup) | 000BLT-142 | GB | 10 | 24.599 | 10 |
| **Offsite Backup Disk Alanı (S3)** | 000BLT-70 | GB | **0** | **0** | **0** |
| **Offsite Backup Disk Alanı (Veeam)** | 000BLT-71 | GB | **0** | **0** | **0** |
| Remote Backup Hizmeti (Nutanix) | 000BLT-221 | GB | 0 | 0 | 0 |
| IBM ICOS S3 Hizmeti | 000BLT-57 | **Adet** | 4 | 156 | 4 |
| IBM ICOS S3 İstanbul | 000BLT-56 | TB | 2 | 2 | 2 |
| IBM ICOS S3 Ankara | 000BLT-55 | TB | 1 | 8 | 1 |
| Veeam Replikasyon Yönetim Hizmeti | 000BLT-151 | Adet | 6 | 243 | 5 |
| Zerto Replikasyon Yönetim Hizmeti | 000BLT-167 | Adet | 7 | 18 | 6 |
| MS Windows Lisans | 009LT-13 | per VM | 296 | 1.294,4 | 226 |
| Standart Windows İşletim Sistemi Yönetim Hizmeti | 000BLT-137 | per VM | 168 | 743,1 | 132 |
| Veeam + Zerto Replication kapasite ürünleri (16 ürün) | — | GB / vCPU | **0** | **0** | **0** |
| Yeni yönetim hizmeti kataloğu `001SX-*` (Temel/Gelişmiş/Premium) | — | Adet / per VM | **0** | **0** | **0** |

---

## A. Offsite Disk (S3) ve object storage

### A1 — Offsite Backup ürünleri hâlâ satışta mı?

**Veri:** `000BLT-70` (S3) ve `000BLT-71` (Veeam) aktif hiçbir siparişte yok.
Aynı şekilde `000BLT-221` Remote Backup Hizmeti (Nutanix) de yok.
**Bugün:** Her ikisi de kural dosyalarında tanımlı, panellerde yer ayrılmış durumda.
**Soru:** Bu ürünler hâlâ satılabilir mi, yoksa katalogdan fiilen çekildi mi?
Offsite backup bugün müşteriye **hangi ürün** üzerinden satılıyor?
**Önerimiz:** Aktif satışı olmayan ürünü envanterde göstermeyiz; katalogda
görünür ama "satışta değil" etiketiyle işaretlenir.
**Farklıysa:** Ürün canlıysa A2 ve A3'ün cevabı da gerekir, aksi halde satış
başladığı gün ekranda yanlış yerde çıkar.

### A2 — Offsite Disk bir storage ürünü mü, backup ürünü mü?

**Bugün:** Sistem kendi içinde çelişiyor. `embedded_rules.json:224` bu ürünü
**Storage › Object Storage** sayıyor; `panel_mapping.py:104` ve matching registry
**Backup › Offsite** sayıyor. Yani müşteri bu ürünü aldığında hangi sekmede
görüneceği ekrana göre değişiyor.
**Soru:** Müşteri "Offsite Backup Disk Alanı (S3)" satın aldığında bunu Storage
tüketimi olarak mı, Backup tüketimi olarak mı raporlamalıyız?
**Önerimiz:** Backup › Offsite. (Ürün adı "Backup" diyor ve amacı yedek saklamak.)
**Farklıysa:** Storage toplamları değişir; S3 kapasite raporu bu GB'leri de içerir.

### A3 — "IBM ICOS S3 Hizmeti"nin 1 adedi nedir?

**Veri:** `000BLT-57` **Adet** ile satılmış (156 adet, 4 müşteri); buna karşılık
`IBM ICOS S3 Ankara` ve `İstanbul` **TB** ile satılmış (toplam 10 TB, 3 müşteri).
**Bugün:** Üç ürün tek kovaya (`storage_s3`) atılıyor; `000BLT-57`'nin ise hiçbir
panelde karşılığı yok — yani satılmış olmasına rağmen hiçbir ekranda görünmüyor.
**Soru:** 1 "Adet" S3 hizmeti ne demek — bir bucket mı, bir vault mı, sabit kotalı
bir paket mi? Bu üç ürün aynı hizmetin farklı satış biçimi mi, ayrı hizmetler mi?
**Önerimiz:** "Hizmet" satırını kapasitesiz servis bedeli sayıp kapasiteye
toplamayız; kapasite yalnız TB ile satılan Ankara/İstanbul satırlarından gelir.
**Farklıysa:** Adet↔TB çevrim kuralı verilirse S3 satılan kapasitesi ~10 TB'dan
çok daha yukarı çıkar.

### A4 — "Bulut Depolama" adlı ürün ne oldu?

**Bugün:** `embedded_rules.json:224` kuralı "Bulut Depolama" adlı bir ürünü de S3
kovasına atıyor.
**Veri:** CRM kataloğunda bu isimde ürün **yok**.
**Soru:** Bu ürün kaldırıldı mı, adı mı değişti, yoksa başka bir CRM'de mi duruyor?
**Önerimiz:** Kuralı geçersiz sayıp temizleriz.
**Farklıysa:** Ürün başka isimle yaşıyorsa doğru adını verin, eşlemeyi ona bağlayalım.

---

## B. Backup alanları

### B1 — En büyük backup ürünümüz ne anlama geliyor? *(öncelikli)*

**Veri:** `000BLT-45` Hyperconverged İmaj Yedekleme Hizmeti = **1,67 PB, 315
müşteri**. Bu, tüm backup ürünleri içinde açık ara en büyüğü — ikincisinin
(NetBackup imaj, 56 TB) yaklaşık **30 katı**.
**Bugün:** Bu ürün CRM Inventory ekranında **gizli**. Sistemdeki not:
*"HC image sellable clarified olana kadar gizli"*. Ayrıca kural dosyası bunu
yedekleme değil, **sanallaştırma storage'ı** sayıyor.
**Soru:** Satılan bu GB nedir — müşteriye tahsis edilen yedek alanı mı, yoksa
VM disk boyutu × snapshot policy'den **hesaplanan** bir değer mi? Müşteri bu
alanı ayrıca mı satın alıyor, sanallaştırma paketinin içinde mi geliyor?
**Önerimiz:** Satılan yedek alanı kabul edip Backup sekmesinde gösteririz.
**Farklıysa:** Hesaplanan bir değerse kapasite olarak satılmış sayılamaz; o zaman
Backup toplamından çıkar ve ekrandaki en büyük kalem yeniden tanımlanır.

### B2 — Satılan GB, dedup ve compression'ın öncesi mi sonrası mı?

**Bugün:** Tanım yok; satılan GB ile altyapıda ölçtüğümüz GB doğrudan
karşılaştırılıyor.
**Soru:** Müşteriye faturalanan GB, kaynak veri boyutu mu (dedup öncesi), yoksa
repository'de kapladığı gerçek alan mı (dedup + compression sonrası)?
**Önerimiz:** Faturalanan değer = dedup sonrası kabul ederiz.
**Farklıysa:** "Satılan vs kullanılan" oranı sistematik olarak yanlış çıkar —
bu soru cevaplanmadan backup doluluk grafiği güvenilir olmaz.

### B3 — Replikasyon artık kapasiteyle satılmıyor; envanterde neye göre gösterelim?

**Veri:** Klasik ve Hyperconverged mimarideki **16 replication kapasite ürününün
(vCPU/RAM/Disk) hiçbiri** aktif siparişte yok. Buna karşılık satılan şeyler:
Veeam Replikasyon Yönetim Hizmeti (243 adet / 5 müşteri), Zerto Replikasyon
Yönetim Hizmeti (18 adet / 6 müşteri), Veeam Cloud Connect Replication Lisansı
(233 per VM / 2 müşteri), Zerto Enterprise License (11 adet / 5 müşteri).
**Bugün:** Sistem replikasyonu **kapasite** (vCPU/RAM/GB) olarak modellemiş;
satılan tarafta o kalemler boş olduğu için panel sürekli sıfır gösteriyor.
**Soru:** (a) Replikasyon bugün VM başına hizmet + lisans olarak mı satılıyor?
(b) Replikasyonu **Backup** başlığı altında mı, ayrı bir **DR** başlığı altında mı
raporlamalıyız?
**Önerimiz:** (a) Satılan replikasyonu **VM adedi** üzerinden gösteririz, kapasite
üzerinden değil. (b) DR olarak ayrı gösteririz — replikasyon geri dönülebilir bir
restore point üretmiyor.
**Farklıysa:** Kapasite satışı devam ediyorsa hangi üründen okunacağını söyleyin.

### B4 — Bir backup ürününde "kullanım" nedir?

**Bugün:** Ürüne göre değişiyor; ortak bir tanım yok.
**Soru:** "Müşteri satın aldığının ne kadarını kullanıyor?" sorusunun cevabı
hangisi olmalı: (a) korunan VM sayısı, (b) repository'de kapladığı alan,
(c) geçerli restore point'i olan VM sayısı? Ayrıca offsite kopyanın tüketimi
**kaynak DC'ye mi, hedef DC'ye mi** yazılmalı?
**Önerimiz:** Ana ölçü (c) geçerli restore point'i olan VM sayısı, ikincil ölçü
(b) kapasite. Offsite tüketimi kaynak DC'ye yazılır.
**Farklıysa:** Backup KPI'ının tamamı bu cevaba göre kurulacak.

---

## C. Yönetim hizmetleri (Veeam, Zerto, Windows)

### C1 — Windows lisansı ile Windows yönetim hizmeti 1:1 değil

**Veri:** Windows ürünlerinden en az biri olan 268 müşterinin dağılımı:

| Durum | Müşteri | Lisans | Yönetim |
|---|---:|---:|---:|
| Sadece lisans var | 136 | 846,3 | — |
| **Eşit (1:1)** | **74** | 329,0 | 329,0 |
| **Sadece yönetim hizmeti var** | **42** | — | 278,0 |
| Yönetim fazla | 9 | 38,1 | 108,0 |
| Lisans fazla | 7 | 81,0 | 28,1 |

**Bugün:** Kodumuz "lisans ve yönetim hizmeti aynı adette gelir, bu yüzden
toplanmamalı" varsayımıyla çalışıyor. Veri bunu doğrulamıyor — müşterilerin
yalnız **%28'inde** iki değer eşit.
**Soru:** (a) Windows yönetim hizmeti, lisans olmadan satılabilir mi (müşterinin
kendi lisansı / BYOL)? 42 müşteride durum bu. (b) "Bu müşterinin kaç Windows VM'i
var?" sorusunda hangi kalem otoritedir?
**Önerimiz:** Lisans otoritedir; yönetim hizmeti ayrı satır olarak gösterilir ve
ikisi **asla toplanmaz**.
**Farklıysa:** Windows VM sayısı ekranda 743 ile 1.294 arasında değişir.

### C2 — Yönetim hizmetinde "1 Adet" ne demek?

**Veri:** Veeam Replikasyon Yönetim Hizmeti 243 adet / 5 müşteri; Zerto
Replikasyon Yönetim Hizmeti 18 adet / 6 müşteri. Aynı birim, çok farklı ölçek.
**Bugün:** Her iki ürün de "satılan miktar kaydedilir, altyapı ile karşılaştırılmaz"
statüsünde duruyor; Zerto satırında karşılaştırma kaynağı hiç tanımlı değil.
**Soru:** 1 adet = 1 VM mi, 1 replikasyon job'u mu, 1 site/VPG mi? Veeam ile Zerto
için aynı şeyi mi ifade ediyor?
**Önerimiz:** Veeam'de VM, Zerto'da VPG kabul ederiz.
**Farklıysa:** Bu birim tanımlanmadan yönetim hizmetinin altyapı karşılığı
ölçülemez; ürün "sold-only" kalır.

### C3 — Yönetim hizmeti bedeli kapasiteye eklenmeli mi?

**Bugün:** `embedded_rules.json:225-226` kuralları, adında "Veeam" veya "Zerto"
geçen her şeyi ilgili teknolojinin **kapasitesine** topluyor. Bu yüzden
"Veeam Replikasyon Yönetim Hizmeti" bedeli, satılan Veeam kapasitesi gibi
görünüyor.
**Soru:** Yönetim hizmetleri kapasite midir, hizmet bedeli midir?
**Önerimiz:** Hizmet bedelidir; kapasiteye **asla** toplanmaz, envanterde ayrı bir
"Yönetim Hizmetleri" grubunda gösterilir.
**Farklıysa:** Gruplama ve toplama kuralını size göre kurarız.

### C4 — İki paralel yönetim hizmeti kataloğu var; hangisi geçerli?

**Veri:** Katalogda aynı hizmetin iki seti duruyor:
- Eski set (`000BLT-13x`): "Standart Windows İşletim Sistemi Yönetim Hizmeti",
  "Standart Intel Linux…", "SUSE for SAP HANA…" → **satılıyor** (132 + 20 + 21 müşteri).
- Yeni set (`001SX-*`): "Windows İşletim Sistemi Yönetimi — Temel / Gelişmiş /
  Premium", "Yedekleme Yönetimi — Temel/Gelişmiş/Premium", "SOC/SIEM Yönetim
  Hizmeti — Temel/Gelişmiş/Premium" → **hiçbiri aktif siparişte yok**.

**Bugün:** Konfigürasyonumuz her iki seti de tanıyor; ekran etiketleri yeni sete
göre yazılmış, gerçek satış ise eski sette. Bu yüzden satılan yönetim hizmetleri
ekranda beklenenden farklı adlarla eşleşebiliyor.
**Soru:** Yeni kademeli set eskisinin yerini mi alacak? Alacaksa geçiş ne zaman?
Envanter ekranını hangi sete göre kuralım?
**Önerimiz:** Eski seti canlı, yeni seti "katalogda var, satışta yok" kabul ederiz.
**Farklıysa:** Yeni set devreye girecekse Temel/Gelişmiş/Premium kademelerinin
envanterde ayrı mı gösterileceğini de belirtmeniz gerekir.

---

## Cevaplar geldiğinde ne olacak

Her cevap, ürünün tanım kaydına (`product_matching_registry`) tek satır olarak
işlenir: ürün hangi başlık altında, hangi birimle, hangi altyapı kaynağıyla
karşılaştırılacak. Ekran değişiklikleri TASK-99 kapsamında uygulanır.

Cevapsız kalan sorularda yukarıdaki **Önerimiz** satırları yürürlüğe girer ve
ekranda "varsayımla hesaplandı" notuyla işaretlenir.

## Ek — bu dokümanı hazırlarken sormadıklarımız

Aşağıdakileri kendi verimizden cevapladık, sizi meşgul etmiyoruz: hangi ürünlerin
aktif siparişi var, hangi birimle satılıyorlar, kaç müşteriyi ilgilendiriyorlar,
Windows lisans/yönetim dağılımı, replikasyon kapasite ürünlerinin boş olduğu.
