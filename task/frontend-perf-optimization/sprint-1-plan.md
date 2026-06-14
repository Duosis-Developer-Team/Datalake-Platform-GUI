# Sprint 1 (Quick Wins) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Düşük riskli, küçük dokunuşlarla per-interaction maliyeti azalt, donma yerine "yükleniyor" göster, ve worker havuzuna nefes aldır — gerçek yapısal çözümlerden (P3 fan-out birleştirme, P5 lazy-mount) ÖNCE.

**Architecture:** Dash (gunicorn gthread, 1 worker / 4 thread) → FastAPI mikroservisler (`src/services/api_client.py`, httpx thread-local client'lar) + lokal DB (`db_service.py`). Tüm callback'ler senkron, off-thread iş yok. Bu sprint sadece GUI callback grafiği + httpx config + Dockerfile'a dokunur; backend kontratı değişmez.

**Tech Stack:** Python 3.10, Dash, dash-mantine-components 0.14.1, httpx, gunicorn, pytest/unittest.

**Test/commit kuralı:** TDD (önce başarısız test), madde başına 1 commit, hepsi `feature/frontend-perf-optimizations` branch'inde, sonunda tek PR.

> ⚠️ **Dürüst etki notu (doğrulamadan sonra):** "Virt sekmesini açınca donuyor"un baskın sebebi **P5 (nested lazy-mount) + B3 (lazy_tab full-tree build)** — bunlar Sprint 2. "Cluster ekle/çıkar donuyor"un baskın sebebi **P3 (4'lü fan-out) + RC-3 (cold cache)** — yine Sprint 2. Bu sprint bu donmaları **hafifletir** (daha hızlı per-call, fail-fast spinner, havuz nefesi), kökten bitirmez. Kök çözüm Sprint 2'de.
>
> ⚠️ **Sentez düzeltmesi:** Sentezdeki "MultiSelect'e `debounce=400` ekle" (P1) **yanlış** — dmc MultiSelect'te `debounce` sadece *arama kutusunu* debounce eder, chip ekle/çıkar `value` değişimini değil. P1 bu yüzden aşağıda spurious-mount-fire guard'ına göre yeniden tasarlandı.

---

## File Structure

| Dosya | Sorumluluk | Bu sprintteki değişiklik |
|-------|-----------|--------------------------|
| ~~`app.py:840,857`~~ | ~~Hosts panel callback'leri~~ | ~~P1~~ → **Sprint 2'ye (P3) ertelendi** |
| `src/services/api_client.py:300-324` | Sellable cache guard | P2a: meta çağrısını sadece veri boşken yap |
| `src/services/api_client.py:131-174` | httpx thread-local client'lar | P2b: `_client_crm`→thread-local · P4b: tight timeout |
| `src/pages/dc_view.py:1761-1814` | Virt nested sub-tab builder | P4a: çıktı Div'lerini `dcc.Loading`'e sar |
| `src/pages/dc_view.py:4768-4772,4818-4822` | SAN + backup serial I/O | P7: `parallel_execute` batch |
| `Dockerfile:33` | gunicorn komutu | P6: `--threads 4`→`8` |
| `tests/` | Birim testler | Her madde için yeni test |

---

## Task 1 (P1): ~~Hosts callback spurious mount-fire guard~~ → **SPRINT 2'YE ERTELENDİ**

**Review kararı (2026-06-14):** İptal/ertelendi. Doğrulama (context7 Dash docs + plotly/dash#1745) gösterdi ki `prevent_initial_call=True` dinamik eklenen component'lerde spurious mount-fire'ı **güvenilir durdurmuyor** — ucuz versiyon işe yaramaz, güvenilir versiyon (`dcc.Store` + set-eşitlik guard) **P3 ile birebir örtüşüyor**. Spurious-fire guard'ı **P3'te (Sprint 2)** callback'leri birleştirirken doğru şekilde ekleyeceğiz. Sprint 1 bu maddeyi atlar.

---

## Task 2 (P2a): Sellable cold path'inde gereksiz `get_sellable_snapshot_meta` çağrısını kaldır

**Mekanizma:** `_api_cache_get_sellable_panels` (`api_client.py:300`) her miss'te `fetch_normalized()` SONRASI **her zaman** `get_sellable_snapshot_meta()` (ikinci CRM round-trip) çağırıyor — oysa meta yalnızca payload boşken bir tiebreak. Veri varsa meta'ya gerek yok. 4 aile × cluster değişimi = gereksiz CRM çağrıları.

**Files:**
- Modify: `src/services/api_client.py:300-324`
- Test: `tests/test_api_client_sellable_cache.py` (mevcut dosyaya ekle)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_client_sellable_cache.py — append
def test_meta_not_called_when_panels_have_data(monkeypatch):
    """P2a: when fetch returns infra-backed data, snapshot meta must NOT be fetched."""
    from src.services import api_client as api
    from src.services import cache_service
    cache_service.clear()
    meta_calls = {"n": 0}

    def fake_meta(*args, **kwargs):
        meta_calls["n"] += 1
        return {"computed_at": None}

    def fetch():
        return [{"panel_key": "dc_cpu", "potential_tl": 1200.0, "has_infra_source": True}]

    monkeypatch.setattr(api, "get_sellable_snapshot_meta", fake_meta)
    out = api._api_cache_get_sellable_panels("k-data", fetch, "DC13", "virt_classic", None)
    assert out == [{"panel_key": "dc_cpu", "potential_tl": 1200.0, "has_infra_source": True}]
    assert meta_calls["n"] == 0          # meta skipped on the warm/data path
    assert cache_service.get("k-data") == out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_client_sellable_cache.py::test_meta_not_called_when_panels_have_data -v`
Expected: FAIL with `assert 1 == 0` (meta currently always called).

- [ ] **Step 3: Apply the fix** — `api_client.py:300-324`

```python
def _api_cache_get_sellable_panels(
    cache_key: str,
    fetch_normalized: Callable[[], list],
    dc_code: str,
    family: Optional[str],
    clusters: Optional[list[str]],
) -> list:
    stale = _api_response_cache.get(cache_key)
    if stale is not None:
        return _clone(stale)
    try:
        out = fetch_normalized()
        # Fast path: data present -> cache & return without the extra meta round-trip.
        if _sellable_panels_have_data(out):
            _api_response_cache.set(cache_key, out)
            return out
        # Empty payload: meta.computed_at is the tiebreak (real-but-zero vs transient miss).
        meta = get_sellable_snapshot_meta(dc_code=dc_code, family=family, clusters=clusters)
        if meta.get("computed_at"):
            _api_response_cache.set(cache_key, out)
            return out
        hit = _api_response_cache.get(cache_key)
        if hit is not None:
            return _clone(hit)
        return out
    except _HTTP_ERRORS:
        hit = _api_response_cache.get(cache_key)
        if hit is not None:
            return _clone(hit)
        return []
```

- [ ] **Step 4: Run tests to verify all sellable cache tests pass**

Run: `pytest tests/test_api_client_sellable_cache.py -v`
Expected: PASS — new test + existing `test_api_cache_get_sellable_panels_skips_transient_zero` (meta still called on empty payload) + `test_api_cache_get_sellable_panels_returns_stale_on_empty_refresh` all green.

- [ ] **Step 5: Commit**

```bash
git add src/services/api_client.py tests/test_api_client_sellable_cache.py
git commit -m "perf(api-client): skip snapshot-meta round-trip on sellable data path (P2a)"
```

---

## Task 3 (P2b): `_client_crm`'i thread-local yap

**Mekanizma:** `_client_crm` (`api_client.py:172`) tek modül-seviye httpx.Client. Diğer hepsi thread-local (`_get_client_dc` vb.). `collect_virt_sellable_panels` 4-worker thread pool ile CRM'e paralel vurunca, paylaşılan client'ın bağlantı havuzunda çekişme → 30s timeout riski. httpx.Client thread-safe değil (dosyanın kendi yorumu uyarıyor).

**Files:**
- Modify: `src/services/api_client.py:171-174` (+ tüm `_client_crm` kullanımları)
- Test: `tests/test_api_client_crm_threadlocal.py` (Create)

- [ ] **Step 1: Inventory call-sites** (uygulamadan önce)

Run: `grep -n "_client_crm" src/services/api_client.py`
Expected: tüm kullanımları listeler (fetch çağrıları + admin refresh target `lambda: _client_crm` ~2189). Hepsi `_get_client_crm()`'e dönecek.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_api_client_crm_threadlocal.py
"""P2b: CRM httpx client must be thread-local (one client per thread)."""
import threading
from src.services import api_client as api


def test_get_client_crm_is_thread_local():
    assert hasattr(api, "_get_client_crm"), "expected a _get_client_crm() accessor"
    main_client = api._get_client_crm()
    assert main_client is api._get_client_crm()  # stable within a thread

    other = {}
    def worker():
        other["client"] = api._get_client_crm()
    t = threading.Thread(target=worker)
    t.start(); t.join()
    assert other["client"] is not main_client  # different thread -> different client
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_api_client_crm_threadlocal.py -v`
Expected: FAIL (`_get_client_crm` yok).

- [ ] **Step 4: Apply the fix** — `api_client.py:171-174` (mirror `_get_client_dc`):

```python
def _get_client_crm() -> httpx.Client:
    c = getattr(_HTTP_TLS, "crm", None)
    if c is None:
        _HTTP_TLS.crm = httpx.Client(
            base_url=CRM_ENGINE_URL, timeout=30.0, transport=_new_http_transport()
        )
        c = _HTTP_TLS.crm
    return c
```

Sonra **tüm** `_client_crm` kullanımlarını `_get_client_crm()` ile değiştir. Admin refresh target'ında (`api_client.py:~2189`): `("crm_engine", lambda: _client_crm)` → `("crm_engine", _get_client_crm)`. Eski modül-seviye `_client_crm = httpx.Client(...)` tanımını sil.

> Step 1'deki grep çıktısındaki her satırı tek tek dönüştür; hiçbir `_client_crm` referansı kalmamalı.

- [ ] **Step 5: Run tests + grep guard**

Run: `pytest tests/test_api_client_crm_threadlocal.py -v && grep -n "_client_crm\b" src/services/api_client.py || echo "no bare _client_crm left"`
Expected: PASS + sadece `_get_client_crm` referansları kalmış.

- [ ] **Step 6: Commit**

```bash
git add src/services/api_client.py tests/test_api_client_crm_threadlocal.py
git commit -m "perf(api-client): make CRM httpx client thread-local to avoid pool contention (P2b)"
```

---

## Task 4 (P4a): Virt çıktı Div'lerini `dcc.Loading`'e sar

**Mekanizma:** Cluster değişiminde callback dönene kadar (cold fetch'te saniyeler) çıktı Div'i sessiz kalıyor → kullanıcı donma sanıyor. `dcc.Loading` ile spinner gösterilir. Repo deseni mevcut: `dc_view.py:4595` (`type="circle"`, `delay_show`).

**Files:**
- Modify: `src/pages/dc_view.py:1761-1814` (`_build_virt_subtab_stack` — `classic-virt-panel`, `hyperconv-virt-panel`, `sellable-*-card` Div'leri)
- Test: `tests/test_virt_loading_wrappers.py` (Create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_virt_loading_wrappers.py
"""P4a: Virt compute panels must be wrapped in dcc.Loading so cold fetches show a spinner."""
from dash import dcc
from src.pages import dc_view


def _has_loading_around(component, target_id: str) -> bool:
    """DFS: is there a dcc.Loading whose subtree contains a child with id==target_id?"""
    found = {"loading_ancestor": False}

    def walk(node, under_loading):
        if getattr(node, "id", None) == target_id and under_loading:
            found["loading_ancestor"] = True
        children = getattr(node, "children", None)
        now = under_loading or isinstance(node, dcc.Loading)
        if isinstance(children, (list, tuple)):
            for ch in children:
                if ch is not None:
                    walk(ch, now)
        elif children is not None and hasattr(children, "children"):
            walk(children, now)
    for top in component:
        if top is not None:
            walk(top, False)
    return found["loading_ancestor"]


def test_classic_panel_wrapped_in_loading():
    stack = dc_view._build_virt_subtab_stack(
        "classic", dc_id="DC13", classic={}, hyperconv={}, power={}, energy={},
        classic_clusters=["DC13-KM-01"], hyperconv_clusters=[], storage_capacity={},
        storage_performance={}, san_bottleneck={}, show_virt_hosts=False,
    )
    assert _has_loading_around(stack, "classic-virt-panel")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_virt_loading_wrappers.py -v`
Expected: FAIL (panel not under a `dcc.Loading`).

- [ ] **Step 3: Apply the fix** — `dc_view.py`, classic branch of `_build_virt_subtab_stack`:

```python
    if tab == "classic":
        card = _build_sellable_inline_kpi(
            dc_id, "virt_classic", "Klasik Mimari — Sellable Potential",
            color="blue", selected_clusters=classic_clusters or None,
            container_id="sellable-classic-card",
        )
        return [
            _cluster_header("virt-classic-cluster-selector", classic_clusters or [], "Select Classic clusters"),
            dcc.Loading(
                type="circle", color="#4318FF", delay_show=250,
                overlay_style={"visibility": "visible", "backgroundColor": "rgba(244, 247, 254, 0.6)"},
                children=html.Div(
                    id="classic-virt-panel",
                    children=_build_compute_tab(classic, "Classic Compute", color="blue", slug="classic"),
                ),
            ),
            html.Div(id="sellable-classic-card", children=_sellable_card_children(card)),
            _build_hosts_panel_shell("classic", "blue") if show_virt_hosts else None,
        ]
```

Hyperconv branch'ine de aynısını uygula (`hyperconv-virt-panel` Div'ini `dcc.Loading`'e sar, `color="teal"` korunur). `dcc`'nin import edildiğini doğrula (dc_view zaten `dcc.Loading` kullanıyor, `4595`).

> ⚠️ `html.Div(id="classic-virt-panel")` Output id'si AYNI kalmalı — sadece `dcc.Loading` ile sarılıyor. Callback Output'ları değişmez.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_virt_loading_wrappers.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pages/dc_view.py tests/test_virt_loading_wrappers.py
git commit -m "feat(dc-view): wrap Virt compute panels in dcc.Loading for cold-fetch feedback (P4a)"
```

---

## Task 5 (P4b): Interactive httpx client'larda timeout'u sıkılaştır (fail-fast)

**Mekanizma:** Interactive client'lar (`_get_client_dc/cust/query/hmdl` + P2b sonrası `crm`) `timeout=30.0` kullanıyor → cold/yavaş upstream thread'i 30s tutuyor. Tight timeout ile interactive çağrı saniyeler içinde stale/empty'e düşer (UI canlı kalır). Admin warm-refresh path'i kendi per-request `httpx.Timeout(600.0, connect=30.0)` override'ını kullanıyor (`api_client.py:~2185`) → **etkilenmez**. Background prefetch da aynı client'ları kullanır ama best-effort + stale fallback → hızlı vazgeçip stale servis etmesi kabul edilebilir.

**Files:**
- Modify: `src/services/api_client.py:131-168` (+ P2b'deki `_get_client_crm`)
- Test: `tests/test_api_client_timeouts.py` (Create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_client_timeouts.py
"""P4b: interactive httpx clients use a tight read timeout (fail-fast), not 30s."""
import httpx
from src.services import api_client as api


def test_interactive_clients_have_tight_read_timeout():
    for getter in (api._get_client_dc, api._get_client_cust, api._get_client_query, api._get_client_hmdl):
        client = getter()
        assert isinstance(client.timeout, httpx.Timeout)
        assert client.timeout.read is not None and client.timeout.read <= 8.0
        assert client.timeout.connect is not None and client.timeout.connect <= 3.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_client_timeouts.py -v`
Expected: FAIL (`timeout=30.0` → `client.timeout.read == 30.0`).

- [ ] **Step 3: Apply the fix** — add a shared interactive timeout constant near the client accessors and use it in all of them:

```python
# Interactive callbacks must fail fast (UI stays alive); warm/admin paths pass their own per-request timeout.
_INTERACTIVE_TIMEOUT = httpx.Timeout(8.0, connect=3.0, read=8.0, write=8.0, pool=3.0)
```

Sonra `_get_client_dc/cust/query/hmdl` (ve P2b'deki `_get_client_crm`) içindeki `timeout=30.0` → `timeout=_INTERACTIVE_TIMEOUT`. Örnek:

```python
def _get_client_dc() -> httpx.Client:
    c = getattr(_HTTP_TLS, "dc", None)
    if c is None:
        _HTTP_TLS.dc = httpx.Client(
            base_url=DATACENTER_API_URL, timeout=_INTERACTIVE_TIMEOUT, transport=_new_http_transport()
        )
        c = _HTTP_TLS.dc
    return c
```

- [ ] **Step 4: Run tests to verify pass (+ no regression in sellable/cluster tests)**

Run: `pytest tests/test_api_client_timeouts.py tests/test_api_client_sellable_cache.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/api_client.py tests/test_api_client_timeouts.py
git commit -m "perf(api-client): fail-fast interactive httpx timeouts; warm/admin keep own override (P4b)"
```

> 📌 **Tunable:** `read=8.0` p95/p99 ölçümü olmadan seçilen makul interactive tavan. Gerçek DC13 metriklerinden sonra ayarlanmalı (çok düşükse yavaş-ama-geçerli yanıtlar boşalır).

---

## Task 6 (P6): gunicorn thread sayısını artır (havuz nefesi)

**Mekanizma:** `--workers 1 --threads 4` → 4 eşzamanlı bloklayan callback tüm pod'u dondurur. `--threads 8` headroom verir. `--workers 1` KALIR (çoğullarsa in-process `cache_service._cache` parçalanır, Redis yok). Tek başına çözüm değil — P3 ile eşleşmeli (yoksa yükü downstream'e iter).

**Files:**
- Modify: `Dockerfile:33`
- Test: `tests/test_dockerfile_gunicorn.py` (Create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dockerfile_gunicorn.py
"""P6: gunicorn runs with >=8 threads and exactly 1 worker (single in-process cache)."""
from pathlib import Path


def test_gunicorn_threads_and_single_worker():
    cmd = Path("Dockerfile").read_text(encoding="utf-8")
    assert '"--workers", "1"' in cmd, "must stay single-worker (in-process cache)"
    assert '"--threads", "8"' in cmd, "threads should be raised to 8"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dockerfile_gunicorn.py -v`
Expected: FAIL (`"--threads", "4"`).

- [ ] **Step 3: Apply the fix** — `Dockerfile:33`, `"--threads", "4"` → `"--threads", "8"`. Satırın geri kalanı (workers 1, timeout 300, max-requests vb.) AYNEN kalır.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dockerfile_gunicorn.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile tests/test_dockerfile_gunicorn.py
git commit -m "perf(deploy): raise gunicorn threads 4->8, keep single worker (P6)"
```

---

## Task 7 (P7): SAN + backup serial I/O bloklarını `parallel_execute`'a al

**Mekanizma:** `build_dc_view` içinde Storage tab'ı için 3 SAN çağrısı (`dc_view.py:4768-4772`) ve Backup tab'ı için 3 çağrı (`4818-4822`) **serial**. Bağımsızlar → `parallel_execute` ile tek thread'de eşzamanlı, ~3× cold wall-clock kazancı. (Virt'i etkilemez; Storage/Backup tab'ı.) Net tab'ı zaten paralel (`4790`), desen örnek.

**Files:**
- Modify: `src/pages/dc_view.py:4768-4772`, `4818-4822`
- Test: `tests/test_dc_view_parallel_io.py` (Create)

- [ ] **Step 1: Write the failing test** (statik: serial yerine `parallel_execute` kullanıldığını doğrula)

```python
# tests/test_dc_view_parallel_io.py
"""P7: SAN and backup fetch groups must be issued via parallel_execute, not serially."""
import ast
from pathlib import Path


def _func_source(name: str) -> str:
    src = Path("src/pages/dc_view.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node) or ""
    raise AssertionError(f"{name} not found")


def test_san_and_backup_use_parallel_execute():
    body = _func_source("build_dc_view")
    # SAN group keys present inside a parallel_execute task dict
    assert "get_dc_san_port_usage" in body and "get_dc_san_health" in body
    assert "get_dc_netbackup_pools" in body and "get_dc_zerto_sites" in body
    # The serial three-in-a-row assignment pattern must be gone; parallel_execute used for both groups.
    assert body.count("parallel_execute") >= 4  # net + storage (existing) + san + backup (new)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dc_view_parallel_io.py -v`
Expected: FAIL (`parallel_execute` count < 4; SAN/backup still serial).

- [ ] **Step 3: Apply the fix**

SAN bloğu `dc_view.py:4768-4772`:

```python
    if _tab_eager(eager_tabs, "storage") and has_san:
        san_batch = parallel_execute(
            {
                "port_usage": lambda: api.get_dc_san_port_usage(dc_id, tr),
                "health": lambda: api.get_dc_san_health(dc_id, tr),
                "traffic": lambda: api.get_dc_san_traffic_trend(dc_id, tr),
            }
        )
        san_port_usage = san_batch["port_usage"]
        san_health_alerts = san_batch["health"]
        san_traffic_trend = san_batch["traffic"]
        _log_dc_build_phase(str(dc_id), "san", t_san)
    else:
        san_port_usage = {}
        san_health_alerts = []
        san_traffic_trend = []
```

Backup bloğu `dc_view.py:4818-4822`:

```python
    if _tab_eager(eager_tabs, "backup"):
        backup_batch = parallel_execute(
            {
                "nb": lambda: api.get_dc_netbackup_pools(dc_id, tr),
                "zerto": lambda: api.get_dc_zerto_sites(dc_id, tr),
                "veeam": lambda: api.get_dc_veeam_repos(dc_id, tr),
            }
        )
        nb_data = backup_batch["nb"]
        zerto_data = backup_batch["zerto"]
        veeam_data = backup_batch["veeam"]
        _log_dc_build_phase(str(dc_id), "backup", t_backup)
    else:
        nb_data = {"pools": []}
        zerto_data = {"sites": []}
        veeam_data = {"repos": []}
```

> `parallel_execute` zaten import edili (`4790` ve `4869` kullanıyor). Çıktı değişken adları (`san_port_usage`, `nb_data` vb.) ve else dalları AYNEN korunur ki downstream kullanım bozulmasın.

- [ ] **Step 4: Run test + broader dc_view tests to verify no regression**

Run: `pytest tests/test_dc_view_parallel_io.py -v && pytest tests/ -k "dc_view or dc view" -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pages/dc_view.py tests/test_dc_view_parallel_io.py
git commit -m "perf(dc-view): parallelize SAN and backup fetch groups (P7)"
```

---

## Task 8: Sprint kapanışı — tam test + PR

- [ ] **Step 1: Run the full suite**

Run: `pytest tests/ -q`
Expected: tüm testler PASS (7 yeni test + mevcutlar). Kırmızı varsa düzelt.

- [ ] **Step 2: Lint (hmdl-api dışı; bu sprint hmdl-api'ye dokunmuyor)** — değiştirilen servisler lint kapsamında değil ama yine de:

Run: `python -m ruff check src/ app.py --select E,F,W --ignore E501 || true`
Expected: bu sprintteki dosyalarda yeni hata yok.

- [ ] **Step 3: Push + PR**

```bash
git push origin feature/frontend-perf-optimizations
gh pr create --base main --head feature/frontend-perf-optimizations \
  --title "Frontend perf — Sprint 1 quick wins (P1,P2,P4,P6,P7)" \
  --body "Bkz. task/frontend-perf-optimization/sprint-1-plan.md. Düşük riskli quick win'ler; yapısal P3/P5 Sprint 2'de."
```

---

## Self-Review (writing-plans)

**Spec coverage:** Sprint 1 maddeleri P1, P2a, P2b, P4a, P4b, P6, P7 → Task 1-7. ✓ (P2 backlog'da P2a+P2b iki alt-madde → Task 2 + Task 3.)
**Placeholder scan:** Her kod adımı gerçek kod içeriyor; TBD/TODO yok. ✓
**Type/isim tutarlılığı:** `_get_client_crm` (Task 3) → Task 5'te kullanılıyor (tutarlı). `_INTERACTIVE_TIMEOUT` Task 5'te tanımlı. Output id'leri (`classic-virt-panel` vb.) Task 4'te korunuyor. ✓
**Bilinen sapmalar:** P1 sentezdeki "debounce"tan farklı (doğrulama gereği); dürüst etki notu eklendi (kök çözüm Sprint 2). ✓

## Execution Handoff

Plan kaydedildi: `task/frontend-perf-optimization/sprint-1-plan.md`. İki uygulama seçeneği:
1. **Subagent-Driven (önerilen)** — her task için taze subagent, aralarda review, hızlı iterasyon.
2. **Inline Execution** — bu session'da batch + checkpoint'lerle.
