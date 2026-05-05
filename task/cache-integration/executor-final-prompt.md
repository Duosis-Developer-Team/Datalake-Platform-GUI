You are the Executor for Datalake-Platform-GUI.

Objective (final pass):
Stabilize and optimize Global View prefetch + floor-map/rack click performance with measurable latency guarantees. Do not do speculative refactors; optimize only hot paths that affect:
1) globe pin -> floor map open latency,
2) first/second rack click detail latency,
3) prefetch completion reliability.

Current measured baseline (from runtime benchmark in app container)
- Global prefetch (all DCs, 12 DC / 189 racks):
  - phase critical_ms ~= 171 ms
  - phase device_ms ~= 88 ms
  - total_ms ~= 259 ms
- `gv.warm(tr)` return latency ~= 295 ms (non-blocking device phase)
- Cold (sample DC13):
  - summary ~= 119.25 ms
  - dc_details ~= 1.28 ms
  - dc_racks ~= 4.49 ms
  - rack_devices first two ~= [1.26, 1.10] ms
- Warm (same process):
  - summary ~= 0.45 ms
  - dc_details ~= 0.06 ms
  - dc_racks ~= 1.09 ms
  - rack_devices first pass avg ~= 0.26 ms
  - rack_devices second pass avg ~= 0.20 ms
- Floor-map figure build (DC13, 78 racks):
  - cold ~= 46.71 ms
  - warm ~= 0.06 ms
- DC13 priority warm (`warm_dc_priority`) full elapsed ~= 8601 ms

Interpretation:
- Backend/API cache is mostly hot and very fast in synthetic runs.
- User still reports real UI slowness; likely callback sequencing/contention or prefetch timing visibility issues rather than single API endpoint cost.

Must-do implementation plan
1) Add explicit “prefetch readiness” state to UI
   - `is_warm(tr)` is currently not consumed.
   - Expose warm state + latest stats in a store and consume it in globe->building->floor map flow.
   - If not warm, run targeted fast-path for selected DC and prevent full-path contention.

2) Make prefetch cooperative with user interaction
   - When current mode is floor_map/building for a selected DC, lower/park Phase-2 workers.
   - Resume when interaction quiets down.
   - Ensure `warm_dc_priority(dc_id)` has priority over global phase-2 queue.

3) Remove duplicate/racing warm jobs
   - Guard against redundant `warm_dc_priority` calls for same DC while one is active.
   - Keep bounded in-flight map keyed by dc_id + tr key.

4) Optimize floor-map transition path end-to-end
   - Time and log:
     a) pin click callback,
     b) building-reveal -> floor-map callback,
     c) rack detail callback.
   - Ensure floor-map callback does not trigger heavyweight unrelated work.

5) Keep cache behavior deterministic
   - Preserve thread-local HTTP clients in app `api_client`.
   - Preserve LRU semantics for app cache.
   - Do not regress datacenter-api cache_backend (`SET NX` on memory-hit backfill).

6) Add/extend tests
   - Unit tests for prefetch in-flight guards and priority warm dedupe.
   - Callback-level tests (or integration-light tests) for warm state gating and mode-dependent throttling.

Acceptance criteria (hard)
- Warm path rack click p95 < 500 ms (measured in runtime logs, not just unit tests).
- Pin -> floor-map p95 < 1200 ms on warmed state.
- During active user interaction, no prefetch storm (bounded worker usage proven by logs).
- No regression in existing tests; add tests for new throttling/guard logic.

Output format required from Executor
1) Root-cause summary (2-4 bullets).
2) Exact files changed + why.
3) Before/after metrics table (critical_ms/device_ms/total_ms, pin->floor, rack click p50/p95).
4) Risk notes and any remaining edge cases.

Constraints
- Avoid broad architectural rewrites.
- Keep changes small, measurable, and reversible.
- If a hypothesis is disproven by logs, remove that attempted code path.
