# Applies WebUI PostgreSQL migrations to an EXISTING bulutistan-webui-db volume.
#
# Why: Postgres runs /docker-entrypoint-initdb.d/*.sql ONLY on first init (empty data dir).
# Restarting webui-db does NOT replay those files.
#
# Tracking: applied filenames are stored in gui_schema_migrations so re-runs skip completed
# files. If one migration fails, earlier files stay recorded and only pending files run next time.
#
# Usage (from Datalake-Platform-GUI repo root):
#   .\scripts\apply-webui-migrations-docker.ps1
#
# Linux/macOS: scripts/apply-webui-migrations-docker.sh
#
# Requires: bulutistan-webui-db container running.

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $repoRoot "docker-compose.yml"))) {
    Write-Error "Run from Datalake-Platform-GUI repo (docker-compose.yml not found)."
    exit 1
}

Set-Location $repoRoot

Write-Host "Applying /docker-entrypoint-initdb.d/*.sql inside webui-db (tracked in gui_schema_migrations; POSTGRES_USER / POSTGRES_DB from container env) ..."

$remoteScript = @'
set -eu

psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c "
  CREATE TABLE IF NOT EXISTS gui_schema_migrations (
    filename   TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
  );"

for f in $(ls /docker-entrypoint-initdb.d/*.sql 2>/dev/null | sort -V); do
  fname=$(basename "$f")
  already=$(psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v "fname=$fname" -tAc "SELECT 1 FROM gui_schema_migrations WHERE filename = :'fname'")
  if [ "$already" = "1" ]; then
    echo "=== Skipping $fname (already applied) ==="
  else
    echo "=== Applying $fname ==="
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f "$f"
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v "fname=$fname" -c "INSERT INTO gui_schema_migrations (filename) VALUES (:'fname') ON CONFLICT DO NOTHING;"
    echo "    -> Recorded $fname"
  fi
done
'@

$remoteScript | docker compose exec -T webui-db sh -s

if ($LASTEXITCODE -ne 0) {
    Write-Error "Migration apply failed (exit $LASTEXITCODE)."
    exit $LASTEXITCODE
}

Write-Host "Done. Verify migrations: docker compose exec -T webui-db psql -U webuiadmin -d bulutwebui -c `"SELECT * FROM gui_schema_migrations ORDER BY filename;`""
Write-Host "Verify tables: docker compose exec -T webui-db psql -U webuiadmin -d bulutwebui -c `"\\dt gui_*`""
Write-Host "Then retry Save on Infra sources."
