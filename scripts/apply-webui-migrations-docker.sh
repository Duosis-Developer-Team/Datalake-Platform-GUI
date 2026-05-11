#!/usr/bin/env sh
# Applies WebUI PostgreSQL migrations to an EXISTING bulutistan-webui-db volume.
#
# Why: Postgres runs /docker-entrypoint-initdb.d/*.sql ONLY on first init (empty data dir).
# Restarting webui-db does NOT replay those files.
#
# Tracking: applied filenames are stored in gui_schema_migrations so re-runs skip completed
# files. If one migration fails, earlier files stay recorded and only pending files run next time.
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

echo "Applying /docker-entrypoint-initdb.d/*.sql inside webui-db (tracked in gui_schema_migrations; POSTGRES_USER / POSTGRES_DB from container env) ..."

docker compose exec -T webui-db sh -s <<'REMOTE_SCRIPT'
set -eu

# Build a single-quoted SQL literal (do not use psql :'var' — some clients pass it verbatim to the server).
sql_literal() {
  printf "%s" "$1" | sed "s/'/''/g"
}

psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c "
  CREATE TABLE IF NOT EXISTS gui_schema_migrations (
    filename   TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
  );"

for f in $(ls /docker-entrypoint-initdb.d/*.sql 2>/dev/null | sort -V); do
  fname=$(basename "$f")
  fnlit=$(sql_literal "$fname")
  already=$(psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT 1 FROM gui_schema_migrations WHERE filename = '$fnlit'")
  if [ "$already" = "1" ]; then
    echo "=== Skipping $fname (already applied) ==="
  else
    echo "=== Applying $fname ==="
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f "$f"
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "INSERT INTO gui_schema_migrations (filename) VALUES ('$fnlit') ON CONFLICT DO NOTHING;"
    echo "    -> Recorded $fname"
  fi
done
REMOTE_SCRIPT

echo "Done. Verify migrations and tables (adjust user/db if WEBUI_DB_* differs in .env):"
echo "  docker compose exec -T webui-db psql -U webuiadmin -d bulutwebui -c \"SELECT * FROM gui_schema_migrations ORDER BY filename;\""
echo "  docker compose exec -T webui-db psql -U webuiadmin -d bulutwebui -c \"\\dt gui_*\""
echo "Then retry Save on Infra sources."
