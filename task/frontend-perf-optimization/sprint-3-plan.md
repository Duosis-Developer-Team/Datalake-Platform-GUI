# Sprint 3 (Async / Cache) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** Cache-katmanı async kazanımları — aynı cold key'e eşzamanlı isteklerde tek fetch (C1), ve opsiyonel arka-plan tazeleme (C2). Worker'ı tamamen serbest bırakan background callback'ler (C3) ayrı bir altyapı kararı.

**Branch:** `feature/frontend-perf-sprint3` (worktree: `.claude/worktrees/sprint3`), Sprint 1+2 üstünde.

**Tech:** Python 3.10, threading, httpx, pytest. Cache: `src/services/cache_service.py` (thread-safe LRU OrderedDict, timestamp YOK). `_api_cache_get_with_stale` (api_client.py) cache-miss'te bloklayan fetch yapıyor.

---

## ⚠️ Dürüst kapsam çerçevesi (önce oku)

Sprint 1+2 zaten RC-1..RC-5'in çoğunu çözdü (P3 paralel fetch, P4b 30s→8s fail-fast, P5 lazy-mount, P8 host cache hit). Sprint 3 kalemlerinin **kalan marjinal değeri**:

- **C1 (request coalescing) — SOLİD, düşük risk, her zaman değerli.** Aynı pahalı cold key'e eşzamanlı N istek (cold page load'da çakışan callback'ler, veya çok kullanıcı) tek fetch'e iner. Net kazanç, contained (api_client). **→ Uygula.**
- **C2 (gerçek stale-while-revalidate) — KOŞULLU değer.** Bir combo'nun İKİNCİ erişiminde stale anında servis + arka planda tazele. Ama interaktif cluster combo'ları çoğu zaman tek-seferlik → "ikinci erişim" kazancı sınırlı. Mevcut warm/prefetch mekanizması zaten cache'i overwrite ediyor. **→ Sprint 1+2 testinden sonra karar ver.**
- **C3 (CeleryManager background callbacks) — YÜKSEK değer ama AĞIR altyapı.** Worker thread'i anında serbest + progress UX. Gerektirir: Celery worker + Redis broker, `k8s/frontend` deployment değişikliği, `render_main_content`'in Flask auth-context sorununun çözümü. Saf kod değişikliği DEĞİL — bir altyapı go/no-go kararı. **→ Ayrı initiative olarak scope'la.**

**Öneri:** Önce Sprint 1+2'yi rebuild edip test et. Donma büyük ölçüde geçtiyse, Sprint 3'ten yalnız **C1**'i uygula (ucuz sigorta), C2/C3'ü kalan gerçek soruna göre kararlaştır.

---

## Task 1 (C1): Request coalescing (single-flight) — aynı cold key'e tek fetch

**Mekanizma:** `_api_cache_get_with_stale` cache-miss'te her çağıran thread için ayrı `fetch_normalized()` çalıştırıyor. Aynı key'e eşzamanlı N miss = N özdeş pahalı upstream çağrısı. Per-key bir "in-flight" event ekle: ilk thread fetch eder, diğerleri onun sonucunu bekler. **Kritik:** cache'in global RLock'ını network sırasında TUTMA (tüm miss'leri serialize eder); ayrı, kısa tutulan bir `_inflight` lock kullan.

**Files:**
- Modify: `src/services/api_client.py` — `_api_cache_get_with_stale` (+ module-level `_inflight` map)
- Test: `tests/test_api_client_coalescing.py` (Create)

### Step 1: Write the failing test
```python
# tests/test_api_client_coalescing.py
"""C1: concurrent misses for the same key trigger exactly ONE fetch (single-flight)."""
import threading
import time
from src.services import api_client as api
from src.services import cache_service


def test_concurrent_misses_fetch_once():
    cache_service.clear()
    calls = {"n": 0}
    lock = threading.Lock()

    def slow_fetch():
        with lock:
            calls["n"] += 1
        time.sleep(0.3)  # simulate a slow cold upstream
        return {"v": 42}

    results = []
    def worker():
        results.append(api._api_cache_get_with_stale("coalesce-key", slow_fetch, {}))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()

    assert calls["n"] == 1, f"expected single-flight (1 fetch), got {calls['n']}"
    assert all(r == {"v": 42} for r in results)
    assert cache_service.get("coalesce-key") == {"v": 42}


def test_sequential_miss_then_hit_still_one_fetch():
    cache_service.clear()
    calls = {"n": 0}
    def fetch():
        calls["n"] += 1
        return {"v": 1}
    api._api_cache_get_with_stale("k-seq", fetch, {})
    api._api_cache_get_with_stale("k-seq", fetch, {})  # 2nd is a cache hit
    assert calls["n"] == 1
```

### Step 2: Run, confirm FAIL
`.venv/bin/python -m pytest tests/test_api_client_coalescing.py -v` → `test_concurrent_misses_fetch_once` FAILs (8 fetches).

### Step 3: Apply the fix — `_api_cache_get_with_stale`
Add module-level single-flight registry near the cache import:
```python
_inflight_lock = threading.Lock()
_inflight: dict[str, threading.Event] = {}
```
Rewrite the getter:
```python
def _api_cache_get_with_stale(
    cache_key: str,
    fetch_normalized: Callable[[], Any],
    empty_fallback: Any,
) -> Any:
    """Cached payload if present; else single-flight fetch (concurrent callers share one fetch).
    On HTTP/transport errors return last-good payload."""
    stale = _api_response_cache.get(cache_key)
    if stale is not None:
        return _clone(stale)

    # Single-flight: only one thread fetches a given key; others wait then read cache.
    with _inflight_lock:
        ev = _inflight.get(cache_key)
        leader = ev is None
        if leader:
            ev = threading.Event()
            _inflight[cache_key] = ev
    if not leader:
        ev.wait(timeout=15)
        hit = _api_response_cache.get(cache_key)
        return _clone(hit) if hit is not None else _clone(empty_fallback)

    # Leader path
    try:
        out = fetch_normalized()
        _api_response_cache.set(cache_key, out)
        return out
    except _HTTP_ERRORS:
        hit = _api_response_cache.get(cache_key)
        if hit is not None:
            return _clone(hit)
        return _clone(empty_fallback)
    finally:
        with _inflight_lock:
            _inflight.pop(cache_key, None)
        ev.set()
```
> `threading` is already imported (api_client uses `_HTTP_TLS = threading.local()`). The `_inflight_lock` is held only for dict ops (microseconds), NEVER during `fetch_normalized()` — so misses for DIFFERENT keys stay fully parallel.

### Step 4: Run tests (new + regression)
```
.venv/bin/python -m pytest tests/test_api_client_coalescing.py tests/test_api_client_sellable_cache.py tests/test_api_client_host_rows_slice.py tests/test_api_client_timeouts.py -v
.venv/bin/python -c "import src.services.api_client; print('import OK')"
```
Expected: all PASS.

### Step 5: Commit
```bash
git add src/services/api_client.py tests/test_api_client_coalescing.py
git commit -m "perf(api-client): single-flight request coalescing on cache miss (C1)"
```

---

## Task 2 (C2): Opsiyonel — arka-plan stale-while-revalidate

> **GATE:** Sprint 1+2 testinden sonra hâlâ "aynı combo'ya tekrar girince yavaş" şikayeti varsa uygula. Yoksa atla.

**Mekanizma:** `cache_service`'i değiştirmeden (cross-cutting riski yok), api_client'ta paralel bir `_fetched_at: dict[str, float]` tut. Getter cache hit'te entry'nin yaşına bak; `> TTL` ise mevcut değeri ANINDA dön + arka planda (modül-seviye `ThreadPoolExecutor`, küçük) tazeleme tetikle (C1 single-flight ile aynı key'i paylaşır → çift tazeleme yok). Caller asla bloklanmaz.

**Files:** `src/services/api_client.py`, `tests/test_api_client_swr.py`.
**Tasarım notu:** TTL'i env'den al (`API_CACHE_SWR_TTL`, default ör. 300s). `Date.now` yerine `time.monotonic()`. Bg executor max_workers küçük (2-3). Tazeleme hatası sessiz (stale servis edilmeye devam). Test: monkeypatch'le yaşlı entry → ilk get stale döner + bg fetch çağrılır (executor'ı senkron sahte ile).

*(Tam TDD adımları C1 onaylanıp Sprint 1+2 test sonucu geldikten sonra detaylandırılacak — şu an spec-level bırakıldı, YAGNI.)*

---

## Task 3 (C3): CeleryManager background callbacks — AYRI INITIATIVE (kod değil, altyapı kararı)

> Bu bir sprint-içi kod görevi DEĞİL. Gerektirir:
> 1. **Celery + Redis broker** (mevcut Redis kullanılabilir; `DiskcacheManager` DEĞİL — 2 replika, disk per-pod).
> 2. `k8s/frontend` deployment: Celery worker container/sidecar.
> 3. **Auth-context çözümü:** `render_main_content` (app.py) Flask `g.auth_user_id`/request context okuyor — Celery worker'da yok. Auth dispatch öncesi çözülmeli, ya da bu callback foreground kalmalı; `expand_dc_view_on_tab` daha uygun aday.
> 4. Hedef callback'ler: `expand_dc_view_on_tab` (dc_view_callbacks.py:131), gerekirse `render_main_content` (app.py:662) → `background=True` + `running=`/`progress=`.
>
> **Karar gerekli:** Celery/Redis altyapı yatırımı yapılacak mı? Yapılırsa ayrı bir plan (sprint-3c) yazılır. Sprint 1+2 donmayı yeterince çözdüyse ertelenebilir.

---

## Self-Review
- C1 tam TDD, contained, düşük risk → uygulanabilir.
- C2 spec-level + GATE'li (YAGNI — test sonucuna bağlı).
- C3 altyapı kararı olarak ayrıldı (kod görevi değil).
- `_inflight_lock` network sırasında tutulmuyor (farklı key'ler paralel kalır) — C1'in en kritik doğruluk noktası.

## Execution Handoff
Önce Sprint 1+2 rebuild + test. Sonra: **C1'i uygula** (subagent-driven, spec+quality review). C2/C3'ü test sonucuna göre karara bağla.
