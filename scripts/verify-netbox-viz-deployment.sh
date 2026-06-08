#!/usr/bin/env bash
# Verify NetBox/Loki visualization filter deployment (API + optional webui migration).
# Usage:
#   ./scripts/verify-netbox-viz-deployment.sh
#   DC_API=http://10.134.52.250:8000 CUST_API=http://10.134.52.250:8001 ./scripts/verify-netbox-viz-deployment.sh
# On test server (with webui-db):
#   docker compose exec -T webui-db psql -U webuiadmin -d bulutwebui -c "\\d gui_netbox_viz_exclusion"

set -euo pipefail

DC_API="${DC_API:-http://localhost:8000}"
CUST_API="${CUST_API:-http://localhost:8001}"
GUI_URL="${GUI_URL:-http://localhost:8050}"

pass=0
fail=0

check_http() {
  local name="$1"
  local url="$2"
  local expect="${3:-200}"
  local code
  code="$(curl -sf -o /tmp/nbx_verify_body.json -w '%{http_code}' --connect-timeout 10 "$url" 2>/dev/null || echo "000")"
  if [[ "$code" == "$expect" ]]; then
    echo "[OK]   $name ($code)"
    pass=$((pass + 1))
    return 0
  fi
  echo "[FAIL] $name expected HTTP $expect got $code"
  if [[ -f /tmp/nbx_verify_body.json ]]; then
    head -c 200 /tmp/nbx_verify_body.json 2>/dev/null || true
    echo
  fi
  fail=$((fail + 1))
  return 1
}

echo "NetBox viz deployment verification"
echo "  datacenter-api: $DC_API"
echo "  customer-api:   $CUST_API"
echo "  gui:            $GUI_URL"
echo

check_http "GET device-roles" "${DC_API}/api/v1/netbox/device-roles" 200 || true
check_http "GET visualization-exclusions" "${CUST_API}/api/v1/netbox/config/visualization-exclusions" 200 || true

roles_code="$(curl -sf -o /tmp/nbx_roles.json -w '%{http_code}' --connect-timeout 10 "${DC_API}/api/v1/netbox/device-roles" 2>/dev/null || echo "000")"
if [[ "$roles_code" == "200" ]] && command -v python3 >/dev/null 2>&1; then
  if python3 - <<'PY'
import json, sys
with open("/tmp/nbx_roles.json") as f:
    data = json.load(f)
if isinstance(data, list) and len(data) > 0 and "role" in data[0]:
    sys.exit(0)
sys.exit(1)
PY
  then
    echo "[OK]   device-roles payload shape"
    pass=$((pass + 1))
  else
    echo "[FAIL] device-roles payload shape"
    fail=$((fail + 1))
  fi
fi

echo
echo "Summary: $pass passed, $fail failed"
if [[ "$fail" -gt 0 ]]; then
  echo "Deploy: git pull feature/netbox-viz-device-role-filter (or main), apply migration 019, rebuild app + customer-api + datacenter-api."
  exit 1
fi
exit 0
