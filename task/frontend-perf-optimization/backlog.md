# Frontend Performans Optimizasyonu — Backlog

**Branch:** `feature/frontend-perf-optimizations`
**Kaynak:** 36-agent eş güdümlü araştırma (7 boyut, 23/28 bulgu adversarial doğrulandı), 2026-06-14
**Problem:** Dash frontend ağır donuyor ("Sayfa Yanıt Vermiyor"). En çok şikayet: DC13 Virt (Sanallaştırma) sekmesi açılışı + cluster ekle/çıkar (zerto, vsde) filtreleme.

> **Çalışma sırası kararı:** Önce A→B (quick win + yapısal + async/cache), **render maliyeti (bölüm D) en sona** — diğerleri bittikten sonra konuşulacak.

---

## 1. Kök Nedenler (neden donuyor — 5 mekanizma)

| # | Kök neden | Kanıt |
|---|-----------|-------|
| RC-1 | Sadece 4 senkron işçi (`gunicorn --workers 1 --threads 4 --timeout 300`), hiç background callback yok → bloklayan callback tüm pod'u dondurur; takılan upstream thread'i 5 dk kilitler | `Dockerfile:33` |
| RC-2 | Tek cluster değişimi 4 ayrı callback'i aynı anda tetikliyor (+ hyperconv 4 daha); debounce yok; tab her mount'ta `value=list(clusters)` ile sahte tetikliyor | `app.py:801/843/914/978`, `dc_view.py:1744` |
| RC-3 | Cache key'i tam cluster CSV'sini gömüyor → her seçim garanti cache miss → 30s bloklayan fetch; "stale-while-revalidate" docstring'i yanlış (arka plan revalidation yok) | `api_client.py:740/769/1925, 368-385` |
| RC-4 | Sellable cold path'i gereksiz çift round-trip (`get_sellable_snapshot_meta`) + thread-safe olmayan paylaşımlı `_client_crm` → 8 CRM çağrısı/cluster, havuz çekişmesi | `api_client.py:172, 307-319` |
| RC-5 | Render path'inde eager inşa: 3 alt-tab'ın hepsi + ~18 gauge tek seferde; `build_dc_lazy_tab_panel` tüm sayfa ağacını kurup atıyor; bazı I/O serial | `dc_view.py:5075-5077, 4542-4585, 4768-4772, 4818-4822` |

---

## A. Quick Win'ler (küçük efor, düşük risk — önce bunlar)

- [ ] **P1 — Cluster MultiSelect'lere `debounce` + "gerçek değişim" guard.**
  N tıklık düzenlemeyi 1'e indirir; mount'taki sahte 4'lü fan-out'u durdurur. → cluster filtre + Virt açılış donması.
  *Yer:* `dc_view.py:1744` (`_cluster_header`), tüketiciler `app.py:801/843/914/978` (+hyperconv). **Efor: Küçük**

- [ ] **P2a — Sellable çift round-trip'i kaldır.**
  `get_sellable_snapshot_meta`'yı sadece payload boşsa (`_sellable_panels_have_data(out)` False) çağır. CRM çağrısı 8→4.
  *Yer:* `api_client.py:307-319`. **Efor: Küçük**

- [ ] **P2b — `_client_crm`'i thread-local yap** (`_get_client_dc` desenini izle), ~26 call-site + health probe.
  Bağlantı havuzu çekişmesini bitirir; paralel fetch gerçek olur.
  *Yer:* `api_client.py:172, 2191`. **Efor: Küçük-orta (mekanik, geniş)**

- [ ] **P4a — Virt çıktı Div'lerini `dcc.Loading`'e sar** → donma yerine çark.
  *Yer:* `dc_view.py` Virt layout (4 output Div). **Efor: Küçük**

- [ ] **P4b — Interactive httpx timeout'larını sıkılaştır** (30s → connect 2-3s / read 5-8s); 30s yalnız admin/warm path'te kalsın. Timeout'ta last-good/empty dön.
  *Yer:* `api_client.py:135/145/155/165/173` (interactive), `2185` (warm). **Efor: Küçük** · ⚠️ read timeout'u p95/p99'dan seç, yoksa yavaş-ama-geçerli DC13 yanıtları boşalır.

- [ ] **P6 — gunicorn `--threads 4 → 8-12`** (workers=1 kalsın; çoğullarsa in-process cache parçalanır).
  *Yer:* `Dockerfile:33`. **Efor: Küçük** · Tek başına yetmez, P3 ile eşleştir.

- [ ] **P7 — SAN + backup serial bloklarını `parallel_execute`'a al.** ~3× cold wall-clock (Virt'i etkilemez; Storage/Backup tab).
  *Yer:* `dc_view.py:4768-4772, 4818-4822`. **Efor: Küçük**

---

## B. Yapısal İşler (orta-büyük efor — quick win'lerden sonra)

- [ ] **P3 — 4'lü fan-out'u tek multi-Output callback'e birleştir** (selector başına); fetch'ler tek `parallel_execute` batch; `sellable-virt-total-card`'ı paylaşımlı `dcc.Store`'dan besle.
  1 selection = 4 thread yerine 1; çift fetch'leri kaldırır.
  *Yer:* `app.py:800-992`. **Efor: Orta**
  ⚠️ `DuplicateCallback` riski (commit 6020480); `hosts-panel-classic` yoksa `no_update`; `app-time-range` Input'unu koru; hosts callback'lerinde `prevent_initial_call=True` eksik (`app.py:840/857`) — birleşmede uyumla.

- [ ] **P5 — Nested Virt alt-tab'larını lazy-mount et.**
  Sadece `default_virt_tab` gövdesini kur; diğer ikisi için stabil-id boş shell; zaten var olan **ölü** `build_virt_nested_subtab_panel`'i yeni bir `Input("virt-nested-tabs","value")` callback'ine bağla. ~12/18 gauge + 2/3 sellable çağrısını açılıştan kaldırır.
  *Yer:* `dc_view.py:5075-5077, 1830, 4954`. **Efor: Orta**
  ⚠️ MATCH callback'ler (`compute-gauge` `dc_view.py:5439`) ve pattern callback'ler mount'a kadar yokluğa tolere etmeli; pattern-rebuild sahte-tetik gotcha'sına dikkat (MEMORY.md).

- [ ] **B3 — `build_dc_lazy_tab_panel` düzelt:** tüm DC ağacını kurup atmak yerine sadece gereken alt-ağacı kur.
  *Yer:* `dc_view.py:4542-4585`. **Efor: Orta**

- [ ] **P8 — Host-row endpoint'lerinde in-process subset slicing.**
  Tam DC host listesini bir kez çek (dc/time key, cluster paramsız), callback'te `selected_clusters`'a göre filtrele → subset toggle = cache hit.
  *Yer:* `api_client.py:763/778`, hosts callback'leri `app.py:840/857`. **Efor: Orta**
  ⚠️ **KRİTİK: SADECE host-row endpoint'leri.** `get_classic_metrics_filtered`/`get_hyperconv_metrics_filtered` server-side SQL aggregate (30g avg/min/max, `db_service.py:744-746/814-816`) döner — bunları row mask'leyerek yeniden türetmek YANLIŞ sayı üretir (overview-vs-cards mismatch geri gelir).

---

## C. Async / Cache Altyapısı

- [ ] **C1 — Request coalescing (single-flight):** aynı cache-key'e eşzamanlı miss'ler tek upstream fetch paylaşsın. Global cache RLock'ı network'ten ÖNCE bırak (per-key event), yoksa tüm miss'leri serialize edip daha kötü stall yaparsın.
  *Yer:* `api_client.py` `_api_cache_get_with_stale` / `_api_cache_get_sellable_panels`. **Efor: Orta**

- [ ] **C2 — Gerçek stale-while-revalidate:** arka planda revalidation ekle (şu an yok; `stale` sadece var olan key'in kopyasını dönüyor).
  *Yer:* `api_client.py:368-385`. **Efor: Orta**

- [ ] **C3 — Background callbacks (CeleryManager + mevcut Redis):** iki ağır build callback'ini `background=True` + `running=`/`progress=` yap → worker anında serbest, progress UX.
  *Yer:* `expand_dc_view_on_tab` (`dc_view_callbacks.py:131`), `render_main_content` (`app.py:662`). **Efor: Büyük**
  ⚠️ `DiskcacheManager` değil **CeleryManager** (2 replika, `k8s/frontend/deployment.yaml`); `render_main_content` Flask `g.auth_user_id`/request context okuyor (`app.py:670-699`) → Celery worker'da yok, auth dispatch öncesi çözülmeli yoksa foreground kalmalı.

> **Async sıralaması:** Önce C1 + P4b + (P3 içindeki) `parallel_execute` (ucuz, Celery'siz), *sonra* C3 background callbacks (progress UX için).

---

## D. Render Maliyeti — **EN SONA** (diğerleri bitince konuşulacak)

- [ ] **D1 — Büyük un-virtualized `dash_table.DataTable`'ları virtualize et** (`sort_action`/`filter_action="native"` olanlar; pagination). **Efor: Küçük-orta**
- [ ] **D2 — Gizli Allocation grid'lerini kurma** (görünmeyeni inşa etme). **Efor: Küçük**
- [ ] **D3 — Sunucu-taraf figür üretimini mümkün olduğunca clientside'a taşı** (tekrarlanan aynı figür build'leri). **Efor: Orta**

> Not: ~18 Plotly gauge'ın CPU/GIL-bound render'ı async ile HIZLANMAZ — çözüm "daha az iş yap" (D1/D2 + P5 lazy-mount). Bu yüzden render işi yapısal lazy-mount'tan (P5) sonra anlamlı.

---

## E. Backend (opsiyonel — latency'yi kökten azaltır)

- [ ] **E1 — `(dc, cluster, timestamp)` index** ekle `*_FILTERED` / `*_AVG30_FILTERED` tablolarına → her cold miss'in ödediği aggregation latency'sini keser. **Efor: Küçük (DB) + koordinasyon**

---

## G. Deferred — Sprint 3 SONRASI (bizden bağımsız mevcut borç)

> Bu maddeler bizim perf çalışmamızdan **bağımsız**; `origin/main`'de de kırıklar. Sprint 3 bitince ayrı, küçük bir temizlik olarak ele alınacak (perf PR'larına karıştırılmadı).

- [ ] **G1 — Pre-existing test borcu düzelt.** `tests/test_dc_view_capacity_table.py` + `tests/test_network_eager_load.py` `origin/main`'de patlıyor: stale `FakeApi` test double'ında `get_sellable_summary_light` metodu eksik + network eager assertion'ları eskimiş. Çözüm: `FakeApi`'ye eksik metodu ekle, network eager assertion'larını güncel davranışa hizala. **Efor: Küçük.** (Collection error'lar — `psycopg2`/`openpyxl` ModuleNotFound — sadece local venv eksiği, repo/CI sorunu DEĞİL; aksiyon gerekmez.)

---

## F. SAKIN YAPMA (tuzaklar)

- ❌ Aggregate metrik endpoint'lerini client-side slice etme (avg/min/max SQL'de hesaplanıyor → yanlış sayı, overview-vs-cards mismatch).
- ❌ Redis olmadan `--workers` > 1 (in-process `cache_service._cache` parçalanır, cold load çoğalır).
- ❌ Zaten cache'li by-panel için `dcc.Store` dedupe'tan büyük kazanç bekleme (gerçek maliyet cold per-combination miss → P3/P8/prewarm çözer).

---

## Önerilen Uygulama Sırası

1. **Sprint 1 (quick win):** P1 → P4a/P4b → P2a/P2b → P6 → P7
2. **Sprint 2 (yapısal):** P3 → P5 → B3 → P8
3. **Sprint 3 (async/cache):** C1 → C2 → C3
4. **Sprint 4 (render — en son):** D1 → D2 → D3 (+ E1 backend koordinasyonu)

**Anahtar dosyalar:** `Dockerfile:33` · `app.py:800-992, 662` · `src/pages/dc_view.py:1744, 5075-5077, 1830, 4542-4585, 4768-4772, 4818-4822` · `src/services/api_client.py:172, 307-319, 368-385, 740/769/1925, 135` · `src/utils/virt_sellable_aggregate.py:71` · `src/utils/api_parallel.py` · `src/pages/dc_view_callbacks.py:131`
