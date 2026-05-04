# Applies WebUI PostgreSQL migrations to an EXISTING bulutistan-webui-db volume.
#
# Why: Postgres runs /docker-entrypoint-initdb.d/*.sql ONLY on first init (empty data dir).
# Restarting webui-db does NOT replay those files. Missing gui_panel_infra_source means the
# volume was created before migration 005 — apply SQL manually or delete webui_pgdata.
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

Write-Host "Applying /docker-entrypoint-initdb.d/*.sql inside webui-db (POSTGRES_USER / POSTGRES_DB from container env) ..."

# Single-quoted -c body: whole script runs in Linux shell inside container (no PowerShell $(...) expansion).
docker compose exec -T webui-db sh -c 'set -e; for f in $(ls /docker-entrypoint-initdb.d/*.sql | sort -V); do echo "=== Applying $f ==="; psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f "$f"; done'

if ($LASTEXITCODE -ne 0) {
    Write-Error "Migration apply failed (exit $LASTEXITCODE)."
    exit $LASTEXITCODE
}

Write-Host "Done. Verify tables: docker compose exec -T webui-db psql -U webuiadmin -d bulutwebui -c `"\\dt gui_*`""
Write-Host "Then retry Save on Infra sources."
