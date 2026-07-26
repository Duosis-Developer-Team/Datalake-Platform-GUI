# TASK-13 — Customer Ekranında Altyapı Bilgilerinin Gizlenmesi

**Tip:** Yetki / UI · **Efor:** S · **Öncelik:** Orta-Yüksek (güvenlik/gizlilik)
**Paydaş:** Can, Sezgin Bey (detayları aktaracak)

## Hedef
Müşteri ekranında altyapı detayları (switch portları vb.) görünmemeli. İlgili kısıtlamalar uygulanacak.

## Mevcut yetki mimarisi

`src/auth/permission_catalog.py` — hiyerarşik `PermissionNode` ağacı:

```
sec:dc_view:network                     "Network"
  ├ sub:dc_view:net:overview            "Network Overview"
  └ sub:dc_view:net:switch              "Switch Roles"      ← switch portları burada
sec:dc_view:storage
  └ sub:dc_view:storage:san             "SAN Switch"
sec:dc_view:colocation                  "Colocation"
action:customer:export / action:dc_view:export …
```

Kontrol noktaları:
- `dc_view.py :: _visible_network_scopes(sec_check)` — `NETWORK_TOP_PERMISSIONS` ile scope filtreliyor
- `customer_view.py` — sekme kurulumunda `visible_sections` parametresi
- `src/utils/visibility.py` — veri yoksa gizleme (yetki değil, **veri** bazlı)
- Cache: `dl:perm_map:*`, TTL `PERMISSION_MAP_CACHE_TTL_SEC` (300 sn)

Roller: Settings › IAM (`datalake-platform-knowledge-base/wiki/Settings-IAM-UI.md`)

## ⚠️ İlk iş: gizlenecek alanların tam listesi

"switch portları vb." yeterli değil. Can ve Sezgin Bey'den **madde madde** liste alın. Aday liste:

| Alan | Nerede | Müşteri görmeli mi? |
|---|---|---|
| Switch port isimleri / port numaraları | DC View › Network › Switch | ❌ |
| Interface bazlı trafik tablosu | Network › Interface table | ❌ (toplam trafiği görebilir) |
| Rack / kabinet konumu, U pozisyonu | Colocation, Floor map | ❓ (kendi kabinetini görebilir?) |
| Host / cluster adları | Virtualization sekmeleri | ❓ |
| Media server / NetBackup host adları | Backup panelleri | ❌ |
| SAN switch, WWN, zoning | Storage › SAN | ❌ |
| IP adresleri, VLAN | Network | ❌ |
| Diğer müşterilerin varlık isimleri | Her yer | ❌ (kritik) |

## Yapılacaklar

- [ ] Gizlenecek alan listesini paydaşlardan al ve dosyaya yaz (bu maddenin ön koşulu)
- [ ] Her alan için **hangi katmanda** kesileceğine karar ver:
      - **Backend (tercih edilen):** müşteri rolünde endpoint alanı hiç dönmesin
      - **Frontend:** yalnızca UI'da gizlensin (veri yine ağdan geçer — **zayıf**)
      > Güvenlik kuralı: hassas alan **backend'de** kesilmeli. Frontend gizleme tek başına yeterli değil.
- [ ] `permission_catalog.py`'ye gerekirse yeni ince taneli düğümler ekle
      (örn. `sub:dc_view:net:switch:ports`, `field:backup:media_server_name`)
- [ ] "Customer" rolü için varsayılan izin setini tanımla (deny-by-default)
- [ ] Response modellerinde alan maskeleme: müşteri rolünde hassas alanlar `None`/çıkarılmış
- [ ] Export (Excel/PDF) çıktılarında da aynı maskeleme uygulansın — **sık atlanır**
- [ ] Chatbot/MCP katmanı da aynı yetkiye tabi olmalı (`services/datalake-mcp`) — kontrol et

## Doğrulama

```bash
# Müşteri rolündeki bir kullanıcı ile giriş yapıp:
# 1) API cevabında hassas alan var mı
curl -s -H "Authorization: Bearer $CUSTOMER_TOKEN" \
  "http://10.134.52.250:8000/api/v1/datacenters/DC13/network/interface-table?range=1d" \
  | python3 -c "
import json,sys; d=json.load(sys.stdin)
rows=d.get('rows') or []
print('kolonlar:', list(rows[0].keys()) if rows else 'bos')
"
# 2) Admin ile aynı çağrı - fark görünmeli
# 3) Export endpoint'i de maskeliyor mu
curl -s -H "Authorization: Bearer $CUSTOMER_TOKEN" \
  "http://10.134.52.250:8000/api/v1/datacenters/DC13/network/interface-export?range=1d" | head -c 500
```

```sql
-- Yetki ağacındaki mevcut düğümler (bulutauth / webui)
SELECT * FROM permission_nodes WHERE key ILIKE '%network%' OR key ILIKE '%switch%';
-- (tablo adı için: SELECT table_name FROM information_schema.tables WHERE table_name ILIKE '%permission%')

-- Rol-izin atamaları
SELECT r.name AS rol, p.key AS izin
FROM role_permissions rp JOIN roles r ON r.id=rp.role_id JOIN permission_nodes p ON p.id=rp.permission_id
WHERE r.name ILIKE '%customer%' ORDER BY 2;
```

## Kabul kriterleri
- [ ] Gizlenecek alan listesi yazılı ve onaylı
- [ ] Müşteri rolüyle yapılan API çağrılarında hassas alanlar **cevapta yok** (frontend gizleme değil)
- [ ] Export çıktıları da maskeli
- [ ] Admin/operasyon rollerinde davranış değişmemiş (regresyon)
- [ ] Chatbot/MCP üzerinden de hassas alan sızmıyor
- [ ] Yetki testi otomatikleştirilmiş (`tests/` altında rol bazlı endpoint testi)

## Cursor / Claude Code prompt

```
Bağlam: task/GUI/00-ortam-ve-dogrulama-rehberi.md, docs/AUTH_SYSTEM.md,
datalake-platform-knowledge-base/wiki/Settings-IAM-UI.md,
src/auth/permission_catalog.py, src/pages/dc_view.py (_visible_network_scopes, NETWORK_TOP_PERMISSIONS),
src/pages/customer_view.py, src/utils/visibility.py

Görev: Müşteri rolünde altyapı detaylarını (switch portları vb.) gizle.

ADIM 0: Gizlenecek alanların tam listesi bana verilmediyse DUR ve iste. Tahminle iş yapma.

1. Her hassas alan için kesme noktasını BACKEND'de kur: müşteri rolünde ilgili alan
   response modelinden çıkarılsın (None yapmak yerine alanı hiç dönme). Frontend gizleme
   tek başına yeterli değildir - bunu raporunda belirt.
2. permission_catalog.py'ye gereken ince taneli düğümleri ekle. Mevcut düğümleri silme,
   ekleme yap (mevcut rol atamaları kırılmasın).
3. "Customer" rolü için deny-by-default varsayılan izin setini tanımla.
4. Export endpoint'lerinde (interface-export, Excel/PDF helper'ları) aynı maskelemeyi uygula.
5. services/datalake-mcp ve chatbot katmanının da aynı yetkiye tabi olduğunu doğrula; değilse düzelt.
6. tests/: rol bazlı endpoint testi - customer rolü hassas alanı göremez, admin görebilir.
   Export için de aynı test.

Kısıt: Admin/operasyon rollerinde hiçbir davranış değişmemeli.
```

## İlgili
TASK-07 (müşteri faturayı görecek) ile birlikte "müşteri neyi görür / neyi görmez" matrisi tek yerde tanımlanmalı.
