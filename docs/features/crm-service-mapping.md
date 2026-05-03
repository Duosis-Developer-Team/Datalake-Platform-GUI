# Feature: CRM service → GUI mapping (YAML + DB override)

## Goal (TR)

CRM `discovery_crm_products` kayıtlarını, müşteri faturalama / efficiency panellerinde kullanılan **servis kategorisi** (`page_key`, örn. `virt_classic`, `backup_veeam`) ve **GUI sekme bağlaması** (`gui_tab_binding`, örn. `virtualization.classic`) ile eşlemek.

- **Varsayılanlar**: repo içinde `config/crm_service_mapping.yaml` + migration ile yüklenen `gui_crm_service_mapping_seed`.
- **Operatör override**: PostgreSQL `gui_crm_service_mapping_override` + Settings `/settings/crm/service-mapping`.

## Progress

| Step | Status |
|------|--------|
| ADR + wiki | Done — [[ADR-0011-crm-service-mapping-yaml-db-override]] |
| SQL migration (pages + seed + override + view + drop legacy) | Done — `datalake/SQL/CRM/migrations/2026-04-24-gui-crm-service-mapping.sql` |
| customer-api endpoints | Done |
| datacenter-api JOIN update | Done |
| Dash Settings page + permission | Done |
| Legacy collector/SQL removal | Done |
| Tests | Done — `tests/test_service_mapping_rules.py` |
| Kaynak bazlı birim + Klasik replication sınıflandırması | Done — `2026-04-25-gui-crm-service-mapping-units-and-replication.sql`, `embedded_rules.json`, `audit_crm_service_mapping_gaps.sql` |
| Granular page_key taxonomy (`_cpu` / `_ram` / `_storage`) + unmatched contract | Done — `embedded_rules.json` v2, `004_granular_pages.sql`, schemas/UI/efficiency_usage updates |

## Technical notes

- `efficiency_usage.resolve_used_quantity` **category_code** prefix’lerine göre çalışır (`virt_classic`, `backup_veeam`, …) ve artık ayrıca **suffix**’lere bakar: `_cpu` → CPU metrik, `_ram` → memory_gb, `_storage` → disk_gb. Bu sayede "Hyperconverged Mimari Intel RAM" SKU’su `virt_hyperconverged_ram` page_key’i ile gerçekten RAM panelini besler (eskiden vCPU bucket’ina düşüyordu).
- Satılan miktarlar için **CRM satır birimi** (`uomid_name`) önceliklidir; view `resource_unit` NULL, sayfa varsayılanı `page_resource_unit` (bkz. `CRM_SERVICE_MAPPING.md`).
- `gui_tab_binding` yalnızca UI etiketleme / Customer View sekmeleri için kullanılır.
- `LIST_SERVICE_MAPPINGS_WEBUI` artık `LEFT JOIN gui_crm_service_pages` kullanır; `category_code` NULL olabilir, `source = 'unmatched'` olarak set edilir. `sales_service.list_service_mappings` datalake’te bulunan ama webui-db’de seed/override’ı olmayan ürünleri de bu durumla yüzeye çıkarır.
- `generate_seed_sql.py --mode patch` idempotent UPSERT/UPDATE üretir (DROP yok); webui-db zaten ayaktayken yeni granüler page’leri ve `productid → page_key` re-classification’ı uygular.
- NiFi `productpricelevel` rotası bu feature’dan bağımsızdır; katalog fiyat analitiği için ayrıca datalake dokümanına bakın.

## References

- [ADR-0011](../../datalake-platform-knowledge-base/adrs/ADR-0011-crm-service-mapping-yaml-db-override.md) (repo-relative path from GUI: `../datalake-platform-knowledge-base/...`)
- SQL: `datalake/SQL/CRM/migrations/2026-04-24-gui-crm-service-mapping.sql`, `2026-04-25-gui-crm-service-mapping-units-and-replication.sql`, `services/customer-api/migrations/webui/004_granular_pages.sql`
- Generator: `shared/service_mapping/generate_seed_sql.py` (`--mode rebuild` | `--mode patch`)
- Rule pack: `shared/service_mapping/embedded_rules.json` (regex priorities + categories), `config/crm_service_mapping.yaml` (mirror)
