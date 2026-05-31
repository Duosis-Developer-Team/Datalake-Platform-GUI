# WebUI App DB migrations

These SQL files initialise the **bulutwebui** database that holds GUI configuration
tables. Raw CRM/datalake metric data stays in the external datalake DB; only
operator-managed mappings, overrides, thresholds and aliases live here.

## Apply order

Files under this directory are applied in **version-sorted** order (`sort -V` on basenames).
Keep numeric prefixes so new migrations always sort after existing ones.

| File | Purpose | Idempotent |
| --- | --- | --- |
| `001_init_schema.sql` | Tables: pages registry, product mapping (seed + override), customer alias, threshold config, price override, calc config | Yes (`CREATE IF NOT EXISTS`) |
| `002_seed_pages_and_mapping.sql` | Initial service pages and productid → page mappings | Yes (`ON CONFLICT DO NOTHING`) |
| `003_seed_calc_thresholds.sql` | Default efficiency thresholds, calc variables, resource ceilings | Yes (`ON CONFLICT DO NOTHING`) |
| `004_granular_pages.sql` | Granular `page_key` taxonomy (generated; patch mode) | Yes (`ON CONFLICT DO UPDATE`) |
| `005_panel_sellable_schema.sql` | Panel registry, infra bindings, ratios, unit conversions, metric snapshots; extends threshold/pages with `panel_key` | Yes |
| `005z_gui_panel_infra_source_allow_null.sql` | Allows NULL infra binding columns on `gui_panel_infra_source` | Yes |
| `006_seed_panel_definitions.sql` | Seed `gui_panel_definition` | Yes (`ON CONFLICT DO UPDATE`) |
| `007_seed_panel_infra_sources.sql` | Seed `gui_panel_infra_source` placeholders | Yes |
| `008_seed_resource_ratios.sql` | Seed `gui_panel_resource_ratio` | Yes |
| `009_seed_unit_conversions.sql` | Seed `gui_unit_conversion` | Yes |
| `010_seed_full_product_mapping.sql` | Full product → page seed rows | Yes |
| `011_update_redis_allocated_units.sql` | Updates seed infra bindings for Redis-backed allocated metrics | Yes |
| `012_power_crm_panels.sql` | IBM Power CRM panels / unit conversions | Yes |
| `013_panel_result_snapshot_and_manual_override.sql` | Tier-2 `gui_panel_result_snapshot` + `manual_total`/`manual_allocated` on infra source | Yes |
| `014_repair_gui_panel_result_snapshot.sql` | Repairs partial/legacy `gui_panel_result_snapshot` (adds `payload`, PK, index) when 013 was skipped by `IF NOT EXISTS` | Yes |
| `015_fix_ibm_power_infra_filter.sql` | Clears invalid `site_name` filter on `virt_power_cpu` / `virt_power_ram` (SellableService uses HMC server name columns) | Yes |

## Tracking table (`gui_schema_migrations`)

Upgrade paths use an **existing** Docker volume: Postgres only runs `/docker-entrypoint-initdb.d/*.sql` on **first** init. The repo scripts record each successfully applied file:

- Table: `gui_schema_migrations (filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ)`
- Created automatically by [scripts/apply-webui-migrations-docker.sh](../../../scripts/apply-webui-migrations-docker.sh) / [scripts/apply-webui-migrations-docker.ps1](../../../scripts/apply-webui-migrations-docker.ps1)
- On each run: skip files already listed; apply pending files with `ON_ERROR_STOP=1`; insert a row after each successful file

If a migration fails part-way through the chain, fix the underlying issue and re-run the script — completed files are skipped.

**Re-apply one file** (e.g. after fixing SQL): delete its row, then run the script again.

```sql
DELETE FROM gui_schema_migrations WHERE filename = '004_granular_pages.sql';
```

### Troubleshooting: `column "payload" does not exist` on `gui_panel_result_snapshot`

If logs show `UndefinedColumn: column "payload" … gui_panel_result_snapshot` but migration `013` is already recorded, an **older partial table** likely existed before 013 ran (`CREATE TABLE IF NOT EXISTS` then skipped DDL). Run the apply script again after pulling **`014_repair_gui_panel_result_snapshot.sql`**. Verify:

```powershell
docker compose exec -T webui-db psql -U webuiadmin -d bulutwebui -c "\d gui_panel_result_snapshot"
```

## Docker: apply all pending migrations

From `Datalake-Platform-GUI` repo root, with `webui-db` running:

```bash
./scripts/apply-webui-migrations-docker.sh
```

```powershell
.\scripts\apply-webui-migrations-docker.ps1
```

Verify:

```powershell
docker compose exec -T webui-db psql -U webuiadmin -d bulutwebui -c "SELECT * FROM gui_schema_migrations ORDER BY filename;"
docker compose exec -T webui-db psql -U webuiadmin -d bulutwebui -c "\dt gui_*"
```

Adjust `webuiadmin` / `bulutwebui` if your `.env` sets `WEBUI_DB_USER` / `WEBUI_DB_NAME`.

## Docker bootstrap (first empty volume)

The `webui-db` service in `docker-compose.yml` mounts this folder as
`/docker-entrypoint-initdb.d`. PostgreSQL applies the files in lexical order on
the **first** container start (when the data volume is empty). After that, use
the apply scripts above so new migrations are tracked consistently.

## Manual application against an existing PostgreSQL host

Run files in sorted order (same as scripts), or use the Docker scripts against a host that exposes the same volume/mount layout.

```bash
for f in $(ls services/customer-api/migrations/webui/*.sql | sort -V); do
  psql -h <host> -p <port> -U webuiadmin -d bulutwebui -v ON_ERROR_STOP=1 -f "$f"
done
```

For parity with Docker upgrades, create `gui_schema_migrations` and insert rows after each file (or run the official apply script against a one-off container attached to that database).

## Adding a new migration

1. Add `NNN_short_description.sql` in this directory with the next sortable prefix (`013_...`, etc.).
2. Prefer idempotent DDL/DML (`IF NOT EXISTS`, `ON CONFLICT`, guarded `ALTER`) so re-runs and tracking replays stay safe.
3. Run `apply-webui-migrations-docker.sh` or `.ps1` after each GUI release / pull on every environment that keeps the `webui_pgdata` volume.

## Source of truth for seeds

`002_seed_pages_and_mapping.sql` (and generated patches like `004_granular_pages.sql`) mirror the GUI YAML rules. Regenerate via
`shared/service_mapping/generate_seed_sql.py` if `crm_service_mapping.yaml` changes,
then update this folder accordingly.
