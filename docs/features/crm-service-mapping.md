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

## Technical notes

- `efficiency_usage.resolve_used_quantity` **category_code** prefix’lerine göre çalışır (`virt_classic`, `backup_veeam`, …). Bu yüzden `page_key` = eski `category_code` değerleri ile uyumludur.
- Satılan miktarlar için **CRM satır birimi** (`uomid_name`) önceliklidir; view `resource_unit` NULL, sayfa varsayılanı `page_resource_unit` (bkz. `CRM_SERVICE_MAPPING.md`).
- `gui_tab_binding` yalnızca UI etiketleme / Customer View sekmeleri için kullanılır.
- NiFi `productpricelevel` rotası bu feature’dan bağımsızdır; katalog fiyat analitiği için ayrıca datalake dokümanına bakın.

## References

- [ADR-0011](../../datalake-platform-knowledge-base/adrs/ADR-0011-crm-service-mapping-yaml-db-override.md) (repo-relative path from GUI: `../datalake-platform-knowledge-base/...`)
- SQL: `datalake/SQL/CRM/migrations/2026-04-24-gui-crm-service-mapping.sql`, `2026-04-25-gui-crm-service-mapping-units-and-replication.sql`
- Generator: `shared/service_mapping/generate_seed_sql.py`
