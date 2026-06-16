#!/usr/bin/env bash
# Smoke-check Virt-related Redis/API cache keys and cold-path latency.
# Usage: ./scripts/verify-virt-cache.sh [DC] [HOST]
set -euo pipefail

DC="${1:-DC13}"
HOST="${2:-localhost}"
DC_API="http://${HOST}:8000"
GUI_API="http://${HOST}:8050"

echo "== Virt cache smoke: dc=${DC} api=${DC_API} =="

echo "-- Redis host-rows keys (7d) --"
if command -v docker >/dev/null 2>&1; then
  docker exec bulutistan-redis redis-cli KEYS "*hosts_all*${DC}*" 2>/dev/null | head -20 || true
  docker exec bulutistan-redis redis-cli KEYS "compute:*${DC}*" 2>/dev/null | head -20 || true
  docker exec bulutistan-redis redis-cli KEYS "dc_details:${DC}:*" 2>/dev/null | head -5 || true
else
  echo "docker not available — skip Redis key listing"
fi

echo "-- datacenter-api host-rows (warm hit expected <2s) --"
curl -sf -w "time_total=%{time_total}s http=%{http_code}\n" -o /tmp/virt_hosts.json \
  "${DC_API}/api/v1/datacenters/${DC}/compute/hyperconverged/hosts?preset=7d"
python3 - <<'PY'
import json
d=json.load(open("/tmp/virt_hosts.json"))
print("host_count", d.get("host_count", len(d.get("hosts", []))))
h=(d.get("hosts") or [None])[0] or {}
print("sample_peak", h.get("mem_used_gb_peak"))
PY

echo "-- datacenter-api dc_details (preset=7d) --"
curl -sf -w "time_total=%{time_total}s http=%{http_code}\n" -o /dev/null \
  "${DC_API}/api/v1/datacenters/${DC}?preset=7d"

echo "-- GUI health --"
curl -sf -o /dev/null -w "gui_http=%{http_code}\n" "${GUI_API}/" || echo "gui unreachable"

echo "-- recent virt_cache log lines (datacenter-api) --"
if command -v docker >/dev/null 2>&1; then
  docker logs bulutistan-datacenter-api --tail 200 2>&1 | grep -E "virt_cache\.|host-rows cache refresh" | tail -15 || true
fi

echo "Done."
