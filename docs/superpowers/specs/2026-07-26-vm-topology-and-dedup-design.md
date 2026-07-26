# VM Dedup + DC→Cluster→Host→VM Topology — Design Spec

**Date:** 2026-07-26
**Follows:** TASK-81 (Licensed OS) NetBox source switch. Extends to TASK-69 area (Datalake Coverage).

## Problem

`discovery_netbox_virtualization_vm` has **42,707 rows** but far fewer real VMs — a ~2.1× duplication
(repeated NetBox records per VM). After dedup by VM identity: **~20,130 unique VMs**
(17,133 poweredOn + 2,997 poweredOff; 15 vCLS system VMs). The poweredOn count (17,133) matches the
platform-metrics dashboard (~17,091) — confirming the dedup. So the Licensed OS tally (42,707) is
~2× inflated. Separately, users need to see **which VM runs on which host, which host in which
cluster, in which DC** — a DC→Cluster→Host→VM topology — on both the **Licensed OS** page and the
**Datalake Coverage** page.

Two data-quality realities the design must handle explicitly (not hide):
- **2,522 VMs have no DC** (`site_name` empty) → unmappable into the tree → must surface as an
  "unmapped" bucket, not be dropped.
- **poweredOff** (~3k) and **vCLS system** (15) VMs must be distinguishable, since licensing usually
  cares about running, non-system guests.

The full hierarchy already lives in that one table:
- **DC/Site** = `site_name` · **Cluster** = `cluster_name` · **Host** = `device_name` (ESXi host)
- **VM** = `name` / identity `custom_fields_config_instance_uuid` · **OS** = `custom_fields_guest_os`

## Goals / Non-goals

- **Goal:** (1) dedup the Licensed OS counts by VM identity; (2) an expandable DC→Cluster→Host→VM
  drill-down tree on the Licensed OS page (with per-node OS breakdown) and on the Datalake Coverage
  page (with per-node VM counts).
- **Non-goal:** changing coverage's collected-vs-expected logic; per-VM licensing billing; writing to
  NetBox. vCLS/system VMs are shown but flagged, not fixed here.

## Design

### 1. Dedup key (shared)

`vm_dedup_key = COALESCE(NULLIF(btrim(custom_fields_config_instance_uuid), ''),
lower(name) || '|' || coalesce(cluster_name,''))` — instanceUUID when present (~89%), else
name+cluster. One representative record per key via `DISTINCT ON (vm_dedup_key)`.

### 2. Licensed OS summary — dedup + power-state + system exclusion

`VM_OS_NETBOX` / `VM_OS_NETBOX_FOR_CUSTOMER` wrap the base select in
`SELECT DISTINCT ON (vm_dedup_key) name, guest_os, status_value ... ORDER BY vm_dedup_key,
(status_value='poweredOn') DESC` so each VM is classified once. Result drops from 42,707 → ~20,130.

**Curation decisions (this spec):**
- **vCLS/system VMs excluded** from the tally (`is_system_vm(name)`) — they are vSphere agents, not
  licensable guests (~15 deduped).
- **Power state:** `_tally_os_rows` returns families for **all** VMs AND a separate **poweredOn-only**
  tally (`families`, `families_running`, `total`, `total_running`). The page shows a
  **"Çalışan / Tümü" toggle** (default: Tümü) so licensing can be viewed either way.
- Rows now carry `status_value`; `_tally_os_rows((name, guest_id, guest_full_name, status_value))`.

### 3. Shared topology module — `shared/topology/vm_topology.py` (pure + SQL)

- `VM_TOPOLOGY_SQL` → deduped rows `(dc, cluster, host, vm_name, instance_uuid, guest_os,
  power_state)` (DISTINCT ON dedup_key; `site_name`→dc, `cluster_name`→cluster, `device_name`→host).
  **Unmapped coalescing:** empty `site_name`→`"(DC atanmamış)"`, empty cluster→`"(cluster yok)"`,
  empty host→`"(host yok)"` — so the ~2,522 DC-less VMs surface in an explicit unmapped bucket
  instead of being dropped.
- `build_tree(rows, *, with_os=False) -> dict`: nests DC→cluster→host→VM. Each node carries
  `counts` = `{clusters?, hosts?, vms, running}` and, when `with_os`, an `os` tally
  `{rhel,suse,windows,free,unknown}` (via `shared.licensing.os_classifier.classify`). Leaf VM nodes:
  `{name, os_family, power_state}`. vCLS/system VMs are excluded from the tree (kept out of counts,
  like the tally). Pure/unit-testable (no DB).
- `is_system_vm(name)` → True for `vCLS*`.

### 4. Endpoint (datacenter-api) — one source for both pages

`GET /api/v1/vm-topology?os=true|false` → `{"tree": {...}, "totals": {dcs,clusters,hosts,vms}}`.
`os=true` includes per-node OS tally (Licensed OS page); `os=false` counts only (Coverage page).
Cached (6h singleflight like the other datacenter-api reads). Both GUI pages call it — the
Coverage page (today hmdl-api-only) additionally calls datacenter-api for the tree.

### 5. Reusable drill-down tree component — `src/components/topology_tree.py`

`build_topology_tree(tree: dict, *, with_os=False) -> component` using nested `dmc.Accordion`:
DC (count badges + OS mini-bar if with_os) → expand → clusters → hosts → VM list. Lazy visual only
(data already loaded). Used by both pages.

### 6. Pages

- **Licensed OS** (`src/pages/licensed_os.py`): deduped family KPIs (now ~20k, not 42.7k) with a
  **"Çalışan / Tümü" toggle** (running-only vs all), vCLS excluded + a "Topoloji (DC → Cluster →
  Host → VM)" section rendering `build_topology_tree(..., with_os=True)`. The unmapped bucket
  ("(DC atanmamış)") is a visible top node.
- **Datalake Coverage** (`hmdl_coverage.py`): add a "Envanter Topolojisi" section rendering
  `build_topology_tree(..., with_os=False)` beside the existing coverage section.

## Data flow

```
discovery_netbox_virtualization_vm
  └─ shared.topology.vm_topology (DISTINCT ON dedup_key → rows → build_tree)
       └─ datacenter-api GET /vm-topology?os=… (cached)
            ├─ Licensed OS page  → build_topology_tree(with_os=True)  + deduped family KPIs
            └─ Coverage page     → build_topology_tree(with_os=False)
```

## Testing (TDD)

- dedup SQL: `DISTINCT ON` on the dedup key; VM_OS_NETBOX reads NetBox guest_os (not raw_vmware),
  carries status_value.
- `_tally_os_rows`: returns both `families` (all) and `families_running` (poweredOn-only); vCLS
  excluded from both.
- `is_system_vm`: True for vCLS, False for a normal VM.
- `build_tree`: nesting DC→cluster→host→VM; per-node counts incl. `running`; OS tally when with_os;
  **unmapped coalescing** ((DC atanmamış)/(cluster yok)/(host yok)); vCLS excluded.
- endpoint: os=true carries os tally, os=false doesn't; totals; unmapped bucket present.
- `build_topology_tree`: renders DC/cluster/host/VM labels + counts; OS mini-bar when with_os.
- Licensed OS page: KPIs use deduped total; running/all toggle; topology section present.
- Coverage page: topology section present.

## Risks

- **Dedup key gaps** (~11% lack instanceUUID) → name+cluster fallback; a renamed/moved VM could
  split, minor. Total lands ~17.4k (matches dashboard ~17.1k).
- **Tree size:** ~17k VMs across DCs — Accordion lazy-renders; VM leaf lists can be long per host
  (cap/scroll per host node). Cached endpoint keeps it off the request path's heavy work.
- **Two services reading one table:** avoided by a single datacenter-api endpoint both pages call.
