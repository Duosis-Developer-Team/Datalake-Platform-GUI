# OS Licence Inventory Group

**Date:** 2026-08-03  
**Status:** Approved for implementation  
**Related:** ADR-0030, TASK-81 licensed-OS detection, CRM Inventory Overview

## Problem

On `/crm/inventory-overview`, licensed OS panels appeared as four confusing accordion groups:

1. **Os** (`license_os`) — `license_windows_os` only  
2. **Os** (`mgmt_os`) — four OS *management* services (not licences)  
3. **Redhat** (`license_redhat`) — RHEL licence SKUs  
4. **Suse** (`license_other`) — SUSE licence SKU (family key is shared with other "other" licences)

Root cause: `_family_label()` humanizes the last segment of `gui_tab_binding` (`licensing.os` → "Os", `mgmt.os` → "Os"), and the three licence SKUs live in three different `gui_panel_definition.family` values.

Separately, the test environment WebUI DB was missing migrations 029–036 / 038–040 / 042–043, so DC Barındırma and OS panels had no infra binding and fell into CRM-only.

## Goal

1. One accordion group **OS Lisans** containing only Windows / Red Hat / SUSE **licence** panels.  
2. Replace capacity/sellable framing with a licence-gap frame: detected guests, CRM sold, gap qty, unit price, gap TL.  
3. Move OS management services (`mgmt_os_*`) to **CRM-only services** (unbind infra).  
4. Apply pending WebUI migrations on test, then promote code test → prod after approval.

## Design

### Presentation regroup (no DB family rewrite)

Mirror `_regroup_backup_families()`:

- Group key: `os_licence`  
- Label: `OS Lisans`  
- Members (by `panel_key`): `license_windows_os`, `license_redhat`, `license_suse`  
- `sellable_profile = "os_licence"`

DB `family` columns stay as seeded; only the inventory accordion regroups.

### Row fields (`_apply_os_licence_fields`)

| Field | Rule |
|-------|------|
| `licence_detected_qty` | `total` (telemetry guest count; `total == allocated` by construction) |
| `licence_gap_qty` | `max(total − crm_sold_qty, 0)` |
| `licence_gap_tl` | `gap × unit_price_tl` when `has_price` |
| sellable / free / unsold / used | cleared (`None`); `potential_tl = 0` |

Header badges: CRM Sold TL + "Eksik lisans N adet" + Lisanslanmalı TL. **No Sellable badge.**

### Management OS → CRM-only

Migration `045_unbind_mgmt_os_infra.sql` nulls infra columns for `mgmt_os_windows|linux|sap|unix` (same pattern as 038). Detection helpers in `licensed_os_inventory.py` remain for DC/Customer views; inventory overview no longer binds them.

### Deploy

1. Fast-forward `development` to `main`, feature branch off `development`.  
2. Deploy `development` to test (`10.134.52.250`): apply migrations + cache flush.  
3. Await approval.  
4. Merge `development` → `main`, promote to prod (`10.134.52.251`).

## Out of scope

- Changing DC View / Customer View licence reconciliation math  
- Rewriting `gui_panel_definition.family` for Red Hat / SUSE  
- Sellable headroom for licences (none by ADR-0030)
