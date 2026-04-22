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

## 4a. Production resolution: TTL=3600 + last_good key + distributed lock

The following decisions close the gap identified in §4. They apply to the **microservice stack** and are binding for production deployments. Implementation is tracked in Faz 1 of [PROD_ARCHITECTURE.md](PROD_ARCHITECTURE.md).

### 4a.1 TTL / refresh ratio fix

| Parameter | Dev (broken) | Production (fixed) |
|-----------|-------------|--------------------|
| `CUSTOMER_DATA_CACHE_TTL_SECONDS` | 900 s | **3 600 s** |
| `CLUSTER_ARCH_MAP_TTL_SECONDS` | 900 s | **3 600 s** |
| `cache_ttl_seconds` (Settings) | 900 s | **3 600 s** |
| Scheduler refresh interval | 15 min (900 s) | 15 min (unchanged) |
| Ratio TTL / refresh | **1×** (race condition) | **4×** (safe) |

With TTL=3600 and refresh every 900 s, a key is overwritten 4 times before it can expire. Even if two consecutive refreshes fail (DB timeout, etc.), the key still serves stale data for up to 1 hour — matching the "old data until new data" pillar.

### 4a.2 last_good shadow key

Each successful `cache_set` also writes a shadow key `{key}:last_good` with TTL = `cache_ttl_seconds * 2` (7 200 s). On `QueryTimeoutError` or DB failure in the request path:

1. Try primary key → miss or expired → skip.
2. Try `{key}:last_good` → serve stale data with a response header `X-Cache: stale`.
3. Only return 503 if both keys are absent.

This gives users visibility into data freshness while preventing empty pages during temporary DB outages.

### 4a.3 Distributed singleflight (multi-replica safety)

The current `threading.Event` in `cache_run_singleflight` deduplicates within a **single process**. With 3 replicas, 3 concurrent cache misses on the same key each trigger a separate DB query, causing a cache stampede.

**Production pattern** — Redis-based distributed lock:

```python
import uuid, time

LOCK_TTL = 30          # seconds
POLL_INTERVAL = 0.2    # seconds
MAX_WAIT = 25          # seconds

def cache_run_distributed_singleflight(key: str, factory, ttl=None):
    val = cache_get(key)
    if val is not None:
        return val

    lock_key = f"lock:{key}"
    pod_id = str(uuid.uuid4())

    # Try to acquire lock (NX = only if not exists)
    acquired = redis_client.set(lock_key, pod_id, nx=True, ex=LOCK_TTL)
    if acquired:
        try:
            val = cache_get(key)   # re-check after acquiring
            if val is not None:
                return val
            val = factory()
            cache_set(key, val, ttl=ttl)
            # Write last_good shadow key with 2x TTL
            cache_set(f"{key}:last_good", val, ttl=(ttl or settings.cache_ttl_seconds) * 2)
            return val
        finally:
            # Release lock only if we still own it (Lua for atomicity)
            redis_client.eval(
                "if redis.call('get',KEYS[1])==ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end",
                1, lock_key, pod_id
            )
    else:
        # Wait for leader to populate cache
        deadline = time.monotonic() + MAX_WAIT
        while time.monotonic() < deadline:
            time.sleep(POLL_INTERVAL)
            val = cache_get(key)
            if val is not None:
                return val
        # Timeout fallback — run factory to avoid starving the user
        return factory()
```

This pattern ensures exactly one DB query per cache miss across all replicas, regardless of concurrency. Keep the existing `threading.Event` singleflight as a secondary guard within each process.

### 4a.4 Cache warming CronJob (decoupled from pod lifecycle)

The current `warm_cache()` call in `start_scheduler` runs at pod startup. This means:
- Every rolling deploy causes a warmup phase during which new pods serve cold DB queries.
- HPA scale-out events (N new pods) each independently warm the cache, causing N × customer_count DB queries simultaneously.

**Production approach:** disable per-pod warmup on startup; delegate to a Kubernetes CronJob that runs every 15 minutes and calls a protected internal endpoint (`POST /api/v1/internal/warm-cache`). The CronJob runs independently of pod count, warming the shared Redis cache exactly once per interval.

Benefits:
- Pods start serving immediately via `last_good` keys (stale-while-revalidate).
- HPA scale-up is faster (no blocking warmup).
- Warmup failures are isolated and retryable via K8s Job backoff.

### 4a.5 WARMED_CUSTOMERS for production

Current setting `WARMED_CUSTOMERS=Boyner` warms only one customer. For production with 100+ customers:

- Set `WARMED_CUSTOMERS=` (empty string) so `_load_customer_names_from_db()` is used.
- The CronJob (§4a.4) warms all customers in parallel with `ThreadPoolExecutor(max_workers=4)`.
- Customers not yet in Redis at first request are served from `last_good` or trigger a single DB fetch via the distributed lock (§4a.3).

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
