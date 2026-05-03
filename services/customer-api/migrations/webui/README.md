# WebUI App DB migrations

These SQL files initialise the **bulutwebui** database that holds GUI configuration
tables. Raw CRM/datalake metric data stays in the external datalake DB; only
operator-managed mappings, overrides, thresholds and aliases live here.

## Apply order

| File | Purpose |
| --- | --- |
| `001_init_schema.sql` | Tables: pages registry, product mapping (seed + override), customer alias, threshold config, price override, calc config |
| `002_seed_pages_and_mapping.sql` | Initial 19 service pages and ~220 productid → page mappings (idempotent via `ON CONFLICT DO NOTHING`) |
| `003_seed_calc_thresholds.sql` | Default efficiency thresholds, calc variables, resource ceilings |

## Docker bootstrap

The `webui-db` service in `docker-compose.yml` mounts this folder as
`/docker-entrypoint-initdb.d`. PostgreSQL applies the files in lexical order on
the **first** container start (when the data volume is empty). To re-seed an
existing volume, drop the volume or run the SQL files manually:

```powershell
docker compose exec webui-db psql -U webuiadmin -d bulutwebui -f /docker-entrypoint-initdb.d/001_init_schema.sql
```

## Manual application against an existing PostgreSQL host

```bash
psql -h <host> -p <port> -U webuiadmin -d bulutwebui \
  -f services/customer-api/migrations/webui/001_init_schema.sql \
  -f services/customer-api/migrations/webui/002_seed_pages_and_mapping.sql \
  -f services/customer-api/migrations/webui/003_seed_calc_thresholds.sql
```

## Source of truth for seeds

`002_seed_pages_and_mapping.sql` mirrors the GUI YAML rules. Regenerate via
`shared/service_mapping/generate_seed_sql.py` if `crm_service_mapping.yaml` changes,
then update this folder accordingly.
