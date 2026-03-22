# Cache strategy: legacy in-process vs Redis (design comparison)

This document compares the **legacy monolith cache** (Dash process + [`src/services/cache_service.py`](../src/services/cache_service.py)) with the **microservice cache** (Redis + in-process `TTLCache` in [`services/datacenter-api/app/core/cache_backend.py`](../services/datacenter-api/app/core/cache_backend.py) and the same pattern in `customer-api`).

It is aligned with the product goals below.

---

## 1. Intended cache behavior (design pillars)

| Pillar | Meaning |
|--------|---------|
| **Fast first paint** | Pages and report views should load quickly; users should not wait for cold DB queries on common paths. |
| **Pre-loaded time ranges** | Critical ranges (e.g. **1d, 7d, 30d** and related “previous month” style windows) are warmed so those presets hit cache. |
| **Periodic refresh** | Background jobs rebuild data on a fixed interval so content stays fresh without user-triggered full recomputation. |
| **Stale until replaced** | **Old cached data should remain served until new data is successfully written** — users prefer slightly stale data over empty or error states. |

Implementation details may differ between legacy and Redis; section 4 calls out gaps.

---

## 2. Legacy (monolith) stack — advantages

| Advantage | Why |
|-----------|-----|
| **Matches “no delete until replace” best** | The legacy [`cache_service`](../src/services/cache_service.py) stores values in a **plain dict** with **no time-based expiry**. Entries stay until **overwritten** by `set`, removed by `delete`/`clear`, or evicted only when **MAX_SIZE (512)** is exceeded (oldest key dropped). That is close to *“yeni veri gelmeden eski verinin silinmemesi”* for typical workloads. |
| **Single-process simplicity** | No network hop; no serialization protocol mismatch; trivial debugging. |
| **Integrated warm + refresh loop** | [`src/services/scheduler_service.py`](../src/services/scheduler_service.py) runs **`warm_cache()`** at startup and **`refresh_all_data()`** every **15 minutes** against [`DatabaseService`](../src/services/db_service.py), aligning with pre-load and periodic update goals. |
| **Predictable key space** | All consumers share one process — no cross-replica cache inconsistency. |

**Caveat:** At **512 keys**, oldest-key eviction can still drop data **without** a refresh — that is rare but contradicts the pillar if it happens.

---

## 3. Microservice stack (Redis + memory) — advantages

| Advantage | Why |
|-----------|-----|
| **Shared cache across replicas** | Multiple API pods/containers can share **one Redis**, improving hit rates under horizontal scaling (legacy per-process cache cannot). |
| **Survives process restart (partially)** | Redis data can outlive a single API restart (depending on Redis persistence and TTL); legacy cache is **lost** on restart unless rebuilt. |
| **Structured TTL for capacity** | Redis `SETEX` and `TTLCache` bound memory growth and avoid unbounded growth (legacy relies on **512** keys + manual discipline). |
| **Graceful degradation** | If Redis is down, [`redis_client.py`](../services/datacenter-api/app/core/redis_client.py) falls back to **memory-only** cache so the API still responds. |
| **Same warm/refresh idea in API** | [`services/datacenter-api/app/services/scheduler_service.py`](../services/datacenter-api/app/services/scheduler_service.py) still runs **`warm_cache()`** at startup and **`refresh_all_data()`** every **15 minutes** on `DatabaseService` in the API process — same rhythm as the monolith. |

---

## 4. Tension: TTL vs “old data until new data”

- **Legacy:** Comments in `cache_service` describe *stale-while-revalidate* intent; **no automatic TTL eviction** on the main dict supports **keeping old values** until the next successful `set` from `refresh_all_data` / request path.

- **Microservices:** `cache_backend` uses **Redis `SETEX`** and **`cachetools.TTLCache`** with **`cache_ttl_seconds`** (from settings). That means entries **can expire** even if no error occurred — **before** the next periodic refresh — which is **not** identical to “never remove until replaced.”

**Practical alignment:** If refresh runs every **15 minutes**, setting **`cache_ttl_seconds` >> 15 minutes** (e.g. hours) keeps behavior close to the pillar while still allowing Redis to reclaim space. Alternatively, evolve the backend to **write-through only** (no expiry, or refresh extends TTL) to match legacy semantics exactly.

---

## 5. Summary table

| Topic | Legacy in-process | Redis + TTLCache (APIs) |
|-------|-------------------|-------------------------|
| **Primary goal: fast UI** | Yes (warm + periodic refresh) | Yes (same scheduler pattern + optional shared hits) |
| **Pre-loaded ranges** | `warm_cache` / `warm_additional_ranges` in `DatabaseService` | Same pattern in datacenter-api `DatabaseService` |
| **Periodic update** | ~15 min `refresh_all_data` | Same |
| **Old data until new write** | Strong (no TTL on dict) | Weaker unless TTL is very long or policy adjusted |
| **Multi-instance consistency** | N/A (single process) | Strong if all instances use same Redis |
| **Restart behavior** | Cache empty until warm | Redis may still hold keys (if TTL not elapsed) |

---

## 6. Related code entry points

| Component | Path |
|-----------|------|
| Legacy cache API | [`src/services/cache_service.py`](../src/services/cache_service.py) |
| Legacy scheduler | [`src/services/scheduler_service.py`](../src/services/scheduler_service.py) |
| API cache backend | [`services/datacenter-api/app/core/cache_backend.py`](../services/datacenter-api/app/core/cache_backend.py) |
| API scheduler | [`services/datacenter-api/app/services/scheduler_service.py`](../services/datacenter-api/app/services/scheduler_service.py) |

---

## 7. Topology cross-link

See also [TOPOLOGY_AND_SETUP.md](TOPOLOGY_AND_SETUP.md) (Redis role and environment variables).
