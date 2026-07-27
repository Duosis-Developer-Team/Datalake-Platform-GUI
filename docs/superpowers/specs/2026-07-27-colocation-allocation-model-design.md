# Colocation Allocation Model — Design

**Date:** 2026-07-27 (phase 2)
**Branch:** `worktree-physical-inventory-colocation-revenue`
**Extends:** [`2026-07-27-colocation-revenue-design.md`](2026-07-27-colocation-revenue-design.md)

## Problem

Phase 1 shipped colocation revenue figures built on `discovery_loki_rack.tenant_name`.
That field is populated on 10 of 234 racks. The Colocation tab therefore reports **5
customers holding 149 U** when the real allocation is **9 customers holding 1,957 U** —
it misses 92% of the colocation footprint, including two of the three largest customers.

It also counts the empty space *inside* a customer's own rack as sellable. Boyner rents 7
racks and fills 87 of their 312 U; the remaining 225 U cannot be sold to anyone, but the
platform values it as available inventory.

## Measured reality (prod `bulutlake`, 2026-07-27)

### Rack roles are authoritative and named

`loki_racks.role_name` resolves the `role_id` on `discovery_loki_rack`:

| `role_id` | `role_name` |
|---|---|
| 1 | NETWORK RACK |
| 2 | HOST RACK |
| 3 | **NON-STANDART RACK** |
| 4 | **CUSTOMER RACK** |

Roles 3 and 4 are the colocation estate. Deduplicated on `(rack_name, site_name)`:

- role 4 (CUSTOMER RACK): **43 racks, 1,972 U**
- role 3 (NON-STANDART RACK): **6 racks, 252 U**

**Cross-system confirmation:** NetBox's "NON-STANDART RACK" is the same thing as the CRM
product "Veri Merkezi Barındırma Hizmeti (Standart Dışı Kabinet)" (232,453.88 TL), and
CUSTOMER RACK corresponds to "(Standart Kabinet)" (187,750.94 TL). Two independent systems
name the same distinction, which is what makes role-based pricing defensible.

### The customer name lives in three different fields

| Field | Example | Customers found only here |
|---|---|---|
| `tenant_name` | Boyner, AytemizBank, Turkonay | — |
| `tags[].name` | `SABANCI DX CO LOCATION`, `BOYNER CO LOCATION`, `CUSTOMER` | **SABANCI DX (18 racks, 821 U)** |
| `description` | `AKSIGORTA`, `GATEWAY HOLDING`, `VERION`, `HRWEB` | **AKSIGORTA (11 racks, 517 U)** |

Reading only `tenant_name` is why Sabancı DX and Aksigorta — the two largest colocation
customers after nobody — are invisible today.

### Resolved allocation

**These figures replace an earlier draft of this table.** The draft came from an ad-hoc probe
that deduplicated racks by name alone and silently assigned conflicted racks to a guessed
customer. The numbers below are what the shipped implementation actually produces, measured
against prod after the tie-break was made order-independent:

| Customer | Racks | Allocated U | Used U |
|---|---|---|---|
| SABANCI DX | 18 | 851 | 83 |
| **Unattributed** | **10** | **465** | **214** |
| AKSIGORTA | 8 | 376 | 228 |
| BOYNER | 7 | 312 | 222 |
| VERION | 1 | 45 | 10 |
| GATEWAY HOLDING | 1 | 42 | 19 |
| ANKARA SIGORTA EXADATA | 1 | 42 | 18 |
| TURKONAY | 1 | 42 | 19 |
| AYTEMIZBANK | 1 | 42 | 18 |
| HRWEB | 1 | 42 | 13 |
| **Total** | **49** | **2,259** | **844** |

Sellable free U (outside colocation racks): **4,477**, worth **46,698,870.68 TL** at the per-U
list price. Whole-estate figures are unchanged from phase 1: 188 racks, 8,603 total U, 5,892
total free U.

### Four racks have irreconcilable ownership

These carry two colocation-role rows naming different customers. They resolve to
**Unattributed** and log the conflict — the alternative was picking a winner by which row the
collector happened to paginate first, which the spec's own "never guessed" rule forbids:

| Rack | Competing claims |
|---|---|
| 112 / ISTANBUL | `tenant_name = AytemizBank` vs `description = AKSIGORTA` |
| 114 / ISTANBUL | tag `FINANS CLOUD` vs `description = AKSIGORTA` |
| 116 / ISTANBUL | tag `FINANS CLOUD` vs `description = AKSIGORTA` |
| 306 / ISTANBUL | tag `SABANCI DX CO LOCATION` vs `description = TURKONAY` |

Each is worth 42-47 U. They are a NetBox data-entry question, not a code question.

### A rack's identity and its capacity can come from different rows

Racks 204, 303, 304 and 305 have a colocation-role duplicate and a HOST-role duplicate whose
capacities disagree (42 vs 52). Identity comes from the colocation row; capacity stays
max-merged, as it is for every other duplicate in the system. So rack 303 reports SABANCI DX
with 52 U even though its colocation row says 42 U.

This is deliberate. Making capacity follow identity would make the merge order-dependent —
the same two rows would yield 42 or 52 depending on which arrived first — and there is no
signal in the data for which capacity is physically real. Uniformity and commutativity were
chosen over per-row fidelity. It accounts for +30 U of SABANCI DX's allocation.

## Design

### 1. Allocation replaces tenancy as the source

A rack belongs to a colocation customer when its `role_id` resolves to CUSTOMER RACK or
NON-STANDART RACK. The customer name resolves in this precedence, first hit wins:

1. `tenant_name`, trimmed
2. a `tags[].name` matching `/CO\s*LOCATION|COLOCATION/i`, with the marker suffix stripped
   (`SABANCI DX CO LOCATION` → `SABANCI DX`)
3. `description`, trimmed

Names normalise case-insensitively so `TURKONAY` and `Turkonay` are one customer. A rack
whose role is colocation but whose name resolves to nothing is attributed to an explicit
**Unattributed** bucket — never dropped, never guessed.

The `tags` value is JSON; parse defensively and treat a malformed value as absent.

### 2. Allocated and used are different numbers, and both are shown

- **Allocated U** — the capacity of every rack assigned to that customer (Boyner: 312).
- **Used U** — front-face U-slots occupied by that customer's devices (Boyner: 87).

Which one a customer is billed on is a commercial question the data cannot answer: none of
these customers has any CRM sales record at all (see the phase-1 follow-ups doc — the
datalake only collects `PRJ-` project orders, and colocation is recurring service billing).
The UI therefore shows both and asserts neither as revenue.

### 3. Sellable free U excludes customer-allocated racks

Free U inside a colocation-role rack is not sellable inventory — it belongs to the customer
holding that rack. The potential figure counts only free U in racks that are **not**
colocation-allocated.

Expected effect: platform potential falls from 61.46 M TL to roughly 47 M TL. The number
gets smaller and correct. Report the measured before/after in the implementation, do not
assume this estimate.

### 4. Per-rack pricing follows the role

Where a whole-rack figure is wanted, CUSTOMER RACK prices at the Standart Kabinet rate and
NON-STANDART RACK at the Standart Dışı rate, both read live from
`discovery_crm_productpricelevels` alongside the existing per-U product. No literal prices
in application code — the phase-1 constraint stands.

## Non-goals

- **Deciding whether customers are billed per-U or per-cabinet.** Not in the data. Both
  figures are shown; the commercial answer is a business input.
- **Fixing the missing recurring-revenue collection or the `statecode IN (3,4)` filter that
  matches zero rows.** Recorded in the phase-1 follow-ups; both are their own work.
- **Naming the 6 unattributed racks.** They surface as Unattributed until NetBox is filled in.

## Testing

- Name resolution: each of the three sources wins in precedence order; a malformed `tags`
  JSON falls through to `description`; case-variant names collapse to one customer; a rack
  with no resolvable name lands in Unattributed rather than being dropped.
- Role gating: only roles 3 and 4 are treated as colocation; a HOST RACK with a tenant name
  is not a colocation customer.
- Sellable exclusion: free U inside a colocation-role rack is absent from the potential
  figure, and the totals still reconcile against the rack-dedup baseline.
- Regression: the `(rack_name, site_name)` dedup guard still holds — 188 racks.

## Risk

The role mapping comes from `loki_racks`, whose last `collection_time` is 2026-04-12 —
about three months stale. The `role_id` → `role_name` mapping is a stable lookup rather
than live state, so staleness is tolerable for naming the roles, but the implementation
must not depend on `loki_racks` for per-rack facts. Read roles from
`discovery_loki_rack.role_id` and use `loki_racks` only to resolve what the id means; if
that becomes a maintenance concern, hard-code the four-role mapping with a comment citing
this measurement.
