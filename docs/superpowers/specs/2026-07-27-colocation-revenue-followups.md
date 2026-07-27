# Colocation Revenue — Follow-ups and Out-of-Scope Findings

**Date:** 2026-07-27
**Source:** work on [`2026-07-27-colocation-revenue-design.md`](2026-07-27-colocation-revenue-design.md)

These were found while building the colocation revenue feature and deliberately **not**
fixed there. Each is real, measured against production, and needs its own scope.

---

## 1. Currency preference never fires — virtualization potential may be priced in the wrong currency

**Severity: highest open item.**

`services/customer-api/app/db/queries/sellable.py:206` and
`services/datacenter-api/app/db/queries/crm_network_pricing.py:27` both sort with:

```sql
ORDER BY (pl.transactioncurrency_text = 'TL') DESC,
```

Measured on prod `bulutlake` 2026-07-27:

| Table | rows matching `'TL'` | rows matching `'Turkish Lira'` |
|---|---|---|
| `discovery_crm_pricelevels` | **0** | 1 |
| `discovery_crm_productpricelevels` | **0** | present for every product |

The literal `'TL'` matches nothing. Every row therefore ties at `FALSE`, the preference
never applies, and whichever row the tiebreaker happens to return decides the currency.
These queries may be returning USD or EUR amounts that the UI labels as TL.

**Why it matters more now.** This feeds the "Potential Sales (Virtualization)" figures.
The colocation work just placed "Potential Sales (Colocation)" — verifiably TL, filtered
on `transactioncurrency_text = 'Turkish Lira'` — directly beside it on the DC cards and
the platform KPI strip. A latent mislabel is now a visible, side-by-side comparison.

**Fix:** change the literal to `'Turkish Lira'`, or better, stop matching on the display
label at all and key off `transactioncurrencyid`. Then re-verify every figure that moved.

## 2. NetBox registers 25 racks under two datacenters with conflicting heights

25 racks at site `ISTANBUL` appear under two DC labels at once:

| Racks | DC labels | `u_height` values |
|---|---|---|
| 101-105, 201-205 | DC13, DH3 | **47 and 52** |
| 303-306 | DC13, DH3 | **42 and 52** |
| 109-119 | DC13, DH4 | 47 |

One physical rack cannot be both 47U and 52U. `_dedupe_physical_racks` resolves the
conflict by taking **MAX** capacity (pinned by tests in
`tests/test_colocation_occupancy.py`), so the surviving figure depends on which rows the
query returned — DC13 reports 2,629 total U when filtered to DC13 and 2,719 when not.

Every colocation capacity and revenue figure inherits that ambiguity. The platform is now
internally consistent (all surfaces use the per-DC path), but consistency is not accuracy.
**Fix at source in NetBox**, then re-measure.

## 3. Internal-tenant classification is fixed on only one of two services

`customer-api` now unions the Administration → Internal (Bulutistan) source mappings into
the internal-tenant prefix set. Two call sites still use the hardcoded builtins only:

- `services/datacenter-api/app/services/dc_service.py:7585` — `used_u_breakdown(cur, dc_pattern=pattern)`, no `internal_prefixes`
- `src/pages/floor_map.py:166` — `is_internal_tenant(t)`, no prefixes

Latent today because `gui_crm_customer_source_mapping` has zero rows. **The day an operator
adds their first internal mapping**, the Floor Map's External/Internal/Untagged bar and the
Colocation tab's bar will report different splits for the same datacenter — the exact class
of defect the colocation work set out to fix.

## 4. Colocation figures on the Datacenters page are not permission-gated

`src/pages/datacenters.py:651`, `:784`, `:1143` render colocation potential with no
permission check. `page:datacenters` defines only `sec:datacenters:grid` and
`action:datacenters:export`. Four other surfaces gate on `sec:dc_view:colocation`.

**Ruling for this release: accepted, recorded deliberately.** Free rack-U per DC is already
ungated on the Global View, and the added information is `free_u × list_price` — an
aggregate, no customer names. But the colocation work spent an escalation and a revert
specifically to preserve the `sec:dc_view:colocation` deny, so this asymmetry is a decision,
not an oversight. Revisit if colocation revenue becomes sensitive.

## 5. A test hangs indefinitely, and the GUI suite is order-dependent

`tests/test_dc_summary_arch_usage.py::test_rebuild_summary_includes_arch_usage` hangs
forever — a stale-mock bug where the patch covers the import but not a later unpatched
`DatabaseService()` instantiation. A hanging test can wedge CI.

Separately, the GUI suite's failure count is **order-dependent**:
`test_dc_view_capacity_table.py` yields 3 failures alone; `test_dc_view_lazy_tabs.py`
yields 2 alone and 4 when paired. Three reviewers measured three different totals. An A/B
checkout against merge base `034f12dc` produced identical results on both sides, so none of
it comes from the colocation branch — but it means no single pass/fail count is
reproducible, and a real regression could hide in the noise.

**Fix:** add `pytest-timeout`, then isolate the shared state causing the leakage.

## 6. Smaller items

- `api_client.get_colocation`'s total-outage fallback returns `{"aggregate": {}}` without
  the price keys, so a full customer-api outage renders four tiles while a DB-only outage
  renders five with `—`. One-line fix: add `unit_price_tl: None`, `free_u_potential_tl:
  None`, `price_source: "unavailable"` to that empty dict.
- Dead `"colo"` plumbing: `src/pages/dc_view.py:5042` `_LAZY_TAB_KEYS` and
  `src/pages/dc_view_callbacks.py:147` `Output("dc-tab-colo-root")`. Verified inert. The two
  must be removed together — `dc_view_callbacks.py:201-206` positionally couples the list
  length to the Output count.
- `tests/test_dc_display 2.py` — a stray duplicate file present since 2026-04-09.
- A pre-existing `NameError` in `_build_physical_inventory_dc_tab` (`rm_height` unset on the
  empty-manufacturer branch) was fixed in passing during this work. It has no test.

## 7. A code deploy does not take effect for 24h without clearing Redis DB 1

Found while verifying the first full rebuild, 2026-07-27. All ten images rebuilt
`--no-cache`, every container ran the new image, and the new bytecode was verified loaded —
yet `/api/v1/crm/colocation/{dc}` kept returning the *previous* payload shape.

Cause: `cache_get` (`services/customer-api/app/core/cache_backend.py:108`) falls back to a
`{key}:last_good` shadow entry with `LAST_GOOD_TTL_SECONDS = 86400` when the primary key
misses. Deleting the primary key — or letting the 6h singleflight TTL lapse — is not enough;
the 24h shadow keeps serving the old value.

**The trap that cost the most time:** these live in **Redis DB 1**, not DB 0. `redis-cli`
defaults to DB 0, so `redis-cli --scan --pattern '*colocation*'` reports nothing while 13
stale entries sit in DB 1. Use `redis-cli INFO keyspace` first, then `-n <db>`.

Clearing after a deploy that changes a payload shape:

```bash
docker exec bulutistan-redis redis-cli -n 1 --scan --pattern '*colocation*' \
  | while read k; do docker exec bulutistan-redis redis-cli -n 1 DEL "$k"; done
```

Worth a deploy step or a cache-version key that invalidates on schema change, the way
`CUSTOMER_ASSETS_CACHE_VERSION` already does elsewhere in this codebase. A stale-shape
response is worse than a slow one: consumers see missing fields, not an error.
