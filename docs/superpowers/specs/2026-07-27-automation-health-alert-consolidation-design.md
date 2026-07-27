# Automation Health: alert consolidation

**Date:** 2026-07-27
**Status:** Approved (direction), pending implementation plan
**Related:** [[ADR-0027-data-freshness-health-framework]], `services/hmdl-api/app/services/freshness_registry.py`, `src/pages/settings/integrations/hmdl_automation_health.py`

## Problem

The Automation Health page shows **40 data alerts**. Customers can reach this page
(`page:settings_hmdl_automation_health` is granted to their role), and what they see is a
list of 40 raw database table names in `dead` state. A customer reading
`Raw Vmware Datastore Metrics Agg — dead, 11 days` has no way to know whether that
affects them, and the sheer count reads as "this platform is broken".

The count is wrong in two independent ways.

### The page monitors tables nothing reads

ADR-0027 built the registry by **auto-discovery**: every `public` table carrying a
recognised timestamp column is monitored, minus a small `_EXCLUDE_EXACT` seed for legacy
`loki_*`. Measured against the running platform on 2026-07-27:

| | count |
|---|---|
| Tables monitored | 159 |
| Referenced anywhere in `services/`, `src/`, `shared/` | **65** |
| Referenced by nothing | **94** |

94 monitored tables feed no query, no screen, no export. Their freshness is not a platform
health signal — it is the freshness of data the platform abandoned. Several are explicitly
superseded and the codebase says so:

- `zabbix_network_interface_metrics` (dead 77 days) — `datacenter-api` reads
  `raw_zabbix_network_interface_metrics_v`, which is current.
- `raw_vmware_vm_config` / `raw_vmware_vm_runtime` (dead 137 days) — `licensed_os.py:3-6`
  records that VMware collection stopped 2026-03-12 and the source moved to
  `discovery_netbox_virtualization_vm`. These names now survive only in that comment.

Of the 65 tables the platform actually reads, **55 are fresh, 9 read as dead, 1 unknown**.
Two of the 9 are the comment-only VMware pair above, so the curated monitored set is
**63 tables** and the true dead figure is **7**. The unmonitored bucket therefore holds
**96**.

**40 alerts → 7.**

### The page counts tables, not incidents

The remaining 7 are not 7 problems. Grouped by the moment they stopped:

| Stopped | Tables | What actually happened |
|---|---|---|
| 11 days ago | `raw_vmware_datastore_metrics_agg`, `raw_vmware_datastore_host_mount` | The VMware datastore flow died 2026-07-16 (the incident behind Overview → Storage 0%) |
| 62–63 days ago | `ibm_lpar_performance_metrics`, `nutanix_host_performance_metrics`, `nutanix_vm_performance_metrics`, `vmware_host_performance_metrics`, `vmware_vm_performance_metrics` | One `*_performance_metrics` rollup stopped across all three hypervisor families |

**7 alerts → 2 incidents.**

The same shape holds in the noise: all 10 `raw_panduit_*` tables stopped within the same
minute 63 days ago. That is one dead PDU collector rendered as ten alerts.

## Decision

Two changes, independent and separately shippable.

### Change 1 — monitor only what the platform reads

Freshness monitoring becomes **opt-in by usage** rather than opt-out by exclusion list.

A table is monitored when the platform reads it. The registry carries that decision
explicitly as curated data (`MONITORED` set seeded from the 2026-07-27 measurement), not as
a runtime scan. Runtime grep was rejected: `hmdl-api` cannot see the other services' source,
and the measurement itself showed grep's two failure modes — `zabbix_network_interface_metrics`
matched inside `raw_zabbix_network_interface_metrics_v`, and the dead VMware pair matched a
comment. A curated set is auditable and cannot silently change meaning.

Unmonitored tables are **not deleted from the response.** They move to a separate
`unmonitored` bucket, excluded from `data_counts.alert` and from the badge, and rendered in
a collapsed section on the page. Nothing is hidden; it stops raising alarms.

**Risk this accepts:** a table that becomes load-bearing later will not alert until someone
adds it to `MONITORED`. Mitigation is a review rule — a new query against a new table adds
that table to the set in the same commit — and the collapsed section keeps the signal
reachable. This is the same maintenance contract `_EXCLUDE_EXACT` already carries, inverted.

### Change 2 — group alerts by flow, label them in user language

Each monitored table declares the **collection flow** that writes it. Alerts roll up per
flow, so one dead collector produces one alert regardless of how many tables it feeds.

The flow carries a human label describing the *data*, not the table:

| Flow | Label (customer-facing) |
|---|---|
| `vmware_datastore` | Depolama kullanım verisi |
| `hypervisor_performance` | Sunucu performans verisi |

The page renders one row per alerting flow:

```
⚠  Depolama kullanım verisi 11 gündür güncellenmiyor
⚠  Sunucu performans verisi 62 gündür güncellenmiyor
✓  Envanter, ağ, yedekleme, CRM güncel
```

Per-table detail moves behind a disclosure on each row, so internal users keep the table
names and ages they debug with. The flow's age is the age of its **oldest** dead table.

Flow assignment defaults to the existing family when a table declares none, so an
unclassified table degrades to today's per-family grouping rather than disappearing.

## Non-goals

- **Fixing the dead collectors.** The datastore flow (11 days) and the performance rollup
  (62 days) are operational failures needing collector work. This spec makes them legible;
  it does not restart them.
- **Changing who can see the page.** Whether `page:settings_hmdl_automation_health` should
  be granted to customer roles is a separate RBAC decision. This spec assumes it stays
  granted and makes the page safe to show.
- **Touching the automation (AWX log) side.** The 4 `AUTOMATION_SPECS` rows are already
  incident-shaped; only the data-family side is being consolidated.

## Components

| Unit | Responsibility |
|---|---|
| `freshness_registry.py` | Owns `MONITORED` and `FLOWS` (flow key → label + member tables). Pure data + lookup, no DB. |
| `freshness.py` | Splits discovered specs into monitored / unmonitored; rolls monitored results up per flow. |
| `automation_health.py` | Emits `data_flows` alongside the existing `data_families`; `data_counts.alert` counts flows, not tables. |
| `hmdl_automation_health.py` (GUI) | Renders one row per alerting flow, per-table detail behind a disclosure, unmonitored in a collapsed section. |
| `hmdl_sync_ui.py` | `combined_alert_count` unchanged in shape — it now sums a flow-based count. |

## Data flow

```
discover_specs (159 tables)
        │
        ├─ MONITORED? ──no──►  unmonitored[]   (no alert, collapsed in UI)
        │
       yes (63)
        │
   compute_freshness  ──►  per-table status
        │
   group by FLOWS  ──►  data_flows[]  (alert = worst member; age = oldest dead member)
        │
   data_counts.alert = count(flows in alert)      2, not 40
```

## Error handling

- A table in `MONITORED` that discovery cannot find (renamed, dropped) is reported by name
  in `data_missing` rather than vanishing — a stale curation entry must be visible, or the
  set rots silently. It is reported, not counted: a name that resolves to no table is a
  curation defect, not a data outage, and must not inflate the alert count the change set
  out to shrink.
- A flow whose members are all `unknown` reports `unknown`, not `ok`. Absence of data is not
  health.
- The GUI keeps its existing "computing" state; flow rollup happens server-side in the
  existing snapshot refresher, so no new latency on the request path.

## Testing

- Registry: every `FLOWS` member is in `MONITORED`; no table belongs to two flows; every
  `MONITORED` entry resolves to a family.
- Rollup: N dead tables in one flow yield exactly 1 alert; flow age equals the oldest dead
  member; a fresh member does not clear a dead sibling.
- Counts: with the 2026-07-27 fixture, `data_counts.alert` is 2 and `unmonitored` holds 96.
- Fallback: a table with no declared flow rolls up under its family and still alerts.
- GUI: an alerting flow renders one row; its table detail is present but not expanded;
  the unmonitored section renders collapsed.

## Expected outcome

| | before | after |
|---|---|---|
| Alerts shown | 40 | 2 |
| Rows a customer reads | 40 table names | 2 sentences + 1 all-clear |
| Information lost | — | none (unmonitored collapsed, per-table detail behind disclosure) |
