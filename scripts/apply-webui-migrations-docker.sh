#!/usr/bin/env sh
# Applies WebUI PostgreSQL migrations to an EXISTING bulutistan-webui-db volume.
#
# Why: Postgres runs /docker-entrypoint-initdb.d/*.sql ONLY on first init (empty data dir).
# Restarting webui-db does NOT replay those files.
#
# Usage (from Datalake-Platform-GUI repo root):
#   chmod +x scripts/apply-webui-migrations-docker.sh
#   ./scripts/apply-webui-migrations-docker.sh
#
# Requires: webui-db service running (docker compose).
#
# Windows alternative: scripts/apply-webui-migrations-docker.ps1

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

if [ ! -f "$REPO_ROOT/docker-compose.yml" ]; then
    echo "Run from Datalake-Platform-GUI repo (docker-compose.yml not found)." >&2
    exit 1
fi

cd "$REPO_ROOT"

echo "Applying /docker-entrypoint-initdb.d/*.sql inside webui-db (POSTGRES_USER / POSTGRES_DB from container env) ..."

docker compose exec -T webui-db sh -c 'set -e; for f in $(ls /docker-entrypoint-initdb.d/*.sql | sort -V); do echo "=== Applying $f ==="; psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f "$f"; done'

echo "Done. Verify tables (adjust user/db if WEBUI_DB_* differs in .env):"
echo "  docker compose exec -T webui-db psql -U webuiadmin -d bulutwebui -c \"\\dt gui_*\""
echo "Then retry Save on Infra sources."
