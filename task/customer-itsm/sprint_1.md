# Feature Plan: Customer ITSM View — Sprint 1

**Branch:** `feature/customer-itsm-view`  
**Base:** `development`  
**Date:** 2026-04-24  
**Status:** ✅ Completed

---

## Objective

Add a new **ITSM** tab to the Customer View page, visualising ServiceCore incident and service request data per customer. No DDL changes to datalake tables.

## Scope

| Area | Status |
|---|---|
| SQL queries (customer_users + customer_tickets CTEs) | ✅ Done |
| ITSMService, schemas, FastAPI router | ✅ Done |
| main.py wiring | ✅ Done |
| api_client functions (summary / extremes / tickets) | ✅ Done |
| _tab_itsm builder (KPI grid + charts + accordions) | ✅ Done |
| build_customer_layout ITSM tab + panel | ✅ Done |
| Export sheets (ITSM_Summary / Extremes / All_Tickets) | ✅ Done |
| Unit tests (needle, service, tab, api_client) | ✅ Done |
| ADR-0009 | ✅ Done |
| Wiki update (02-Module-Platform-GUI.md) | ✅ Done |

## Key files created / modified

### New files

- `services/customer-api/app/utils/customer_needle.py`
- `services/customer-api/app/db/queries/itsm.py`
- `services/customer-api/app/services/itsm_service.py`
- `services/customer-api/app/routers/itsm.py`
- `services/customer-api/tests/test_customer_needle.py`
- `services/customer-api/tests/test_itsm_service.py`
- `tests/test_customer_view_itsm_tab.py`
- `tests/test_api_client_itsm.py`
- `task/customer-itsm/sprint_1.md` (this file)
- `../datalake-platform-knowledge-base/adrs/ADR-0009-servicecore-customer-resolution-email-domain-chain.md`

### Modified files

- `services/customer-api/app/models/schemas.py` — added ITSMSummary, ITSMTicket, ITSMExtremeTicket, ITSMExtremes
- `services/customer-api/app/main.py` — wired ITSMService + itsm router
- `src/services/api_client.py` — added get_customer_itsm_{summary,extremes,tickets}
- `src/pages/customer_view.py` — added _tab_itsm, _fmt_hours, _priority_color, _itsm_ticket_table, _itsm_tickets_for_export; updated _build_customer_export_sheets, _customer_content, build_customer_layout
- `../datalake-platform-knowledge-base/wiki/02-Module-Platform-GUI.md` — Customer ITSM tab section

## Test results

```
services/customer-api:
  tests/test_customer_needle.py  — 11/11 passed
  tests/test_itsm_service.py     — 10/10 passed

Datalake-Platform-GUI:
  tests/test_customer_view_itsm_tab.py — 18/18 passed
  tests/test_api_client_itsm.py        —  5/5  passed

Total: 44 tests, 0 failures
```

## Architecture decision

See [ADR-0009](../../datalake-platform-knowledge-base/adrs/ADR-0009-servicecore-customer-resolution-email-domain-chain.md) for the email-domain chain resolution approach.

## Known limitations

- **SR resolution time** cannot be computed — `discovery_servicecore_servicerequests` has no `closed_and_done_date`. Avg/median/p95 resolution KPIs cover incidents only.
- If a customer's email domain changes, the ILIKE needle will not automatically follow — the customer name in the GUI must match the new domain.
