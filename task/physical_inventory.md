## Physical Inventory Feature

- **Amaç**: DC ve müşteri bazlı fiziksel cihazları (NetBox `discovery_netbox_inventory_device` tablosu) görselleştirmek; Overview’da interaktif bar chart, DC ve Customer view’da Physical Inventory sekmeleri sunmak. Boyner sorgularının kapsamını `%boyner%` ILIKE ile genişletmek.

### Veri Kaynağı

- Tablo: `public.discovery_netbox_inventory_device`
- Müşteri (Boyner): `tenant_id = 5`
- DC eşleştirme: `site_name ILIKE %dc_name%`

### Uygulanan Değişikliklar

#### 1. Sorgular (`src/queries/customer.py`)

- `PHYSICAL_INVENTORY_CUSTOMER_DEVICE_LIST` — Boyner cihaz listesi (name, device_role_name, manufacturer_name, location)
- `PHYSICAL_INVENTORY_DC_TOTAL` — DC’deki toplam cihaz sayısı
- `PHYSICAL_INVENTORY_DC_BY_ROLE` — DC’de device_role_name’e göre sayılar
- `PHYSICAL_INVENTORY_DC_ROLE_MANUFACTURER` — DC’de role + manufacturer kırılımı
- `PHYSICAL_INVENTORY_OVERVIEW_BY_ROLE` — Tüm platformda role dağılımı (Overview level 0)
- `PHYSICAL_INVENTORY_OVERVIEW_MANUFACTURER` — Seçili role için manufacturer dağılımı (drill level 1)
- `PHYSICAL_INVENTORY_OVERVIEW_DC` — Seçili role+manufacturer için DC dağılımı (drill level 2)

#### 2. Servis (`src/services/db_service.py`)

- **Boyner pattern**: `vm_pattern`, `lpar_pattern`, `veeam_pattern`, `zerto_name_like` artık `%{name}%` (ILIKE ile geniş kapsam).
- **Yeni metodlar**:
  - `get_physical_inventory_customer()` — Boyner cihaz listesi
  - `get_physical_inventory_dc(dc_name)` — total, by_role, by_role_manufacturer
  - `get_physical_inventory_overview_by_role()`
  - `get_physical_inventory_overview_manufacturer(role)`
  - `get_physical_inventory_overview_dc(role, manufacturer)`

#### 3. Overview (`src/pages/home.py`)

- **Platform Breakdown** kartı kaldırıldı; yerine **Physical Inventory** kartı eklendi.
- İçerik: başlık, “Device types · click to drill down” açıklaması, Reset butonu (drill sonrası görünür), `dcc.Store` (drill state), `dcc.Graph` (bar chart).
- İlk görünüm: device_role_name’e göre yatay bar chart (`_phys_inv_bar_figure`).
- Drill-down: `app.py` callback ile level 0 → 1 (manufacturer) → 2 (DC) ve Reset ile level 0’a dönüş.

#### 4. DC View (`src/pages/dc_view.py`)

- **Physical Inventory** sekmesi eklendi (DC’de en az 1 cihaz varsa görünür).
- `_build_physical_inventory_dc_tab(phys_inv)`:
  - KPI: Total Devices
  - Bar chart: Devices by Role (device_role_name)
  - Grouped bar chart: Manufacturer by Role (role + manufacturer kırılımı).

#### 5. Customer View (`src/pages/customer_view.py`)

- **Physical Inventory** sekmesi eklendi (her zaman gösterilir).
- `_tab_physical_inventory(devices)`:
  - KPI: Total Physical Devices
  - Tablo: Name | Device Role | Manufacturer | Location (COALESCE(location_name, site_name)).

#### 6. Callback (`app.py`)

- `update_phys_inv_chart`: chart click ve Reset butonuna göre drill state güncellenir; level 0/1/2 için uygun servis çağrıları yapılıp figure ve Reset butonu stilı döndürülür.

### Etkilenen Dosyalar

- `src/queries/customer.py`
- `src/services/db_service.py`
- `src/pages/home.py`
- `src/pages/dc_view.py`
- `src/pages/customer_view.py`
- `app.py`
