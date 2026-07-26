# VM Dedup + DC→Cluster→Host→VM Topology — Design Spec

**Date:** 2026-07-26
**Follows:** TASK-81 (Licensed OS) NetBox source switch. Extends to TASK-69 area (Datalake Coverage).

## Problem

`discovery_netbox_virtualization_vm` has **42,707 rows but only ~17,418 distinct VMs**
(`custom_fields_config_instance_uuid`) — a ~2.45× duplication (repeated NetBox records per VM +
125 vCLS system VMs). So the Licensed OS tally (42,707) is inflated. Separately, users need to see
**which VM runs on which host, which host in which cluster, in which DC** — a DC→Cluster→Host→VM
topology — on both the **Licensed OS** page and the **Datalake Coverage** page.

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

### 2. Licensed OS summary — dedup

`VM_OS_NETBOX` / `VM_OS_NETBOX_FOR_CUSTOMER` wrap the base select in
`SELECT DISTINCT ON (vm_dedup_key) ... ORDER BY vm_dedup_key, (status_value='poweredOn') DESC`
so each VM is classified once. Result drops from 42,707 → ~17,418. `_tally_os_rows` unchanged.

### 3. Shared topology module — `shared/topology/vm_topology.py` (pure + SQL)

- `VM_TOPOLOGY_SQL` → deduped rows `(dc, cluster, host, vm_name, instance_uuid, guest_os,
  power_state)` (DISTINCT ON dedup_key; `site_name`→dc, `cluster_name`→cluster, `device_name`→host).
  Empty dc/cluster/host coalesced to a literal `"(bilinmeyen)"` so nothing is silently dropped.
- `build_tree(rows, *, with_os=False) -> dict`: nests DC→cluster→host→VM. Each node carries
  `counts` = `{clusters?, hosts?, vms}` and, when `with_os`, an `os` tally
  `{rhel,suse,windows,free,unknown}` (via `shared.licensing.os_classifier.classify`). Leaf VM nodes:
  `{name, os_family, power_state}`. Pure/unit-testable (no DB).
- `is_system_vm(name)` → True for `vCLS*` (shown but badge-able).

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

- **Licensed OS** (`src/pages/licensed_os.py`): deduped family KPIs (now ~17.4k, not 42.7k) + a
  "Topoloji (DC → Cluster → Host → VM)" section rendering `build_topology_tree(..., with_os=True)`.
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

- dedup SQL: `DISTINCT ON` on the dedup key; VM_OS_NETBOX reads NetBox guest_os (not raw_vmware).
- `build_tree`: nesting DC→cluster→host→VM; per-node counts; OS tally when with_os; unknown-node
  coalescing; dedup already applied upstream.
- `is_system_vm`.
- endpoint: os=true carries os tally, os=false doesn't; totals.
- `build_topology_tree`: renders DC/cluster/host/VM labels + counts; OS mini-bar when with_os.
- Licensed OS page: KPIs use deduped total; topology section present.
- Coverage page: topology section present.

## Risks

- **Dedup key gaps** (~11% lack instanceUUID) → name+cluster fallback; a renamed/moved VM could
  split, minor. Total lands ~17.4k (matches dashboard ~17.1k).
- **Tree size:** ~17k VMs across DCs — Accordion lazy-renders; VM leaf lists can be long per host
  (cap/scroll per host node). Cached endpoint keeps it off the request path's heavy work.
- **Two services reading one table:** avoided by a single datacenter-api endpoint both pages call.
