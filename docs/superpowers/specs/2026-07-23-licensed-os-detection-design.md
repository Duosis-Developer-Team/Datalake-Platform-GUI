# Licensed OS Detection & CRM Reconciliation (TASK-81)

**Date:** 2026-07-23
**Task:** TASK-81 "Lisanslı OS Tespiti" — Bulutistan / BulutDL / Data Görselleştirme
**Description (verbatim):** _"Rhel, SUSE ve Windows OS'lerin ayırt edilerek crm eşleştirmeleri yapılmalı."_

## Problem

Bulutistan runs customer VMs whose guest operating systems fall into two groups:

- **Free** — Ubuntu, CentOS, Debian, Rocky, AlmaLinux (no vendor cost).
- **Licensed** — RHEL (Red Hat CCSP), SUSE (SLES), Windows Server (Microsoft SPLA). Each running licensed VM is a real vendor cost that must be billed back to the customer.

Today these two sides never meet:

- The **infrastructure** side knows what is actually running — the guest-OS string lives in Postgres (`raw_vmware_vm_config.guest_full_name` etc.) — but **nothing in the GUI reads it**. There is **zero** OS normalization/classification code anywhere in the three repos.
- The **CRM** side knows what was sold — `shared/sellable/panel_mapping.py` already classifies products into `license_redhat` / `license_suse` / `license_microsoft_spla` / `license_microsoft_csp` / `mgmt_os_windows`.

Nobody can answer **"how many licensed RHEL/SUSE/Windows VMs does this customer actually run, versus how many licenses were sold?"** The gap is pure revenue leakage (detected > sold → Bulutistan eats the vendor cost) or stale billing (sold > detected).

## Goal

Close the missing middle of the chain: read the guest OS, classify RHEL/SUSE/Windows apart from free/unknown, attribute each VM to a customer, count, and reconcile against the already-known CRM sold counts. Surface the result visually.

## The chain (what exists vs what we build)

| Step | Status | Location |
|------|--------|----------|
| 1. Read OS + classify | ❌ **New — the core work** | `shared/licensing/os_classifier.py` (new) |
| 2. Attribute VM → customer | ✅ Exists | `shared/customer/match.py` (customer alias matching) |
| 3. Count per customer × OS | ⚠️ New query | `services/datacenter-api/app/db/queries/` (new) |
| 4. Reconcile detected vs sold | ⚠️ New service; sold side exists | new reconciliation service |
| 5. Visualize | ⚠️ New page + Customer View section | `src/pages/` (new) + `src/pages/customer_view.py` |

The single genuinely new piece is **Step 1** — the classifier. The rest is wiring existing parts together.

## Component design

### 1. OS classifier — `shared/licensing/os_classifier.py` (new)

Deterministic rule table, **same style as `shared/sellable/panel_mapping.py`** and `datalake/collectors/Zabbix/Linux-Hana/lib/template_filter.py` (lowercase substring matching, first-match-wins, ordered most-specific-first).

**Public API:**

```python
def classify(raw: str, *, guest_id: str | None = None) -> OsClass
# OsClass = (family: str, confidence: str)
#   family     ∈ {"rhel", "suse", "windows", "free", "unknown"}
#   confidence ∈ {"confirmed", "probable", "none"}
```

Input handles two shapes seen in the data:

- **Display string** (`guest_full_name`, NetBox `custom_fields_guest_os`, Nutanix `guest_os`): e.g. `"Red Hat Enterprise Linux 8 (64-bit)"`, `"Microsoft Windows Server 2019 (64-bit)"`, `"SUSE Linux Enterprise 15 (64-bit)"`, `"Ubuntu Linux (64-bit)"`.
- **vSphere enum** (`guest_id`): e.g. `rhel8_64Guest`, `sles15_64Guest`, `windows2019srv_64Guest`, `centos8_64Guest`, `ubuntu64Guest`, `otherLinux64Guest`, `otherGuest`.

**Family rules (lowercase substring):**

- `rhel` ← `"red hat"`, `"rhel"`
- `suse` ← `"suse"`, `"sles"`
- `windows` ← `"windows"`, `"microsoft windows"`, enum prefix `windows*`
- `free` ← `"ubuntu"`, `"centos"`, `"debian"`, `"rocky"`, `"alma"`, `"oracle linux"`, `"amazon linux"`, `"fedora"`
- `unknown` ← anything else, incl. `"other linux"`, `otherGuest`, `otherLinux64Guest`, empty/NULL

**Confidence:**

- `confirmed` — matched a licensed/free family from an explicit signal.
- `probable` — reserved for weaker signals (e.g. VMware Tools field NULL, config falls to `otherLinux64Guest` but a secondary hint exists such as the VM-name heuristic observed in Nutanix snapshot data). Phase 1 may emit only `confirmed`/`none`; the `probable` bucket must exist in the type from day one so the UI never has to be reshaped.
- `none` — `unknown` family; no reliable signal. Never upgraded to a licensed guess.

### 2. Detection query — `services/datacenter-api` (new)

- **Primary source:** `raw_vmware_vm_config` — `guest_id` (deterministic enum) + `guest_full_name` (display), latest row per VM.
- **Truth correction:** COALESCE with `raw_vmware_vm_runtime.guest_guest_full_name` (VMware-Tools-reported actual OS) to catch VMs provisioned as `otherLinux64Guest`. This field is frequently NULL (powered-off / Tools absent) — coalesce, never depend on it.
- **Customer attribution:** existing `shared/customer/match.py` alias resolution.
- **Output shape:** rows of `(customer, family, confidence, vm_count)` — plus a global (all-customers) rollup for the overview.
- **Phase 1 = VMware only.** Nutanix (`nutanix_vm_metrics.guest_os`, NGT-dependent, NULL-heavy) and IBM come later behind the same output interface.

### 3. Reconciliation service (new)

- **Sold side (exists):** CRM per-customer license counts already flow through `panel_mapping.py` → `license_redhat` / `license_suse` / `license_microsoft_spla` + `license_microsoft_csp` / `mgmt_os_windows`, and are already surfaced in Customer View's "Sold vs used (other categories)" section.
- **Reconcile:** per customer × OS family produce `(detected, sold, delta)`. `delta = detected − sold`. `delta > 0` (more running than sold) = billing leakage → red flag.
- OS-family → CRM-category mapping: `rhel → license_redhat`, `suse → license_suse`, `windows → license_microsoft_spla + license_microsoft_csp + mgmt_os_windows` (Windows sold count aggregates the Microsoft licensing categories).
- Classification cannot be expressed as a plain `gui_panel_infra_source` SQL column binding (it needs the classifier), so reconciliation is a **dedicated service path**, not the generic panel binding.

### 4. Visualization — two surfaces fed by one data layer

- **New "Lisanslı OS" page** (`src/pages/licensed_os.py`, new): top = global distribution (RHEL / SUSE / Windows / unknown counts); bottom = per-customer reconciliation table `(customer, OS, detected, sold, delta)`. DC filter. Export via existing export helpers.
- **Customer View** (`src/pages/customer_view.py`): add RHEL/SUSE/Windows rows to the existing "Sold vs used (other categories)" section — the sold column is already populated; we fill the **detected** column from the reconciliation service.

## Boundaries (accepted up front)

- **IBM Power out of scope this phase.** `ibm_lpar_general.lpar_details_ostype` returns only `Linux`/`AIX`/`IBMi` — it cannot distinguish RHEL from SUSE, which the task explicitly requires. Deferred to a follow-up task (needs Zabbix/NetBox enrichment).
- **The "unknown" bucket is permanent and shown honestly.** Other-Linux and Tools-absent VMs will never be classified with certainty. Never fabricate a licensed guess; surface unknowns as a separate "needs manual review" list. No false precision.
- Nutanix included only after VMware is complete and correct, behind the same detection interface.

## Testing (TDD)

- **Classifier** — table-driven tests first: every family, both input shapes (display string + enum), and edge cases (empty, NULL, mixed case, `"Other Linux"`, `otherGuest`, whitespace, partial matches like `"Red Hat"` alone). This is the highest-value test surface.
- **Reconciliation service** — unit tests for delta computation, the Windows multi-category aggregation, and the detected/sold join including the zero-sold and zero-detected edges.
- **Detection query** — test against fixture rows covering the COALESCE(config, runtime) fallback and customer attribution.
- Follow the existing `tests/` conventions (203 test files; `test_customer_view_sold_vs_used.py`, `test_crm_sellable_potential_page.py` are the nearest patterns).

## Build order

1. `os_classifier.py` + tests (pure, no deps — fully testable in isolation).
2. Detection query (VMware) + tests.
3. Reconciliation service + tests.
4. New "Lisanslı OS" page.
5. Customer View "Sold vs used" detected-column wiring.
6. (Later phases) Nutanix, then IBM.

## Repo scope

All work is inside **`Datalake-Platform-GUI`** (`shared/`, `services/datacenter-api`, `src/pages`). No changes to sibling repos in this phase. A dedicated worktree under `.claude/worktrees/` per the repo's existing convention.
