# CRM Inventory Product Matching — Design

**Date:** 2026-07-16  
**Status:** Approved to implement (follows [[CRM-Inventory-Infra-Matching]] / ADR-0024)  
**Branch:** `feature/crm-inventory-product-matching`

## Goal

Surface Excel-driven CRM product ↔ infrastructure matching on `/crm/inventory-overview` so operators see, per sold SKU: Source, Matching rule, match status, CRM sold qty, and (where available) linked inventory panel totals.

## Non-goals (this PR)

- Per-customer Veeam/Zerto license reconciliation (customer-page phase).
- Live recompute of all infra tables (use inventory panel totals when `panel_key` is mapped).
- CRM collector `blt_usagedatasource` sync.

## Approach

1. **Registry** (`shared/matching/product_matching_registry.yaml`): productnumber → usage_source, matching_rule, match_status (`capacity` | `documented` | `sold_noted_customer_phase` | `crm_only`), optional `panel_key`, `infra_tables`.
2. **Service** (`ProductMatchingService`): join registry + global CRM sold (`statecode=0` Active; productid→productnumber) + optional panel row from `InventoryOverviewService`.
3. **API:** `GET /api/v1/crm/inventory-matching` (+ include `product_matching` summary/rows on inventory-overview payload for one-fetch UI).
4. **UI:** new accordion **Product Matching** on CRM Inventory (filter: all / capacity / documented / customer_phase).
5. **Mock + unit tests.**

## Recommendation

Ship registry + sold join + panel enrich first; infra column-level live SQL stays in knowledge-base `scripts/matching/` until DQ issues (Nutanix used_storage, NetBox name dupes) are resolved.
