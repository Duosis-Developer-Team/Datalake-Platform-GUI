# Customer View Modernization (Design Spec)

**Status:** Implemented (pilot)  
**Pilot screen:** `/customer-view?customer=…`  
**Visual wireframe:** Cursor canvas `customer-view-modernization.canvas.tsx`

Related: [LOADING_UX_DESIGN.md](../LOADING_UX_DESIGN.md) | [[02-Module-Platform-GUI]] | ADR-0010, ADR-0016

---

## Goals

| Goal | Implementation |
|------|----------------|
| Reduce clutter | Hide zero/empty metrics and sections dynamically |
| Clear user flow | Summary = decisions; Billing = commercial; Virt = drill-down |
| No duplicate data | CRM detail moved out of Summary into Billing |
| Reusable patterns | `src/utils/visibility.py`, shared status badges |

---

## Tab responsibilities

### Summary (decision)

- **Shows:** Single unified panel (`build_customer_summary_panel`) — customer header (name, overage badge, active order value), compact **Customer signals** strip (billable: instances, backup, S3, CRM; satisfaction: SLA compliance %, lowest service availability %, avg ticket resolution, open tickets, VM outages), and **Issues requiring attention** list (resource overusage table, open tickets, SLA breaches, services &lt; 98% availability via product_catalog + AuraNotify categories).
- **Hides:** Separate intro card above tabs, large metric cards, CRM KV panel, active/invoiced order tables, virtualization gauge panels.
- **Data:** `compliance_payload`, `itsm_summary`, `service_breakdown`, `aura.get_dc_services_availability` for SLA category matching.

### Billing (commercial)

- **Shows:** CRM realized KPIs (non-zero), CRM summary KV (non-empty rows), active orders, invoiced orders, sold-vs-used (non-virt/backup), compute/backup/S3 billing lines (non-zero platforms only).
- **Hides:** Zero revenue KPIs, empty service categories, bare-metal/power rows with no instances.

### Virtualization

- **Shows:** Platform sub-tabs only when platform has VMs/LPARs or resources; VM tables and compute metrics.
- **Hides:** Pure Nutanix / Power sub-tabs when count is zero; sold-vs-used gauge/compliance stack (moved to Summary overusage list).

### Backup

- **Shows:** Vendor tabs (Veeam / Zerto / NetBackup) only when vendor has meaningful totals or asset lists.
- **Hides:** Vendor tabs with all-zero metrics.

### Availability

- **Shows:** Service outage and VM outage sections only when records exist in period.
- **Hides:** Empty tables and “No data” placeholder rows.

### ITSM

- **Shows:** KPI cards with meaningful values; distribution charts when data exists.
- **Hides:** Zero-count KPI tiles (e.g. SLA breach = 0).

### Physical Inventory / S3

- Tab visible only when devices or vaults exist (`has_phys_inv`, `has_s3`).

---

## Visibility rules

Implemented in `src/utils/visibility.py`:

- `is_meaningful_value()` — `None`, `-`, `N/A`, empty strings, empty collections, numeric zero (configurable).
- `visible_kv_rows()` — label/value pairs for KV panels.
- `visible_metrics()` — metric dicts with `value` key.
- `filter_compliance_rows_for_display()` — drops inert compliance rows.
- `filter_efficiency_rows_for_display()` — drops `no_sales` / `no_usage` without quantities.
- `filter_overusage_rows()` — over/unsold_usage rows for Summary problems table.
- `compute_sla_compliance_pct()` — ITSM breach rate for satisfaction strip.
- `asset_has_usage()` — platform-level non-zero check.

---

## Summary panel (unified)

- `src/components/customer_summary_panel.py` — replaces separate intro card + large signals grid.
- Overusage detail: `build_compliance_issue_table()` in `sold_vs_used_panel.py` (no gauges).
- CRM KPI strip remains in Billing only.

---

## Progress

| Step | Status |
|------|--------|
| Wireframe / canvas | Done |
| Visibility primitives + tests | Done |
| Summary refactor | Done |
| Billing refactor | Done |
| Panel refactors (CRM, compliance, sold-vs-used) | Done |
| Conditional tabs (phys inv, backup vendors, virt platforms) | Done |
| Unified Summary panel + virt gauge removal | Done |
| Unit tests | Done |
