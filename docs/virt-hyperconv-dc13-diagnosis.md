# DC13 Hyperconverged zero-data diagnosis (2026-06-15)

## API comparison (test server `10.134.52.250`)

| Endpoint | hosts | mem_cap (GB) | mem_util_pct |
|----------|-------|--------------|--------------|
| `GET /compute/hyperconverged` (unfiltered) | 104 | 281308.92 | 62.9 |
| `GET /compute/hyperconverged?clusters=<all 15>` (filtered) | 104 | 159278.43 | 63.4 |

## Findings

1. **Backend is not returning zeros** when all Nutanix clusters are passed — filtered path is slow (~24s cold) but returns data.
2. **GUI zeros + spinner** are caused by blocking Dash callbacks on slow filtered SQL + per-chip fan-out (6 callbacks per cluster toggle), not missing DB rows.
3. **Unfiltered vs filtered capacity mismatch** — full cluster list should use the unfiltered `get_dc_details().hyperconv` fast path (same semantics as empty selection).
4. **Cluster list** comes from `nutanix.CLUSTER_LIST` only; VMware `HYPERCONV_CLUSTER_LIST` union improves name coverage.

## Fixes applied in `feature/virt-perf-filter-mem-fix`

- Full-cluster fast path in `get_*_metrics_filtered`
- Redis cache for `/compute/classic` and `/compute/hyperconverged`
- Staged cluster filter (Apply + 800ms debounce) — no compute on every chip change
- Merged virt tab callbacks (panel + sellable + hosts + total in one batch per tab)
