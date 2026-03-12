## Customer View Upgrade — DC-style Hierarchy & Billing

- **Amaç**: Customer View ekranının, Data Center detay ekranı ile aynı sekme hiyerarşisine sahip olması ve faturalandırma odaklı ek bir `Billing` sekmesi sunması.

### Uygulanan Değişiklikler

- **Import düzeltmesi**:
  - `customer_view.py` içinde eksik olan `smart_storage`, `smart_memory`, `smart_cpu`, `pct_float` importları eklendi.

- **Yeni `Billing` sekmesi**:
  - `_tab_billing()` fonksiyonu ile:
    - Classic / Hyperconverged / Power compute kaynakları için fatura satırları (VM/LPAR, CPU, Memory, Disk) oluşturuldu.
    - Backup (Veeam, Zerto, NetBackup) metrikleri faturalandırma perspektifiyle özetlendi.
    - Müşteriye ait S3 vault sayısı billing kartı olarak gösterildi.

- **Virtualization sekmesi (iç içe sekmeler)**:
  - `Virtualization` sekmesi altında, DC detay sayfası ile aynı hiyerarşi kuruldu:
    - `Klasik Mimari` → `_tab_classic(classic)`
    - `Hyperconverged Mimari` → `_tab_hyperconv(hyperconv)`
    - `Power Mimari` → `_tab_power(power_asset)`
  - Bu yapı `dmc.Tabs(color=\"violet\", variant=\"outline\")` ile uygulanarak DC ekranı ile görsel ve işlevsel uyum sağlandı.

- **Backup sekmesi (iç içe sekmeler)**:
  - Üstte HANA/Power özet kartları korundu.
  - Altında `Backup` için iç içe sekmeler eklendi:
    - `Veeam` → `_tab_veeam(backup_assets, backup_totals)`
    - `Zerto` → `_tab_zerto(backup_assets, backup_totals)`
    - `Netbackup` → `_tab_netbackup(backup_assets, backup_totals)`

- **Summary sekmesi**:
  - Eski manuel layout kaldırılarak, doğrudan `_tab_summary(totals, assets)` kullanıldı.
  - Böylece compute ve backup için tek, tutarlı billing odaklı özet paneli oluştu.

- **Header & sekme entegrasyonu**:
  - `build_customer_layout` artık DC detay sayfasındaki gibi bir `dmc.Tabs` içerisinde:
    - `create_detail_header(..., tabs=tabs_list)` çağırıyor.
    - `tabs_list` içinde `Summary`, `Virtualization`, `Backup`, `Billing` ve (varsa) `S3` sekmeleri bulunuyor.
  - Header altındaki intro kartı, seçilen müşteri adını (`selected_customer or \"Boyner\"`) dinamik olarak gösteriyor.

- **S3 görünürlüğü**:
  - `_customer_content` dönen sözlüğe `\"has_s3\"` ve `\"s3\"` anahtarları eklendi.
  - `build_customer_layout` içinde `has_s3` değerine göre hem header sekmeleri hem de `S3` paneli koşullu olarak render ediliyor.

