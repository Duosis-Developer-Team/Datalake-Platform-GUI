#!/usr/bin/env bash
# Compare VIP flags in webui-db with customer-api catalog response.
# Usage (local Compose):
#   ./scripts/verify-vip-consistency.sh
# Usage (remote test host via SSH):
#   WEBUI_DB_CONTAINER=bulutistan-webui-db CUSTOMER_API_URL=http://localhost:8001 \
#     ssh root@10.134.52.250 'bash -s' < ./scripts/verify-vip-consistency.sh

set -euo pipefail

WEBUI_DB_CONTAINER="${WEBUI_DB_CONTAINER:-bulutistan-webui-db}"
WEBUI_DB_USER="${WEBUI_DB_USER:-webuiadmin}"
WEBUI_DB_NAME="${WEBUI_DB_NAME:-bulutwebui}"
CUSTOMER_API_URL="${CUSTOMER_API_URL:-http://localhost:8001}"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is required." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is required." >&2
  exit 1
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

docker exec "$WEBUI_DB_CONTAINER" psql -U "$WEBUI_DB_USER" -d "$WEBUI_DB_NAME" -t -A -F',' \
  -c "SELECT crm_accountid, is_vip::text, cache_pinned::text FROM gui_crm_customer_profile_flags WHERE is_vip = TRUE ORDER BY crm_accountid;" \
  >"$TMP_DIR/db_vip.csv" || {
  echo "ERROR: failed to read gui_crm_customer_profile_flags (is migration 018 applied?)." >&2
  exit 1
}

curl -sf "${CUSTOMER_API_URL}/api/v1/customers/catalog" -o "$TMP_DIR/catalog.json" || {
  echo "ERROR: failed to fetch ${CUSTOMER_API_URL}/api/v1/customers/catalog" >&2
  exit 1
}

python3 - "$TMP_DIR/db_vip.csv" "$TMP_DIR/catalog.json" <<'PY'
import json
import sys
from pathlib import Path

db_path, catalog_path = sys.argv[1], sys.argv[2]
db_vip = {}
for line in Path(db_path).read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line:
        continue
    account_id, is_vip, _cache_pinned = line.split(",", 2)
    if is_vip.lower() == "true":
        db_vip[account_id] = True

catalog = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
api_vip = {}
for row in (catalog.get("customers") or []):
    account_id = row.get("crm_accountid")
    if account_id:
        api_vip[str(account_id)] = bool(row.get("is_vip"))

db_ids = set(db_vip)
api_ids = {aid for aid, flag in api_vip.items() if flag}

missing_in_api = sorted(db_ids - api_ids)
missing_in_db = sorted(api_ids - db_ids)
mismatched = sorted(aid for aid in (db_ids & api_ids) if not api_vip.get(aid))

errors = []
if missing_in_api:
    errors.append("VIP in DB but not is_vip in catalog: {}".format(missing_in_api))
if missing_in_db:
    errors.append("VIP in catalog but not is_vip=true in DB: {}".format(missing_in_db))
if mismatched:
    errors.append("Account in both sets but catalog is_vip=false: {}".format(mismatched))

if errors:
    print("VIP consistency check FAILED:")
    for err in errors:
        print("  - {}".format(err))
    sys.exit(1)

print("VIP consistency OK (db_vip={}, catalog_vip={})".format(len(db_ids), len(api_ids)))
PY
