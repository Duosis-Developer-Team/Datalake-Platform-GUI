# Colocation Configuration — rack rolü bazlı sellable U ayarı

**Tarih:** 2026-08-04
**Durum:** tasarım onaylandı (Arca, 2026-08-04)
**Dal:** `worktree-sellable-u-role-filter`
**İlgili:** `docs/superpowers/specs/2026-07-27-colocation-allocation-model-design.md` (allocation modeli),
commit `7cd4c9e2` / `c0a7398e` / `364536e5` (8. şikâyet — sellable U'dan customer + network kabinlerinin çıkarılması)

---

## 1. Problem

`shared/colocation/allocation.py` içindeki `NON_SELLABLE_ROLE_IDS` sabiti, sellable colocation U
hesabına hangi rack rolünün gireceğini **kodda** belirliyor. Bu bir iş kararı; değiştirmek için
bugün deploy gerekiyor.

Müşteri talebi (Arca, 2026-08-04): operatörler hangi Loki rack rolünün sellable hesabından hariç
tutulacağını **ekrandan** ayarlayabilsin. Bugünkü davranış varsayılan olarak korunsun, ileride
değiştirilebilsin.

Sabitin beslediği iki tüketici var:

| Tüketici | Fonksiyon | Ekrandaki karşılığı |
|---|---|---|
| `sellable_service._query_colocation_totals` | `sellable_rack_totals(rows)` | CRM sellable `dc_hosting_u` paneli (total × %80 − allocated → TL) |
| `colocation_matching_service._fetch_colocation` | `aggregate_rack_allocations(rows)` | DC Colocation kartı: `sellable_free_u`, `role_breakdown`, `free_u_potential_tl` |

Üçüncü bir kullanım daha var ama **kapsam dışı**: `is_colocation_rack()` / `COLOCATION_ROLE_IDS`
(rol 3 ve 4), "bu kabin hangi müşteriye ait" sorusunu cevaplıyor. Onu oynatmak kabinleri müşteriler
altında yeniden dosyalar; bu işin konusu değil.

## 2. Ölçülmüş gerçeklik (canlı, 2026-08-04)

Rol kataloğu `loki_racks (role_id, role_name)`'den doğrulandı — tam 4 rol var, "generic rack" diye
bir rol yok; konuşmada "generic" denen şey **NON-STANDART RACK (rol 3)**:

| role_id | role_name | kabin | Σ u_height (ham) |
|---|---|---|---|
| 1 | NETWORK RACK | 42 | 1.930 |
| 2 | HOST RACK | 139 | 6.408 |
| 3 | NON-STANDART RACK | 7 | 294 |
| 4 | CUSTOMER RACK | 46 | 2.113 |

Varsayılanın `{1,3,4}` mi `{1,4}` mü olacağı ölçülerek karara bağlandı (188 de-duplike kabin):

| | excluded = 1,3,4 | excluded = 1,4 |
|---|---|---|
| Global sellable free U | 3.503 | 3.800 |
| Engine sellable U | 2.575,2 | 2.805,4 |
| DC13 sellable free U | 272 | 537 |

Aradaki 297 U'nun kaynağı: rol 3'teki 7 kabinin 6'sı DC13'te **Sabancı DX'in colocation alanı**
(`303,304,305,307,308` → tenant "SABANCI DX"; `306` → tag "SABANCI DX CO LOCATION"), 7'si DC14'te
`B3-15`. Rol 3 zaten `COLOCATION_ROLE_IDS` içinde olduğu için bu kabinler "müşteriye tahsisli"
sayılıyor. Sellable'a alınırsa **aynı U hem tahsisli hem satılabilir** görünür — 8. şikâyette
düzeltilen çift sayımın aynısı.

**Karar:** varsayılan `{1, 3, 4}` excluded (bugünkü davranış). Rol 3 ekrandan açılabilir kalır,
ama açılırken §8'deki uyarı çıkar.

## 3. Kapsam

**Dahil:**
- Rol bazlı sellable/excluded ayarı, **global** (platform geneli, tek ayar seti).
- Administration → Integration and Configuration → NetBox/Loki altında yeni sub-tab.
- Cache doğruluğu: ayar değişince hiçbir yerde bayat sayı kalmaması.

**Hariç:**
- **DC bazlı istisna.** İlk tasarımda vardı, Arca'nın kararıyla çıkarıldı (2026-08-04): ayar tek
  ve global. DC'ye özel kural gerekirse ayrı bir iş olarak konuşulur; veri modeli buna kapalı değil
  (§4'teki nota bak) ama bu specin kapsamında yok.
- `COLOCATION_ROLE_IDS` (müşteri atfı) — sabit kalır.
- Rol *tanımlama*; katalog Loki'nin, biz sadece okuruz.
- Fiziksel Total/Used/Free U tile'ları — bunlar fiziksel gerçek, ayardan etkilenmez.

## 4. Veri modeli

`services/customer-api/migrations/webui/047_colocation_role_rule.sql` (bulutwebui, NiFi'nin
görmediği GUI ayar veritabanı — `gui_netbox_viz_exclusion` ile aynı yer):

```sql
CREATE TABLE IF NOT EXISTS gui_colocation_role_rule (
    role_id    TEXT PRIMARY KEY,
    sellable   BOOLEAN NOT NULL,
    notes      TEXT,
    updated_by TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Seed (bugünkü davranış, `ON CONFLICT DO NOTHING` — mevcut kurulumu ezmez):

```sql
('1',FALSE), ('2',TRUE), ('3',FALSE), ('4',FALSE)
```

Tasarım notları:

- `role_id` **TEXT**: `discovery_loki_rack.role_id` bir VARCHAR kolonu; int'e çevirip karşılaştırmak
  allocation modülünün bilerek kaçındığı bir varsayım.
- Rol başına tek satır, DC kolonu yok. İleride DC bazlı istisna istenirse `dc TEXT NOT NULL
  DEFAULT '*'` kolonu + `UNIQUE (dc, role_id)` ile genişletilebilir; o zaman `'*'` global demek
  olur ve **NULL kullanılmaz** — Postgres UNIQUE, NULL'ları birbirinden farklı sayar, iki global
  satır yazılabilirdi. Bugün böyle bir kolon yok.

## 5. Kural nesnesi — `shared/colocation/role_rules.py`

DB bilmeyen, değişmez (frozen) küçük bir değer nesnesi:

```python
@dataclass(frozen=True)
class RoleRules:
    sellable: Mapping[str, bool]        # role_id -> sellable

    def is_sellable(self, role_id) -> bool
    @property
    def etag(self) -> str               # 8 hane, kural setinin hash'i
    @classmethod
    def from_rows(cls, rows) -> "RoleRules"

DEFAULT_RULES = RoleRules({"1": False, "2": True, "3": False, "4": False})
```

**Çözüm sırası:** rolün kaydı varsa o; **kaydı yoksa sellable.**

İkinci madde bugünkü `is_sellable_rack()` davranışının aynısı ve bilerek böyle: rol bilgisi hiç
taşımayan aggregate'ler var (Floor Map occupancy özeti), onları "satılamaz" saymak sayılarını
sessizce sıfırlar. Aynı sebeple `role_id` `None` veya tanınmayan bir değerse sellable kabul edilir.

**etag:** `(role_id, sellable)` çiftlerinin sıralanmış kanonik gösteriminin blake2s hash'inin ilk
8 hanesi. Sayaç değil hash olmasının sebebi: DB'ye elle müdahale edilse bile kendini toparlar,
satır sırasından etkilenmez, ve ayarı eski hâline döndürünce eski cache tekrar kullanılabilir hale
gelir.

**Geriye uyum:** `is_sellable_rack(role_id)` ve `NON_SELLABLE_ROLE_IDS` kalır, `DEFAULT_RULES`
üzerinden türetilir. Mevcut çağıranlar ve testler değişmeden çalışır.

### 5.1 İmza değişiklikleri

```python
sellable_rack_totals(rows, rules=DEFAULT_RULES)
aggregate_rack_allocations(rows, rules=DEFAULT_RULES)
```

Global state yok, modül seviyesinde mutable sabit yok: kural **parametre olarak** geçer. Böylece
bir isteğin kullandığı kural seti, o isteğin cache anahtarındaki etag ile aynı olur; bir worker'ın
belleğindeki eski sabit başka bir isteğin sayısını etkileyemez.

`role_breakdown` bucket'ları bugünkü şeklini korur (`role_id / role_name / sellable / rack_count /
capacity_u / used_u / free_u`, sellable'lar önce, sonra `-free_u`). Ayar global olduğu için bir
rolün `sellable` bayrağı tüm platformda tek anlam taşır; ek alan gerekmiyor.

## 6. API — customer-api

`app/services/colocation_role_rule_service.py` (webui pool üzerinden okuma/yazma + `load_rules()`),
`app/routers/colocation_config.py`:

```
GET /api/v1/colocation/role-rules   → {rules: [...], catalog: [...], etag, degraded}
PUT /api/v1/colocation/role-rules   → {rules: [{role_id, sellable}], notes}
```

- PUT **tam set** yazar (dört rolün dördü), tek rol değil: kısmi yazım, ekranda görülen hâl ile
  kaydedilen hâlin ayrışmasına açık kapı bırakır.
- **Katalog** (`role_id` + `role_name`) `loki_racks`'ten canlı okunur, sabit listeden değil: Loki'ye
  5. bir rol eklenirse sayfada kendiliğinden görünür. Kaydı olmayan rol §5'teki kurala göre
  **sellable** sayılır — yani yeni bir rol, operatör karar verene kadar sellable havuzunu büyütür.
  Bu bilinçli: bugünkü `is_sellable_rack()` de aynısını yapıyor ve tersi (yeni rolü sessizce
  satılamaz saymak) sayıyı sebepsiz düşürürdü. Ekranda bu roller "yeni — karar verilmedi"
  rozetiyle işaretlenir ki fark edilmeden kalmasın.
- **Önizleme sayıları** (kabin / capacity / free U) ayrı bir sorgu değil, kartın kullandığı **aynı**
  `role_breakdown` payload'ından gelir. Operatörün gördüğü ile kartın gösterdiği tanım gereği aynıdır.
- `load_rules()` process içinde 30 saniye memo'lanır; her istekte webui'ye gidilmez.

**Hata davranışı:** webui-db kapalıysa yazma `503`; okuma `DEFAULT_RULES`'a düşer ve payload
`degraded: true` taşır, ekranda kırmızı bant çıkar, kaydetme kapanır. Config yokluğu **asla**
"her şey satılabilir" diye yorumlanmaz — o yorum sellable U'yu sessizce şişirirdi.

## 7. Cache

Etkilenen üç cache: `colocation:{dc}` (customer-api, 6 saat), `sellable:panels:{dc}:*` (sellable
engine), `api:*` (GUI cevap cache'i).

**Mekanizma: etag anahtarda + kaydetmede flush.**

```
colocation:{dc}:{etag}
sellable:panels:{dc}:...:{etag}
```

Sadece flush'a güvenmek yetmiyor. `services/customer-api/app/core/cache_backend.py:87-100`'de
`cache_get`, Redis'te bulamazsa in-memory tier'a bakıyor ve orada bulursa değeri **`nx=True` ile
Redis'e geri yazıyor**. Yani bir worker Redis'i temizlese bile, başka bir worker'ın belleğindeki
eski değer Redis'e geri dolabiliyor — silinen sayı kendiliğinden geri geliyor. Etag anahtarda
olduğunda eski anahtar bir daha hiç sorulmaz, dolayısıyla geri de yazılamaz.

Flush yine de yapılır ama **hız için**: kaydetme sonrası `colocation:` prefix'i,
`invalidate_result_cache()` ve GUI tarafında `api:` prefix'i temizlenir ki sayı TTL beklemeden
değişsin. Doğruluğu etag garanti eder, flush sadece anındalık sağlar.

**Yan fayda:** deploy sonrası elle Redis flush'lama zorunluluğu kalkar (bkz. `364536e5` commit
mesajındaki uyarı) — etag zaten yeni anahtar üretir.

## 8. Ekran

**Yol:** `/administration/integrations/netbox/colocation`
**Permission:** yeni kod `page:settings_colocation_config`
**Navigasyon:** `shell.py`'a `NETBOX_TABS` eklenir (CRM/HMDL sub-nav kalıbının aynısı):
bugünkü sayfa "Filters", yenisi "Colocation Configuration". Breadcrumb:
`Administration › Integrations › NetBox / Loki`.

Bölümler:

1. **Etki kartı** — ayarın neyi değiştirdiğini yazar: DC Colocation kartındaki Sellable Free U, TL
   potansiyeli, CRM sellable `dc_hosting_u` paneli. Fiziksel Total/Used/Free U'nun **etkilenmediği**
   açıkça belirtilir.
2. **Rol tablosu** — rol başına bir satır, tek ve global:

   ```
   Role                  Racks   Capacity U   Free U    Sellable?
   HOST RACK (2)          139       6.408      3.503     [ ON  ]
   NETWORK RACK (1)        42       1.930          …     [ off ]
   NON-STANDART (3)         7         294        297     [ off ]
   CUSTOMER RACK (4)       46       2.113          …     [ off ]

   Sellable free U:  3.503  →  kaydedince: 3.800        [Kaydet]
   ```

   Alttaki önizleme switch'ler değiştikçe canlı hesaplanır — operatör kaydetmeden önce sayının ne
   olacağını görür. Racks / Capacity U kolonları §2'deki ölçümden; Free U kolonu `role_breakdown`'dan
   gelir (rol 2 → 3.503 ve rol 3 → 297 ölçüldü, diğer ikisi implementasyonda payload'dan doldurulur).
   Capacity ve Free U de-duplikasyon sonrası hesaplandığı için ham u_height toplamından farklı
   olabilir — DC13'te aynı kabinin iki farklı u_height ile göründüğü bilinen bir durum var
   (memory `netbox-rack-duplicate-heights`), dedupe MAX alır.

**İki koruma modalı** — ikisi de engellemez, sadece kararın bilerek verildiğinden emin olur:

- **Müşteriye tahsisli rol sellable yapılırsa** (rol 3 veya 4, yani `COLOCATION_ROLE_IDS` üyesi):
  "Bu rol müşteriye tahsisli kabinleri işaretliyor. Sellable yaparsan aynı U hem tahsisli hem
  satılabilir sayılacak (+297 U)." §2'deki çift sayım tam olarak bu.
- **Dört rol birden excluded yapılırsa**: sellable U platform genelinde 0 olur, panel ve TL
  potansiyeli sıfırlanır.

## 9. Test

Kural: her test bir cümleyle **hangi bozulmayı yakaladığını** söyleyebilmeli; söyleyemiyorsa
yazılmaz. Aşağıdakiler bu kapıdan geçenler.

**`shared/colocation/role_rules.py`**

| Test | Yakaladığı bozulma |
|---|---|
| Bilinmeyen/None rol sellable sayılır | Floor Map gibi rol taşımayan aggregate'lerin boş U'su sessizce sıfırlanır |
| etag satır sırasından bağımsız | Aynı kural farklı sırada okunduğunda etag değişirse cache her istekte ıskalar |
| Kural değişince etag değişir | Değişmezse ayar kaydedilir ama ekran eski sayıyı göstermeye devam eder |

**`shared/colocation/allocation.py`**

| Test | Yakaladığı bozulma |
|---|---|
| `rules` verilmezse bugünkü sayı çıkar | Varsayılan kayarsa canlı sellable U deploy anında sessizce değişir |
| Rol sellable yapılınca free U'su havuza girer | Kural okunuyor ama toplama uygulanmıyorsa ekran ayarı kaydeder, sayı değişmez |

**customer-api**

| Test | Yakaladığı bozulma |
|---|---|
| webui kapalıyken `DEFAULT_RULES`'a düşer | Config okunamayınca "her şey sellable" yorumlanırsa sellable U şişer |
| Yazma sonrası cache invalidation çağrılır | Kaydet'e basılır, sayı 6 saat değişmez |
| etag cache anahtarına girer | Farklı kural setleri aynı anahtarı paylaşır, bayat sayı servis edilir |

**GUI**

| Test | Yakaladığı bozulma |
|---|---|
| Switch'ler kayıtlı config'i yansıtır | Ekran her zaman varsayılanı gösterir, operatör kaydettiğini sanır |
| RBAC: yetkisiz kullanıcı access-denied görür | Ayar sayfası herkese açılır |
| Sub-nav iki tab gösterir | Yeni sayfaya link olmaz, sadece URL ile erişilir |

**Regression:** mevcut 128 colocation testi yeşil kalır; migration seed'i bugünkü kuralı yazdığı için
canlı DC13 deploy öncesi ve sonrası **272** sellable free U okumalıdır. Bu ölçüm testin yerine
geçmez, testlerin doğru şeyi ölçtüğünün kanıtıdır.

## 10. Uygulama sırası (katman katman commit)

1. `shared/colocation/role_rules.py` + `allocation.py` imzaları + testleri
2. Migration `047` + `colocation_role_rule_service` + router + testleri
3. `sellable_service` / `colocation_matching_service` bağlanması + cache etag'i
4. `api_client` fonksiyonları + cache invalidation
5. Sayfa + callback'ler + `shell.py` sub-nav + permission
6. Canlı doğrulama (DC13 = 272 U, ayar değiştir → sayı anında değişiyor mu)

Her adım kendi commit'ini alır ve hemen pushlanır.
