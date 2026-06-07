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

- **Shows:** Customer signals (up to 4 meaningful KPIs), resource compliance issues (filtered rows), overage footer when applicable.
- **Hides:** CRM KV panel, active/invoiced order tables, compute resource grid, backup capacity cards, zero platform counts.

### Billing (commercial)

- **Shows:** CRM realized KPIs (non-zero), CRM summary KV (non-empty rows), active orders, invoiced orders, sold-vs-used (non-virt/backup), compute/backup/S3 billing lines (non-zero platforms only).
- **Hides:** Zero revenue KPIs, empty service categories, bare-metal/power rows with no instances.

### Virtualization

- **Shows:** Platform sub-tabs only when platform has VMs/LPARs or resources; compliance stack for mapped categories with usage/entitlement; VM tables.
- **Hides:** Pure Nutanix / Power sub-tabs when count is zero; gauge cards for `no_sales` / `no_usage` with no quantities.

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
- `asset_has_usage()` — platform-level non-zero check.

---

## Header / context card

- Single `build_crm_context_card()` replaces dual intro strip.
- Customer name, overage badge, active order value, optional overage loss line.
- CRM KPI strip removed from header (lives in Billing).

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
| Unit tests | Done |
