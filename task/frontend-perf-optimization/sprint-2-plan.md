# Sprint 2 (Structural) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement task-by-task with two-stage review (spec + quality). Steps use checkbox (`- [ ]`) syntax.

**Goal:** "Cluster ekle/çıkar" ve "DC13 Virt açılış" donmalarını **kökten** çöz — fan-out'u azalt, nested sub-tab'ların ağır içeriğini lazy-mount et, host-row subset toggle'ını cache hit'e çevir.

**Architecture:** Dash (`suppress_callback_exceptions=True`, app.py:63). Virt nested tabs (`dmc.Tabs id=virt-nested-tabs`) şu an **3 sub-tab'ı da eager kuruyor, switch callback'i YOK** (CSS toggle). Cluster selector'lar sub-tab stack'inin içinde. Branch: `feature/frontend-perf-sprint2` (Sprint 1 üstünde).

**Tech Stack:** Python 3.10, Dash, dash-mantine-components 0.14.1, httpx, pytest. `.venv` (3.11) repo kökünde mevcut.

**Test/commit:** TDD, madde başına commit. Sprint 1 fix'leri bu branch'te mevcut.

---

## Design Decisions (bağımlılık çözümleri — koda karşı doğrulandı)

1. **Selector'ları HER ZAMAN mount tut.** Nested tab'ı tamamen lazy yaparsak o tab'ın `virt-{tab}-cluster-selector`'ı kaybolur → total-card callback'i (her iki selector'a Input) ve per-tab callback'ler kırılır. Çözüm: P5'te selector + boş panel/sellable **shell**'leri eager kalsın; yalnız ağır `_build_compute_tab` (~18 gauge) + sellable içeriği lazy olsun.

2. **Shared-output → `allow_duplicate=True`.** `classic-virt-panel` ve `sellable-classic-card`'ı hem P3 selector-change callback'i hem P5 tab-switch callback'i yazacak. İkisi de aynı output'a yazdığı için P5 callback'inde `allow_duplicate=True` (Dash 2.16+ destekliyor) + `prevent_initial_call=True` şart.

3. **Sıra: P3 → P5 → P8.** P3 önce (selector callback'lerini birleştir), sonra P5 (lazy tab-switch callback'i birleştirilmiş builder'ı çağırsın), en son P8 (bağımsız, api_client). P5'i P3'ten önce yapmak shared-output koordinasyonunu zorlaştırır.

4. **`DuplicateCallback` haritası (Explore ile doğrulandı):** Şu an her Output'un TEK sahibi var. P3'te iki callback'i tek callback'e birleştirmek güvenli (eski callback'ler SİLİNİR). P5'te eklenen tab-switch callback'i shared output'a yazdığı için yalnız orada `allow_duplicate`.

5. **`build_virt_nested_subtab_panel` (dc_view.py:1838) ÖLÜ kod** — yalnız bir log string'inde adı geçiyor, hiç çağrılmıyor (Explore doğruladı). P5 bunu temel alacak ama shell/lazy modeline uyarlanacak.

---

## File Structure

| Dosya | Değişiklik |
|-------|-----------|
| `app.py:800-953` | P3: classic & hyperconv panel+sellable callback'lerini birleştir (`parallel_execute`) |
| `app.py` (yeni) | P5: `virt-nested-tabs.value` switch callback'i (lazy populate, `allow_duplicate`) |
| `src/pages/dc_view.py:1761-1822` | P5: `_build_virt_subtab_stack`'e `content_mode` ("full"\|"shell") param |
| `src/pages/dc_view.py:4999-5011` | P5: `_virt_nested_tab_panel` — sadece default tab "full", diğerleri "shell" |
| `src/services/api_client.py:776-803` | P8: host-row'ları full-fetch-cached + Python filtreleme |
| `tests/` | Her madde için yeni test |

---

## Task 1 (P3): Classic & Hyperconv panel+sellable callback'lerini birleştir

**Mekanizma:** Tek cluster değişimi `virt-classic-cluster-selector.value`'yu 3 callback'e tetikliyor (panel, hosts, sellable) — her biri ayrı thread bloklar. `classic-virt-panel` ve `sellable-classic-card` İKİSİ DE her zaman DOM'da (koşulsuz), bu yüzden güvenle tek callback'te birleştirilebilir; iki fetch `parallel_execute` ile tek thread'de eşzamanlı koşar. Hosts ayrı kalır (koşullu, `show_virt_hosts`). Total card ayrı kalır.

**Files:**
- Modify: `app.py` — `update_classic_virt_panel` (800-813) + `update_classic_sellable_card` (912-931) → tek callback; aynısı hyperconv (816-829 + 934-953)
- Test: `tests/test_virt_combined_callbacks.py` (Create)

### Step 1: Write the failing test
```python
# tests/test_virt_combined_callbacks.py
"""P3: classic/hyperconv panel+sellable served by ONE combined callback (not separate)."""
import ast
from pathlib import Path


def _function_names(src_path: str) -> set[str]:
    tree = ast.parse(Path(src_path).read_text(encoding="utf-8"))
    return {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}


def _callback_outputs(func_name: str) -> list[str]:
    """Return the Output id strings declared in func_name's @app.callback decorator."""
    src = Path("app.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            deco_src = ast.get_source_segment(src, node.decorator_list[0]) or ""
            import re
            return re.findall(r'Output\(\s*"([^"]+)"', deco_src)
    raise AssertionError(f"{func_name} not found")


def test_combined_classic_callback_owns_panel_and_sellable():
    names = _function_names("app.py")
    assert "update_classic_virt_block" in names, "expected combined callback update_classic_virt_block"
    # old separate callbacks must be gone
    assert "update_classic_virt_panel" not in names
    assert "update_classic_sellable_card" not in names
    outs = _callback_outputs("update_classic_virt_block")
    assert "classic-virt-panel" in outs and "sellable-classic-card" in outs


def test_combined_hyperconv_callback_owns_panel_and_sellable():
    names = _function_names("app.py")
    assert "update_hyperconv_virt_block" in names
    assert "update_hyperconv_virt_panel" not in names
    assert "update_hyperconv_sellable_card" not in names
    outs = _callback_outputs("update_hyperconv_virt_block")
    assert "hyperconv-virt-panel" in outs and "sellable-hyperconv-card" in outs
```

### Step 2: Run, confirm FAIL
`pytest tests/test_virt_combined_callbacks.py -v` → FAIL (combined callbacks don't exist; old ones do).

### Step 3: Apply the fix — replace classic panel + sellable callbacks (app.py:800-813 and 912-931) with ONE:
```python
@app.callback(
    dash.Output("classic-virt-panel", "children"),
    dash.Output("sellable-classic-card", "children"),
    dash.Input("virt-classic-cluster-selector", "value"),
    dash.Input("app-time-range", "data"),
    dash.State("url", "pathname"),
    prevent_initial_call=True,
)
def update_classic_virt_block(selected_clusters, time_range, pathname):
    dc_id = _dc_id_from_pathname(pathname)
    if not dc_id:
        return dash.no_update, dash.no_update
    tr = time_range or default_time_range()
    batch = parallel_execute({
        "metrics": lambda: api.get_classic_metrics_filtered(dc_id, selected_clusters, tr),
        "card": lambda: _build_sellable_inline_kpi(
            dc_id, "virt_classic", "Klasik Mimari — Sellable Potential",
            color="blue", selected_clusters=selected_clusters or None,
            container_id="sellable-classic-card",
        ),
    })
    panel = _build_compute_tab(batch["metrics"], "Classic Compute", color="blue")
    sellable = _sellable_card_children(batch["card"]) or html.Div(id="sellable-classic-card")
    return panel, sellable
```
Same for hyperconv — replace `update_hyperconv_virt_panel` (816-829) + `update_hyperconv_sellable_card` (934-953) with `update_hyperconv_virt_block` (outputs `hyperconv-virt-panel` + `sellable-hyperconv-card`, family `virt_hyperconverged`, color `teal`, "Hyperconverged Compute" / "Hyperconverged Mimari — Sellable Potential"). DELETE the 4 old functions.

Imports: `parallel_execute` — confirm imported in app.py (`grep -n parallel_execute app.py`); if absent, add `from src.utils.api_parallel import parallel_execute`. `_build_sellable_inline_kpi`, `_sellable_card_children`, `_build_compute_tab`, `_dc_id_from_pathname` are already imported (used by current callbacks).

> ⚠️ Keep `update_classic_hosts_panel`, `update_hyperconv_hosts_panel`, `update_virt_total_sellable_card` UNCHANGED — only panel+sellable merge.

### Step 4: Run tests + import sanity
```
pytest tests/test_virt_combined_callbacks.py -v
python -c "import app"   # must register callbacks with NO DuplicateCallback error
```
Expected: PASS; app imports clean (proves no duplicate Output ownership).

### Step 5: Commit
```bash
git add app.py tests/test_virt_combined_callbacks.py
git commit -m "perf(dc-view): merge classic/hyperconv panel+sellable into one parallel callback (P3)"
```

---

## Task 2 (P5): Nested Virt sub-tab'ların ağır içeriğini lazy-mount et

**Mekanizma:** `_virt_nested_tab_panel` 3 sub-tab'ı da eager kuruyor → DC13 Virt açılışında ~18×3 gauge + 3 sellable birden. Çözüm: yalnız `default_virt_tab` "full" kurulsun; diğer enabled tab'lar selector + BOŞ panel/sellable shell ile kurulsun (selector mount kalsın → coupling kırılmaz). `virt-nested-tabs.value` değişince aktif tab'ın içeriği doldurulsun (zaten varsa atla).

**Files:**
- Modify: `src/pages/dc_view.py` — `_build_virt_subtab_stack` (1761) `content_mode` param; `_virt_nested_tab_panel` (4999) default→"full", diğerleri→"shell"
- Modify: `app.py` — yeni `populate_virt_nested_tab` callback (`allow_duplicate=True`)
- Test: `tests/test_virt_lazy_mount.py` (Create)

### Step 1: Write the failing test
```python
# tests/test_virt_lazy_mount.py
"""P5: non-default Virt sub-tabs render selector + empty panel shell (heavy content deferred)."""
import ast
from pathlib import Path
from dash import html
from src.pages import dc_view


def _panel_children_count(stack, panel_id: str):
    """Find html.Div(id=panel_id) and return len of its children (0 = empty shell)."""
    found = {"node": None}

    def walk(node):
        if getattr(node, "id", None) == panel_id:
            found["node"] = node
        ch = getattr(node, "children", None)
        if isinstance(ch, (list, tuple)):
            for c in ch:
                if c is not None:
                    walk(c)
        elif ch is not None and hasattr(ch, "children"):
            walk(ch)
    for top in stack:
        if top is not None:
            walk(top)
    node = found["node"]
    assert node is not None, f"{panel_id} not found"
    ch = getattr(node, "children", None)
    if ch is None:
        return 0
    return len(ch) if isinstance(ch, (list, tuple)) else 1


def test_shell_mode_renders_selector_but_empty_panel():
    stack = dc_view._build_virt_subtab_stack(
        "classic", dc_id="DC13", classic={"hosts": 1}, hyperconv={}, power={}, energy={},
        classic_clusters=["DC13-KM-01"], hyperconv_clusters=[], storage_capacity={},
        storage_performance={}, san_bottleneck={}, show_virt_hosts=False,
        content_mode="shell",
    )
    # selector still present
    flat = repr(stack)
    assert "virt-classic-cluster-selector" in flat
    # panel is an empty shell
    assert _panel_children_count(stack, "classic-virt-panel") == 0


def test_full_mode_renders_populated_panel():
    stack = dc_view._build_virt_subtab_stack(
        "classic", dc_id="DC13", classic={"hosts": 1}, hyperconv={}, power={}, energy={},
        classic_clusters=["DC13-KM-01"], hyperconv_clusters=[], storage_capacity={},
        storage_performance={}, san_bottleneck={}, show_virt_hosts=False,
        content_mode="full",
    )
    assert _panel_children_count(stack, "classic-virt-panel") >= 1


def test_populate_callback_exists_with_allow_duplicate():
    src = Path("app.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "populate_virt_nested_tab":
            deco = ast.get_source_segment(src, node.decorator_list[0]) or ""
            assert "allow_duplicate=True" in deco
            assert "virt-nested-tabs" in deco
            return
    raise AssertionError("populate_virt_nested_tab callback not found")
```

### Step 2: Run, confirm FAIL
`pytest tests/test_virt_lazy_mount.py -v` → FAIL (`content_mode` kwarg unknown; callback missing).

### Step 3a: Add `content_mode` to `_build_virt_subtab_stack` (dc_view.py:1761)
Add param `content_mode: str = "full"` to the signature. In the classic & hyperconv branches, build the compute panel children only in full mode:
```python
    if tab == "classic":
        card = _build_sellable_inline_kpi(...)  # unchanged
        panel_children = (
            _build_compute_tab(classic, "Classic Compute", color="blue", slug="classic")
            if content_mode == "full" else None
        )
        sellable_children = _sellable_card_children(card) if content_mode == "full" else None
        return [
            _cluster_header("virt-classic-cluster-selector", classic_clusters or [], "Select Classic clusters"),
            dcc.Loading(
                type="circle", color="#4318FF", delay_show=250,
                overlay_style={"visibility": "visible", "backgroundColor": "rgba(244, 247, 254, 0.6)"},
                children=html.Div(id="classic-virt-panel", children=panel_children),
            ),
            html.Div(id="sellable-classic-card", children=sellable_children),
            _build_hosts_panel_shell("classic", "blue") if show_virt_hosts else None,
        ]
```
Same for hyperconv branch (gate `panel_children`/`sellable_children` on `content_mode == "full"`). Leave the Power branch always-full (no selector, single tab). `_build_hosts_panel_shell` stays (it's a shell already; its content is callback-driven).

### Step 3b: `_virt_nested_tab_panel` (dc_view.py:4999) — defer only non-default classic/hyperconv
```python
    def _virt_nested_tab_panel(tab_key: str, enabled: bool):
        """Virt nested tab body. Heavy content of non-default classic/hyperconv sub-tabs
        is deferred (shell); they are filled by populate_virt_nested_tab on first switch.
        Power is always built full (no cluster selector, not handled by the populate callback)."""
        if not enabled or not _tab_eager(eager_tabs, "virt"):
            return None
        if tab_key == "power":
            mode = "full"
        else:
            mode = "full" if tab_key == default_virt_tab else "shell"
        stack = _build_virt_subtab_stack(tab_key, content_mode=mode, **virt_subtab_kwargs)
        return dmc.TabsPanel(
            value=tab_key, pt="lg",
            children=dmc.Stack(gap="lg", children=[c for c in stack if c is not None]),
        )
```
> **Scope note:** Power is NOT lazy-mounted in this sprint (it has no cluster selector and is not handled by `populate_virt_nested_tab`; shell-ing it would leave it permanently empty — the bug this guard avoids). When the default tab is `classic` and `hyperconv` is enabled, this defers the hyperconv sub-tab's ~6 gauges + sellable — the common DC13 case. Deferring power too is a future enhancement (needs storage fetches in the populate callback).

### Step 3c: Add the populate callback in app.py (near the virt block callbacks)
```python
@app.callback(
    dash.Output("classic-virt-panel", "children", allow_duplicate=True),
    dash.Output("sellable-classic-card", "children", allow_duplicate=True),
    dash.Output("hyperconv-virt-panel", "children", allow_duplicate=True),
    dash.Output("sellable-hyperconv-card", "children", allow_duplicate=True),
    dash.Input("virt-nested-tabs", "value"),
    dash.State("virt-classic-cluster-selector", "value"),
    dash.State("virt-hyperconv-cluster-selector", "value"),
    dash.State("app-time-range", "data"),
    dash.State("url", "pathname"),
    dash.State("classic-virt-panel", "children"),
    dash.State("hyperconv-virt-panel", "children"),
    prevent_initial_call=True,
)
def populate_virt_nested_tab(active, classic_sel, hyperconv_sel, time_range, pathname,
                             classic_built, hyperconv_built):
    """Lazy-build the activated Virt sub-tab's heavy content the first time it is shown."""
    dc_id = _dc_id_from_pathname(pathname)
    if not dc_id:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update
    tr = time_range or default_time_range()
    no = dash.no_update
    if active == "classic" and not classic_built:
        metrics = api.get_classic_metrics_filtered(dc_id, classic_sel, tr)
        card = _build_sellable_inline_kpi(
            dc_id, "virt_classic", "Klasik Mimari — Sellable Potential",
            color="blue", selected_clusters=classic_sel or None, container_id="sellable-classic-card",
        )
        return (_build_compute_tab(metrics, "Classic Compute", color="blue"),
                _sellable_card_children(card) or html.Div(id="sellable-classic-card"), no, no)
    if active == "hyperconv" and not hyperconv_built:
        metrics = api.get_hyperconv_metrics_filtered(dc_id, hyperconv_sel, tr)
        card = _build_sellable_inline_kpi(
            dc_id, "virt_hyperconverged", "Hyperconverged Mimari — Sellable Potential",
            color="teal", selected_clusters=hyperconv_sel or None, container_id="sellable-hyperconv-card",
        )
        return (no, no, _build_compute_tab(metrics, "Hyperconverged Compute", color="teal"),
                _sellable_card_children(card) or html.Div(id="sellable-hyperconv-card"))
    return no, no, no, no
```
> The `*-built` State checks (current children) make this idempotent: a tab is filled once, re-switching is a no-op (content persists in DOM since dmc.Tabs keeps inactive panels mounted). Power tab is always full (built eagerly) — not handled here.

### Step 4: Run tests + import sanity (DuplicateCallback check)
```
pytest tests/test_virt_lazy_mount.py tests/test_virt_combined_callbacks.py tests/test_virt_loading_wrappers.py -v
python -c "import app"   # allow_duplicate must let this register cleanly
```
Expected: PASS; `import app` clean.

### Step 5: Commit
```bash
git add app.py src/pages/dc_view.py tests/test_virt_lazy_mount.py
git commit -m "perf(dc-view): lazy-mount non-default Virt sub-tab heavy content (P5)"
```

---

## Task 3 (P8): Host-row endpoint'lerini full-fetch-cached + Python filtreleme yap

**Mekanizma:** `get_classic_host_rows`/`get_hyperconv_host_rows` cluster listesini cache key'e gömüyor → her subset toggle = backend round-trip. Host satırları ham per-host veri ve her satır `cluster` alanı taşıyor (doğrulandı: `dc_service.py:1393`); her host'un capacity/usage/alloc'u kendine ait. Çözüm: tüm DC host listesini bir kez çek (clusters'sız cache key), seçili cluster'lara göre Python'da filtrele → subset toggle = cache hit.

**Files:**
- Modify: `src/services/api_client.py` — `get_classic_host_rows` (776-788), `get_hyperconv_host_rows` (791-803)
- Test: `tests/test_api_client_host_rows_slice.py` (Create)

### Step 1: Write the failing test
```python
# tests/test_api_client_host_rows_slice.py
"""P8: host rows fetched once (all clusters), then sliced in-process per subset."""
from unittest.mock import patch
from src.services import api_client as api
from src.services import cache_service


def test_classic_host_rows_fetched_once_for_multiple_subsets():
    cache_service.clear()
    full = {"hosts": [
        {"host": "h1", "cluster": "DC13-KM1"},
        {"host": "h2", "cluster": "DC13-KM2"},
        {"host": "h3", "cluster": "DC13-KM1"},
    ], "host_count": 3}
    calls = {"n": 0}

    def fake_get_json(client, path, params=None):
        calls["n"] += 1
        # backend called with NO clusters param (full DC fetch)
        assert "clusters" not in (params or {}), "P8 must fetch all hosts, not a cluster subset"
        return full

    with patch.object(api, "_get_json", side_effect=fake_get_json):
        sub1 = api.get_classic_host_rows("DC13", ["DC13-KM1"], None)
        sub2 = api.get_classic_host_rows("DC13", ["DC13-KM2"], None)
        allh = api.get_classic_host_rows("DC13", None, None)

    assert calls["n"] == 1, "backend should be hit once; subsets served from the cached full list"
    assert {h["host"] for h in sub1["hosts"]} == {"h1", "h3"} and sub1["host_count"] == 2
    assert {h["host"] for h in sub2["hosts"]} == {"h2"} and sub2["host_count"] == 1
    assert allh["host_count"] == 3
```

### Step 2: Run, confirm FAIL
`pytest tests/test_api_client_host_rows_slice.py -v` → FAIL (currently embeds clusters in params + cache key; backend hit per subset).

### Step 3: Apply the fix — `get_classic_host_rows` (api_client.py:776):
```python
def get_classic_host_rows(
    dc_code: str, selected_clusters: Optional[list[str]], tr: Optional[dict]
) -> dict:
    """Per-host compute rows for Classic (KM). Full DC list fetched once (cached);
    cluster subset is sliced in-process so toggling clusters is a cache hit."""
    enc = quote(dc_code, safe="")
    params = _build_time_params(tr)  # NO clusters param -> one cache entry per dc/time
    ck = f"api:classic_hosts_all:{enc}:{json.dumps(sorted(params.items()), separators=(',', ':'))}"

    def fetch() -> dict:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/compute/classic/hosts", params=params)
        return data if isinstance(data, dict) else {"hosts": [], "host_count": 0}

    full = _api_cache_get_with_stale(ck, fetch, {"hosts": [], "host_count": 0})
    return _slice_host_rows(full, selected_clusters)
```
Same for `get_hyperconv_host_rows` (cache key `api:hyperconv_hosts_all:`, endpoint `/compute/hyperconverged/hosts`).

Add the shared slicer helper (near the host-row functions):
```python
def _slice_host_rows(full: dict, selected_clusters: Optional[list[str]]) -> dict:
    """Return host rows filtered to selected_clusters (None/empty => all). Each row is self-contained."""
    hosts = (full or {}).get("hosts") or []
    if not selected_clusters:
        return {"hosts": list(hosts), "host_count": len(hosts)}
    wanted = set(selected_clusters)
    filtered = [h for h in hosts if h.get("cluster") in wanted]
    return {"hosts": filtered, "host_count": len(filtered)}
```

> ⚠️ Backend full fetch still cluster-filters in SQL when given clusters; we now pass NO clusters so it returns all KM/Nutanix hosts for the DC. Per-host capacity/usage/alloc are independent of the selection (confirmed: `CLASSIC_HOST_ROWS` is per-host; VM allocation is grouped by host), so slicing is correct. Do NOT apply this pattern to `get_*_metrics_filtered` (those are server-side aggregates).

### Step 4: Run tests (new + existing api_client tests for no regression)
```
pytest tests/test_api_client_host_rows_slice.py tests/test_api_client_sellable_cache.py tests/test_api_client_timeouts.py tests/test_cluster_filter.py -v
python -c "import src.services.api_client; print('import OK')"
```
Expected: PASS.

### Step 5: Commit
```bash
git add src/services/api_client.py tests/test_api_client_host_rows_slice.py
git commit -m "perf(api-client): fetch all host rows once and slice clusters in-process (P8)"
```

---

## Task 4: Sprint kapanışı

- [ ] **Full Sprint 2 test run:** `pytest tests/test_virt_combined_callbacks.py tests/test_virt_lazy_mount.py tests/test_api_client_host_rows_slice.py tests/test_virt_loading_wrappers.py -v` → all PASS.
- [ ] **`python -c "import app"`** → no DuplicateCallback / import error (the critical integration check for P3+P5).
- [ ] **Push + PR** (after user review): `git push origin feature/frontend-perf-sprint2` → `gh pr create --base main`.

---

## Self-Review

**Spec coverage:** P3 → Task 1; P5 → Task 2; P8 → Task 3. B3 dropped per scope decision. ✓
**Placeholder scan:** All code steps contain real code. ✓
**Type/name consistency:** `update_classic_virt_block`/`update_hyperconv_virt_block` (P3) referenced consistently; `populate_virt_nested_tab` + `allow_duplicate` outputs match P3's output ids; `_slice_host_rows` defined and used in both host-row fns; `content_mode` param consistent across `_build_virt_subtab_stack` + `_virt_nested_tab_panel`. ✓
**Risk notes:** `allow_duplicate=True` required on P5 callback (shared outputs with P3). `suppress_callback_exceptions=True` confirmed (lazy components safe). Idempotent populate via `*-built` State. ✓

## Execution Handoff
Plan: `task/frontend-perf-optimization/sprint-2-plan.md`. Subagent-driven, two-stage review (spec + quality) per task — higher rigor than Sprint 1 given the callback-graph risk. P3 → P5 → P8 order is mandatory (shared-output coordination).
