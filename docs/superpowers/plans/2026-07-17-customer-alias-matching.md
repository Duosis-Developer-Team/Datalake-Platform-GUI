# Customer Alias Matching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the four customer-alias match methods (`contains`/`prefix`/`suffix`/`exact`) behave identically and correctly everywhere, and restrict `id_exact` to the sources where it means something.

**Architecture:** One new module, `shared/customer/match.py`, owns all match semantics. The match decision is derived exactly once from `(data_source, method, value)` and is never re-inferred from a pattern string downstream. The module emits two artefacts from one table: an SQL ILIKE pattern and an in-memory predicate. A parity test simulates Postgres ILIKE and asserts the two agree for every method × value × name combination, which makes future divergence a CI failure rather than a silent production bug. All four existing match sites are rewired to consume it.

**Tech Stack:** Python 3.11, pytest, Postgres (psycopg), Dash/Mantine UI.

## Global Constraints

- Work happens in the worktree: `.claude/worktrees/customer-alias-matching` on branch `worktree-customer-alias-matching`, based on `3de24d83`. Paths below are relative to that worktree root, written `$W`.
- **Interpreter:** `$PY = /Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI/.venv/bin/python`. The venv lives in the main checkout; the worktree has none. Do not symlink it in — `.gitignore` has `.venv/` with a trailing slash, which matches directories only, so a symlink shows up as untracked and dirties the tree. System `python3` is 3.9 and dies on `X | None`.
- **The three test suites cannot be combined in one pytest run.** `tests/`, `services/customer-api/tests/` and `services/datacenter-api/tests/` each have an `__init__.py`, so they all resolve to the package name `tests` and pytest raises `ImportPathMismatchError`. This is pre-existing. Run each from its own directory:

  ```bash
  # root (shared/ + Dash UI)
  cd $W && $PY -m pytest tests/<file> -q

  # customer-api
  cd $W/services/customer-api && $PY -m pytest tests/ -q

  # datacenter-api — needs shared/ on the path; its conftest does not add it,
  # and app/config.py does `env_file = ".env"`, so running from the repo root
  # makes pydantic Settings swallow the root .env and die on extra_forbidden.
  cd $W/services/datacenter-api && PYTHONPATH=$W $PY -m pytest tests/ -q
  ```

- **Known-failing at baseline — not caused by this work, do not chase:**

  | Suite | Failure |
  |---|---|
  | root `tests/` | `test_backup_sidebar_helpers.py` — collection error, `KeyError: '_compute_backup_tr'` |
  | root `tests/` | `test_zabbix_query_deduplication.py` — collection error, `No module named 'app.db'` (root `app.py` shadows the `app/` package) |
  | customer-api | `test_sellable_service.py::test_recompute_family_constraints_global_host_fallback_uses_star_compute` |
  | datacenter-api | `test_dc_service_host_rows_slice.py::test_classic_host_rows_single_sql_for_cluster_subsets` |
  | datacenter-api | `test_host_rows.py::test_datastore_metrics_excludes_backup_datastores` |

  Green baseline to preserve: `tests/test_unmapped_classifier.py` 17 passed; customer-api 368 passed / 1 failed; datacenter-api 230 passed / 2 failed / 29 skipped.
- `shared/` is importable from every service: each Dockerfile does `COPY shared/ ./shared/`, and `services/*/tests/conftest.py` appends the GUI root to `sys.path`. Do not duplicate match code into a service.
- Postgres' default LIKE/ILIKE escape character is backslash. Patterns are passed as bind parameters, so `\_` works with no `ESCAPE` clause. Never string-interpolate a pattern into SQL.
- Do not change the DB table name: `gui_crm_customer_source_mapping`.
- Next free webui migration number: `028`.
- Turkish is fine in commit messages; code and comments stay in English to match the codebase.

## Product decisions (already made — do not re-litigate)

1. **`_` and `%` in an alias value are literal characters, not wildcards.** They get escaped.
2. **Explicit rules suppress the display-name fallback.** If a source has any rule, no `%DisplayName%` guess is added for it. (This is already the code's intent; it only failed because `exact` produced no patterns.)
3. **`id_exact` is only valid for `physical_device` and `auranotify`.** It must be rejected everywhere else, at three layers: UI, API, DB.
4. **One shared module** is the single source of truth.
5. **`exact` is implemented as a wildcard-free ILIKE.** An ILIKE with no wildcards *is* a case-insensitive equality test, which is exactly what the in-memory `==` does. This lets the `exact_by_source` bucket be deleted so only one consumption path survives.

## Background: the four bugs this fixes

| # | Bug | Evidence |
|---|-----|----------|
| 1 | `exact` is dead code — `exact_by_source` is populated but never read by any query | Whole-repo grep finds 3 references: definition, `has_mappings`, population |
| 2 | No ILIKE wildcard escaping — `contains 'Boyner_Dr'` also matches `BoynerXDr` | Measured against a Postgres ILIKE simulator |
| 3 | Four unsynced match implementations | resolver / adapter / classifier / dc_service |
| 4 | `id_exact` unvalidated — selectable for name-based sources; SQL drops the rule, Python treats it as `contains '5'` | UI offers it; no API check; no DB CHECK |

---

### Task 1: Create `shared/customer/match.py` with a parity test

**Files:**
- Create: `shared/customer/match.py`
- Create: `tests/test_customer_match.py`

**Interfaces:**
- Consumes: nothing (pure module, no imports from the repo).
- Produces, relied on by every later task:
  - `TEXT_METHODS: tuple[str, ...]` = `("contains", "prefix", "suffix", "exact")`
  - `ID_METHODS: tuple[str, ...]` = `("id_exact",)`
  - `ALL_METHODS: tuple[str, ...]`
  - `ID_SOURCES: tuple[str, ...]` = `("physical_device", "auranotify")`
  - `DEFAULT_METHOD: str` = `"contains"`
  - `escape_like(value: str) -> str`
  - `sql_pattern(method: str, value: str) -> tuple[str, str]` — returns `("ilike", pattern)` or `("id_exact", raw_value)`
  - `predicate(method: str, value: str) -> Callable[[str], bool]`
  - `allowed_methods(data_source: str) -> tuple[str, ...]`
  - `is_allowed(data_source: str, method: str) -> bool`
  - `normalize_method(data_source: str, method: str) -> str`

- [ ] **Step 1: Write the failing test**

Create `tests/test_customer_match.py`:

```python
"""Parity + behaviour tests for shared.customer.match (pure, no DB).

The parity test is the point of this file: it simulates Postgres ILIKE and
asserts sql_pattern() and predicate() agree for every method x value x name.
If someone ever changes one side only, this goes red.
"""
import re
import unittest

from shared.customer import match


def ilike_matches(pattern: str, name: str) -> bool:
    """Simulate Postgres ILIKE with the default backslash escape character."""
    out: list[str] = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "\\" and i + 1 < len(pattern):
            out.append(re.escape(pattern[i + 1]))
            i += 2
            continue
        if ch == "%":
            out.append(".*")
        elif ch == "_":
            out.append(".")
        else:
            out.append(re.escape(ch))
        i += 1
    return re.fullmatch("".join(out), name, re.IGNORECASE | re.DOTALL) is not None


class TestEscapeLike(unittest.TestCase):
    def test_escapes_wildcards_and_backslash(self):
        self.assertEqual(match.escape_like("Boyner_Dr"), r"Boyner\_Dr")
        self.assertEqual(match.escape_like("50%"), r"50\%")
        self.assertEqual(match.escape_like(r"a\b"), r"a\\b")

    def test_empty_is_safe(self):
        self.assertEqual(match.escape_like(""), "")


class TestSqlPattern(unittest.TestCase):
    def test_four_text_methods(self):
        self.assertEqual(match.sql_pattern("contains", "Boyner"), ("ilike", "%Boyner%"))
        self.assertEqual(match.sql_pattern("prefix", "Boyner"), ("ilike", "Boyner%"))
        self.assertEqual(match.sql_pattern("suffix", "Boyner"), ("ilike", "%Boyner"))
        self.assertEqual(match.sql_pattern("exact", "Boyner"), ("ilike", "Boyner"))

    def test_exact_is_wildcard_free_ilike(self):
        kind, pattern = match.sql_pattern("exact", "Boyner_Dr")
        self.assertEqual(kind, "ilike")
        self.assertEqual(pattern, r"Boyner\_Dr")

    def test_underscore_is_escaped_in_every_text_method(self):
        for method in match.TEXT_METHODS:
            _kind, pattern = match.sql_pattern(method, "Boyner_Dr")
            self.assertIn(r"\_", pattern, f"{method} must escape underscore")

    def test_id_exact_passes_value_through(self):
        self.assertEqual(match.sql_pattern("id_exact", "5"), ("id_exact", "5"))

    def test_unknown_method_falls_back_to_contains(self):
        self.assertEqual(match.sql_pattern("bogus", "Boyner"), ("ilike", "%Boyner%"))


class TestPredicate(unittest.TestCase):
    def test_four_text_methods(self):
        self.assertTrue(match.predicate("contains", "boyner")("xxBoynerxx"))
        self.assertTrue(match.predicate("prefix", "boyner")("Boyner-vm01"))
        self.assertTrue(match.predicate("suffix", "vm01")("Boyner-vm01"))
        self.assertTrue(match.predicate("exact", "boyner")("Boyner"))
        self.assertFalse(match.predicate("exact", "boyner")("Boyner-vm01"))

    def test_underscore_is_literal(self):
        p = match.predicate("contains", "Boyner_Dr")
        self.assertTrue(p("Boyner_Dr_Prod"))
        self.assertFalse(p("BoynerXDr"))

    def test_empty_value_never_matches(self):
        self.assertFalse(match.predicate("contains", "")("anything"))
        self.assertFalse(match.predicate("contains", "   ")("anything"))

    def test_id_exact_never_name_matches(self):
        # Mirrors SQL: an id_exact rule contributes no name pattern at all.
        self.assertFalse(match.predicate("id_exact", "5")("srv-5-web"))


class TestAllowedMethods(unittest.TestCase):
    def test_id_sources_only_allow_id_exact(self):
        for source in match.ID_SOURCES:
            self.assertEqual(match.allowed_methods(source), match.ID_METHODS)
            self.assertTrue(match.is_allowed(source, "id_exact"))
            self.assertFalse(match.is_allowed(source, "contains"))

    def test_name_sources_reject_id_exact(self):
        for source in ("virtualization", "netbox_vm_customer", "backup_veeam", "s3_icos"):
            self.assertEqual(match.allowed_methods(source), match.TEXT_METHODS)
            self.assertFalse(match.is_allowed(source, "id_exact"))
            self.assertTrue(match.is_allowed(source, "exact"))

    def test_normalize_method_repairs_bad_input(self):
        self.assertEqual(match.normalize_method("virtualization", "id_exact"), "contains")
        self.assertEqual(match.normalize_method("physical_device", "contains"), "id_exact")
        self.assertEqual(match.normalize_method("virtualization", "PREFIX"), "prefix")


class TestSqlPredicateParity(unittest.TestCase):
    """The guard: SQL and in-memory must agree, for every method and every name."""

    VALUES = ["Boyner", "Boyner_Dr", "boynerdr2_boynerdr2", "50%", "A_B", r"back\slash"]
    NAMES = [
        "Boyner", "boyner", "BOYNER",
        "Boyner_Dr", "BoynerXDr", "Boyner-Dr", "Boyner Dr",
        "Boyner_Dr_Prod", "prefix-Boyner_Dr", "50%", "50X", "A_B", "AxB",
        "boynerdr2_boynerdr2", r"back\slash", "unrelated-vm",
        # Whitespace: ILIKE compares the column as stored, so predicate() must
        # not strip the name either. These lock that in.
        "Boyner ", " Boyner", "",
    ]

    def test_parity(self):
        for method in match.ALL_METHODS:
            for value in self.VALUES:
                kind, pattern = match.sql_pattern(method, value)
                pred = match.predicate(method, value)
                for name in self.NAMES:
                    py = pred(name)
                    if kind == "id_exact":
                        sql = False  # id_exact contributes no name pattern
                    else:
                        sql = ilike_matches(pattern, name)
                    self.assertEqual(
                        sql, py,
                        f"divergence: method={method!r} value={value!r} name={name!r} "
                        f"pattern={pattern!r} sql={sql} python={py}",
                    )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PY -m pytest tests/test_customer_match.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'shared.customer.match'`

- [ ] **Step 3: Write minimal implementation**

Create `shared/customer/match.py`:

```python
"""Single source of truth for customer alias match semantics.

Every consumer — the SQL pattern resolver, the unmapped classifier, and the
physical-inventory filter — derives its behaviour from here. The decision is
made once, from (data_source, method, value), and is never re-derived from a
pattern string further down the pipeline. Re-deriving intent from a pattern is
what made the four implementations drift apart in the first place.

`exact` is expressed as a wildcard-free ILIKE: an ILIKE with no wildcards is a
case-insensitive equality test, identical to what predicate() does. That keeps a
single consumption path (ilike) instead of a second 'exact' bucket.
"""
from __future__ import annotations

from typing import Callable

TEXT_METHODS: tuple[str, ...] = ("contains", "prefix", "suffix", "exact")
ID_METHODS: tuple[str, ...] = ("id_exact",)
ALL_METHODS: tuple[str, ...] = TEXT_METHODS + ID_METHODS

DEFAULT_METHOD: str = "contains"

# Sources correlated by numeric tenant id rather than by name. A name-matching
# method here (or an id method on a name source) is a configuration error.
ID_SOURCES: tuple[str, ...] = ("physical_device", "auranotify")


def allowed_methods(data_source: str) -> tuple[str, ...]:
    """The methods that are meaningful for this data source."""
    return ID_METHODS if (data_source or "").strip() in ID_SOURCES else TEXT_METHODS


def is_allowed(data_source: str, method: str) -> bool:
    return (method or "").strip().lower() in allowed_methods(data_source)


def normalize_method(data_source: str, method: str) -> str:
    """Coerce a possibly-invalid method into a valid one for this source."""
    candidate = (method or "").strip().lower()
    if is_allowed(data_source, candidate):
        return candidate
    return ID_METHODS[0] if (data_source or "").strip() in ID_SOURCES else DEFAULT_METHOD


def escape_like(value: str) -> str:
    """Escape LIKE/ILIKE wildcards so the value matches literally.

    Postgres' default LIKE escape character is backslash, so no ESCAPE clause is
    needed — provided the result is passed as a bind parameter, never inlined.
    Backslash is escaped first so the later replacements are not re-escaped.
    """
    return (value or "").replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def sql_pattern(method: str, value: str) -> tuple[str, str]:
    """Return (kind, pattern): ('ilike', pattern) or ('id_exact', raw_value)."""
    cleaned = (value or "").strip()
    key = (method or DEFAULT_METHOD).strip().lower()
    if key == "id_exact":
        return "id_exact", cleaned
    escaped = escape_like(cleaned)
    if key == "exact":
        return "ilike", escaped
    if key == "prefix":
        return "ilike", f"{escaped}%"
    if key == "suffix":
        return "ilike", f"%{escaped}"
    return "ilike", f"%{escaped}%"


def predicate(method: str, value: str) -> Callable[[str], bool]:
    """In-memory counterpart of sql_pattern, with identical semantics.

    Case-insensitive, wildcard-free. id_exact never matches a name: it resolves
    through tenant ids, and contributes no name pattern on the SQL side either.

    The *value* is stripped, mirroring sql_pattern. The *name* is deliberately
    NOT stripped: ILIKE compares the column as stored, so stripping here would
    make `exact` match a trailing-space name that SQL rejects. Parity beats
    tidiness — the caller normalises the name if it wants that.
    """
    needle = (value or "").strip().lower()
    key = (method or DEFAULT_METHOD).strip().lower()

    if key == "id_exact" or not needle:
        return lambda name: False

    if key == "prefix":
        return lambda name: (name or "").lower().startswith(needle)
    if key == "suffix":
        return lambda name: (name or "").lower().endswith(needle)
    if key == "exact":
        return lambda name: (name or "").lower() == needle
    return lambda name: needle in (name or "").lower()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PY -m pytest tests/test_customer_match.py -q`
Expected: PASS — 21 passed

- [ ] **Step 5: Commit**

```bash
git add shared/customer/match.py tests/test_customer_match.py
git commit -m "feat(match): single source of truth for alias match semantics

Adds shared/customer/match.py: escape_like, sql_pattern, predicate and the
id_exact source restriction, plus a parity test that simulates Postgres ILIKE
and asserts the SQL and in-memory paths agree for every method x value x name."
```

---

### Task 2: Measure production impact before any behaviour ships

**Files:**
- Create: `scripts/alias_match_impact_report.py`

**Interfaces:**
- Consumes: `shared.customer.match.sql_pattern`, `shared.customer.match.is_allowed` (Task 1).
- Produces: a printed report. No later task depends on its return value; it is a human gate.

This task exists because Task 3 changes what customers see. The escaping decision is made, but we ship it knowing the size of the change, not hoping it is zero. The script is strictly read-only — `SELECT` only.

- [ ] **Step 1: Write the script**

Create `scripts/alias_match_impact_report.py`:

```python
#!/usr/bin/env python3
"""Read-only report: which alias rules change behaviour under the match fix?

Answers three questions before the fix ships:
  1. Which rules contain LIKE wildcards (_ or %) that are about to become literal?
  2. Which rules use `exact` (today silently dropped, about to start working)?
  3. Which rules use a method that is invalid for their data source?

Usage:
    $PY scripts/alias_match_impact_report.py

Requires the same DB env vars the customer-api uses. Runs SELECTs only.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg
from psycopg.rows import dict_row

from shared.customer import match

QUERY = """
SELECT crm_account_name, data_source, match_method, match_value, enabled
FROM gui_crm_customer_source_mapping
WHERE enabled = TRUE
ORDER BY crm_account_name, data_source, priority
"""


def dsn() -> str:
    return (
        f"host={os.environ.get('DB_HOST', 'localhost')} "
        f"port={os.environ.get('DB_PORT', '5432')} "
        f"dbname={os.environ.get('DB_NAME', 'webui')} "
        f"user={os.environ.get('DB_USER', 'postgres')} "
        f"password={os.environ.get('DB_PASS', '')}"
    )


def main() -> int:
    with psycopg.connect(dsn(), row_factory=dict_row) as conn:
        rows = conn.execute(QUERY).fetchall()

    wildcard_rows = []
    exact_rows = []
    invalid_rows = []

    for row in rows:
        value = str(row["match_value"] or "")
        method = str(row["match_method"] or "")
        source = str(row["data_source"] or "")

        if ("_" in value or "%" in value) and method in match.TEXT_METHODS:
            wildcard_rows.append(row)
        if method == "exact":
            exact_rows.append(row)
        if not match.is_allowed(source, method):
            invalid_rows.append(row)

    def dump(title: str, subset: list, note: str) -> None:
        print("=" * 78)
        print(f"{title}: {len(subset)} rule(s)")
        print(note)
        print("=" * 78)
        for r in subset:
            old = f"%{r['match_value']}%" if r["match_method"] == "contains" else r["match_value"]
            _kind, new = match.sql_pattern(r["match_method"], r["match_value"])
            print(f"  {r['crm_account_name'][:28]:28s} {r['data_source'][:20]:20s} "
                  f"{r['match_method']:9s} {r['match_value'][:24]:24s}")
            print(f"      before: {old!r}")
            print(f"      after : {new!r}")
        print()

    print(f"\nTotal enabled rules: {len(rows)}\n")
    dump("WILDCARD -> LITERAL", wildcard_rows,
         "These match MORE rows today than they will after the fix.")
    dump("EXACT (currently dropped)", exact_rows,
         "These do nothing today. After the fix they start filtering.")
    dump("INVALID method for source", invalid_rows,
         "These must be corrected or deleted before the DB CHECK is validated.")

    print("=" * 78)
    print(f"SUMMARY  wildcard={len(wildcard_rows)}  exact={len(exact_rows)}  "
          f"invalid={len(invalid_rows)}  total={len(rows)}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run it against the real database**

Run: `$PY scripts/alias_match_impact_report.py`
Expected: a report. Do not proceed to Task 3 until a human has read the three counts.

If the `invalid` count is greater than zero, those rows are the silent hole from bug #4 — decide per row whether to correct the method or delete the rule, and do it before Task 7 validates the constraint.

- [ ] **Step 3: Commit**

```bash
git add scripts/alias_match_impact_report.py
git commit -m "chore(match): read-only impact report for the alias match fix"
```

---

### Task 3: Rewire `customer_mapping_resolver` and delete `exact_by_source`

**Files:**
- Modify: `services/customer-api/app/services/customer_mapping_resolver.py` (`sql_pattern_for_match` at :122, `ResolvedSourcePatterns` at :95-119, `build_resolved_patterns` at :137-186)
- Modify: `services/customer-api/tests/test_customer_mapping_resolver.py` (:15-20)

**Interfaces:**
- Consumes: `shared.customer.match.sql_pattern` (Task 1).
- Produces:
  - `sql_pattern_for_match(method, value)` stays as a thin re-export so existing importers keep working; it now delegates to `match.sql_pattern`.
  - `ResolvedSourcePatterns` loses the `exact_by_source` field entirely.
  - `MATCH_METHODS` is re-exported from `match.ALL_METHODS`.

- [ ] **Step 1: Update the failing test**

The existing test encodes bug #1 (`("exact", "Boyner")`). Replace the body of `test_sql_pattern_for_match_contains_prefix_suffix_exact` in `services/customer-api/tests/test_customer_mapping_resolver.py` with:

```python
def test_sql_pattern_for_match_contains_prefix_suffix_exact():
    assert sql_pattern_for_match("contains", "Boyner") == ("ilike", "%Boyner%")
    assert sql_pattern_for_match("prefix", "Boyner") == ("ilike", "Boyner%")
    assert sql_pattern_for_match("suffix", "Boyner") == ("ilike", "%Boyner")
    # exact is a wildcard-free ILIKE, not a separate bucket
    assert sql_pattern_for_match("exact", "Boyner") == ("ilike", "Boyner")
    assert sql_pattern_for_match("id_exact", "5") == ("id_exact", "5")


def test_exact_rule_reaches_the_query_and_suppresses_the_fallback():
    rules = [MappingRule(data_source="virtualization", match_method="exact", match_value="Boyner_Dr")]
    resolved = build_resolved_patterns(rules, fallback_search_name="Boyner")
    # The rule produces a pattern (bug #1: it used to produce none) ...
    assert resolved.ilike_patterns("virtualization") == [r"Boyner\_Dr"]
    # ... so the display-name fallback must not also fire for that source.
    assert "%Boyner%" not in resolved.ilike_patterns("virtualization")


def test_netbox_vm_customer_exact_rules_are_not_lost():
    rules = [MappingRule(**m) for m in BOYNER_DEFAULT_MAPPINGS]
    resolved = build_resolved_patterns(rules, fallback_search_name="Boyner")
    patterns = resolved.ilike_patterns("netbox_vm_customer")
    assert len(patterns) == 6, "all six tenant rules must reach the query"
    assert r"Boyner\_Sap" in patterns


def test_id_exact_on_a_name_source_is_ignored_not_broadened():
    rules = [MappingRule(data_source="virtualization", match_method="id_exact", match_value="5")]
    resolved = build_resolved_patterns(rules, fallback_search_name="Boyner")
    # It must not become a `contains '5'` — the fallback is the only pattern.
    assert resolved.ilike_patterns("virtualization") == ["%Boyner%"]
```

Add `BOYNER_DEFAULT_MAPPINGS` to the import block at the top of that test file.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd $W/services/customer-api && $PY -m pytest tests/test_customer_mapping_resolver.py -q`
Expected: FAIL — `sql_pattern_for_match("exact", "Boyner")` returns `("exact", "Boyner")`, and `ilike_patterns("netbox_vm_customer")` is `[]`.

- [ ] **Step 3: Write the implementation**

In `services/customer-api/app/services/customer_mapping_resolver.py`:

Add the import near the top (after `from app.utils.customer_needle import customer_to_email_needle`):

```python
from shared.customer import match as alias_match
```

Replace the `MATCH_METHODS` tuple (:22-28) with a re-export:

```python
MATCH_METHODS: tuple[str, ...] = alias_match.ALL_METHODS
```

Delete the `exact_by_source` field from `ResolvedSourcePatterns` (:100) and drop it from `has_mappings` (:113-119), which becomes:

```python
    def has_mappings(self) -> bool:
        return bool(
            self.ilike_by_source
            or self.physical_tenant_ids
            or self.itsm_needles
        )
```

Replace `sql_pattern_for_match` (:122-134) with a delegating shim:

```python
def sql_pattern_for_match(method: str, value: str) -> tuple[str, str]:
    """Return (kind, pattern) where kind is 'ilike' or 'id_exact'.

    Thin wrapper: shared.customer.match owns the semantics so the SQL and
    in-memory paths cannot drift. Kept as a named function because existing
    call sites and tests import it.
    """
    return alias_match.sql_pattern(method, value)
```

In `build_resolved_patterns`, delete the `exact` branch (:157-161). The loop body becomes:

```python
    for rule in sorted_rules:
        kind, pattern = sql_pattern_for_match(rule.match_method, rule.match_value)
        if kind == "id_exact":
            if rule.data_source == "physical_device":
                try:
                    resolved.physical_tenant_ids.append(int(pattern))
                except ValueError:
                    continue
            continue
        bucket = resolved.ilike_by_source.setdefault(rule.data_source, [])
        if pattern not in bucket:
            bucket.append(pattern)
        if rule.data_source == "itsm_servicecore":
            needle = customer_to_email_needle(rule.match_value)
            if needle not in resolved.itsm_needles:
                resolved.itsm_needles.append(needle)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd $W/services/customer-api && $PY -m pytest tests/ -q
cd $W && $PY -m pytest tests/test_customer_match.py -q
```
Expected: customer-api stays at its baseline of 368 passed / 1 failed (the `test_sellable_service` failure is pre-existing); the match test stays at 21 passed. If any other test referenced `exact_by_source`, fix it now — the field is gone on purpose.

- [ ] **Step 5: Commit**

```bash
git add services/customer-api/app/services/customer_mapping_resolver.py services/customer-api/tests/test_customer_mapping_resolver.py
git commit -m "fix(match): make exact rules reach the query

exact rules landed in exact_by_source, which no query ever read: they were
silently dropped, and the display-name fallback ran in their place. exact is
now a wildcard-free ILIKE on the single ilike path, and exact_by_source is
deleted. Also fixes id_exact on a name source being dropped inconsistently."
```

---

### Task 4: Delete `_normalize_ilike_pattern` from the customer adapter

**Files:**
- Modify: `services/customer-api/app/adapters/customer_adapter.py:39-58`
- Create: `services/customer-api/tests/test_customer_adapter_patterns.py`

**Interfaces:**
- Consumes: `ResolvedSourcePatterns.ilike_patterns` (Task 3).
- Produces: `CustomerAdapter._resolve_patterns(source_patterns, source_key, fallback) -> list[str]` — unchanged signature, new behaviour: resolved patterns are returned verbatim.

This is the fourth match implementation and the subtlest one. `_normalize_ilike_pattern` throws away the method that produced a pattern and re-guesses it from the string: "no `%` in here, so it must be a bare value — make it a contains". That silently re-broadens `exact` back into `contains`, and after Task 1 it would also misfire on an escaped literal `%` (`\%` contains a `%` character). The resolver already emits final patterns; the adapter must not second-guess them.

The one behaviour worth keeping is the empty-pattern guard, which moves up into `_resolve_patterns` where it can look at whether a pattern exists rather than at what it says.

- [ ] **Step 1: Write the failing test**

Create `services/customer-api/tests/test_customer_adapter_patterns.py`:

```python
"""The adapter must pass resolved patterns through untouched."""
from __future__ import annotations

from app.adapters.customer_adapter import CustomerAdapter
from app.services.customer_mapping_resolver import MappingRule, build_resolved_patterns


def _adapter() -> CustomerAdapter:
    noop = lambda *a, **k: None
    return CustomerAdapter(noop, noop, noop, noop)


def test_exact_pattern_is_not_rebroadened_into_contains():
    rules = [MappingRule(data_source="virtualization", match_method="exact", match_value="Boyner_Dr")]
    resolved = build_resolved_patterns(rules)
    out = _adapter()._resolve_patterns(resolved, "virtualization", "%Boyner%")
    # Must stay wildcard-free. The old code wrapped it into %Boyner\_Dr%.
    assert out == [r"Boyner\_Dr"]


def test_contains_pattern_passes_through():
    rules = [MappingRule(data_source="virtualization", match_method="contains", match_value="Boyner")]
    resolved = build_resolved_patterns(rules)
    out = _adapter()._resolve_patterns(resolved, "virtualization", "%fallback%")
    assert out == ["%Boyner%"]


def test_escaped_literal_percent_is_not_mistaken_for_a_wildcard():
    rules = [MappingRule(data_source="virtualization", match_method="exact", match_value="50%")]
    resolved = build_resolved_patterns(rules)
    out = _adapter()._resolve_patterns(resolved, "virtualization", "%fallback%")
    assert out == [r"50\%"]


def test_no_patterns_falls_back():
    out = _adapter()._resolve_patterns(None, "virtualization", "%Boyner%")
    assert out == ["%Boyner%"]


def test_empty_source_patterns_falls_back():
    resolved = build_resolved_patterns([])
    out = _adapter()._resolve_patterns(resolved, "storage_ibm", "%Boyner%")
    assert out == ["%Boyner%"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd $W/services/customer-api && $PY -m pytest tests/test_customer_adapter_patterns.py -q`
Expected: FAIL — `test_exact_pattern_is_not_rebroadened_into_contains` gets `['%Boyner\\_Dr%']`.

- [ ] **Step 3: Write the implementation**

In `services/customer-api/app/adapters/customer_adapter.py`, delete the whole `_normalize_ilike_pattern` static method (:39-46) and replace `_resolve_patterns` (:48-58) with:

```python
    def _resolve_patterns(
        self,
        source_patterns: ResolvedSourcePatterns | None,
        source_key: str,
        fallback: str,
    ) -> list[str]:
        """Resolved patterns are final — never re-shape them here.

        shared.customer.match decided the semantics when the rule was turned into
        a pattern. Inferring intent from the pattern string (e.g. "no % means it
        needs wrapping") re-broadens exact rules and misreads escaped literals.
        """
        if source_patterns:
            patterns = [p for p in source_patterns.ilike_patterns(source_key) if (p or "").strip()]
            if patterns:
                return patterns
        return [fallback]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd $W/services/customer-api && $PY -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/customer-api/app/adapters/customer_adapter.py services/customer-api/tests/test_customer_adapter_patterns.py
git commit -m "fix(match): stop re-deriving match intent in the customer adapter

_normalize_ilike_pattern wrapped any wildcard-free pattern into %...%, which
turned exact rules back into contains and would misread an escaped literal %.
Patterns from the resolver are final; the adapter now passes them through."
```

---

### Task 5: Rewire `unmapped_classifier` to the shared predicate

**Files:**
- Modify: `shared/customer/unmapped_classifier.py` (`OwnerMatcher` at :49-71, `owner_matchers_from_mappings` at :124-150)
- Modify: `tests/test_unmapped_classifier.py` (append the new tests)

**Interfaces:**
- Consumes: `shared.customer.match.predicate`, `shared.customer.match.normalize_method` (Task 1).
- Produces: `OwnerMatcher(owner, kind, value)` — same constructor signature and same `matches(name_lower)` method, so `classify_unmapped` and `build_unmapped_payload` are untouched.

Two bugs live here. `matches` re-implements the four methods by hand, and the `kind` filter at :143 silently rewrites any unknown method — including `id_exact` — into `contains`, which is how `id_exact '5'` came to claim every VM with a 5 in its name.

Note `OwnerMatcher.matches` takes an already-lowercased name and the dataclass is frozen, so build the predicate on each call rather than caching it in a field.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_unmapped_classifier.py`:

```python
class TestOwnerMatcherUsesSharedSemantics(unittest.TestCase):
    def test_underscore_is_literal(self):
        m = OwnerMatcher(owner="Boyner", kind="contains", value="Boyner_Dr")
        self.assertTrue(m.matches("boyner_dr_prod"))
        self.assertFalse(m.matches("boynerxdr"))

    def test_four_methods(self):
        self.assertTrue(OwnerMatcher("o", "prefix", "boyner").matches("boyner-vm01"))
        self.assertTrue(OwnerMatcher("o", "suffix", "vm01").matches("boyner-vm01"))
        self.assertTrue(OwnerMatcher("o", "exact", "boyner").matches("boyner"))
        self.assertFalse(OwnerMatcher("o", "exact", "boyner").matches("boyner-vm01"))

    def test_empty_value_never_matches(self):
        self.assertFalse(OwnerMatcher("o", "contains", "  ").matches("anything"))


class TestIdExactIsNotBroadenedToContains(unittest.TestCase):
    def test_id_exact_rule_claims_nothing(self):
        rows = [{
            "data_source": "virtualization",
            "match_method": "id_exact",
            "match_value": "5",
            "crm_account_name": "Boyner",
        }]
        matchers = owner_matchers_from_mappings(rows, display_names=[])
        # Bug #4: this used to become contains '5' and claim every VM with a 5.
        for m in matchers:
            self.assertFalse(m.matches("srv-5-web"))

    def test_valid_rule_still_builds_a_matcher(self):
        rows = [{
            "data_source": "virtualization",
            "match_method": "prefix",
            "match_value": "Boyner",
            "crm_account_name": "Boyner",
        }]
        matchers = owner_matchers_from_mappings(rows, display_names=[])
        self.assertEqual(len(matchers), 1)
        self.assertTrue(matchers[0].matches("boyner-vm01"))
```

Make sure `OwnerMatcher` and `owner_matchers_from_mappings` are imported at the top of that test file.

- [ ] **Step 2: Run test to verify it fails**

Run: `$PY -m pytest tests/test_unmapped_classifier.py -q`
Expected: FAIL — `test_underscore_is_literal` passes already, but `test_id_exact_rule_claims_nothing` fails: the matcher claims `srv-5-web`.

- [ ] **Step 3: Write the implementation**

In `shared/customer/unmapped_classifier.py`, add to the imports:

```python
from shared.customer import match as alias_match
```

Replace `OwnerMatcher.matches` (:61-71) so the class body reads:

```python
@dataclass(frozen=True)
class OwnerMatcher:
    """One ownership predicate mirroring a mapping rule / display-name fallback.

    ``kind`` is one of shared.customer.match.ALL_METHODS. The semantics live in
    that module so this path and the SQL path cannot drift apart.
    """

    owner: str
    kind: str
    value: str

    def matches(self, name_lower: str) -> bool:
        return alias_match.predicate(self.kind, self.value)(name_lower)
```

Replace the `kind` line in `owner_matchers_from_mappings` (:142-145) with:

```python
        source = str(row.get("data_source") or "")
        method = str(row.get("match_method") or alias_match.DEFAULT_METHOD).strip().lower()
        if not alias_match.is_allowed(source, method):
            # An id_exact rule on a name source claims nothing — mirroring the SQL
            # side, which drops it. Silently rewriting it to `contains` made every
            # name containing the id vanish from Unmapped.
            continue
        owner = str(row.get("crm_account_name") or row.get("crm_accountid") or "")
        matchers.append(OwnerMatcher(owner=owner, kind=method, value=value))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$PY -m pytest tests/test_unmapped_classifier.py tests/test_customer_match.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add shared/customer/unmapped_classifier.py tests/test_unmapped_classifier.py
git commit -m "fix(match): unmapped classifier uses the shared predicate

Drops the hand-rolled four-branch matcher and the filter that rewrote any
unknown method into contains — which made an id_exact rule claim every name
containing the id, hiding those resources from the Unmapped page."
```

---

### Task 6: Rewire `dc_service._matches_device` to the shared predicate

**Files:**
- Modify: `services/datacenter-api/app/services/dc_service.py` (`_matches_device` at :6760-6770, inside `get_physical_inventory_customer`)
- Create: `services/datacenter-api/tests/test_dc_service_alias_match.py`

**Interfaces:**
- Consumes: `shared.customer.match.predicate` (Task 1).
- Produces: no new public API. `_matches_device` keeps its `(device: dict) -> bool` signature.

This is the third hand-rolled copy: `if method in {"contains", "id_exact"} and key in tenant_key` treats `id_exact` as a substring match, same bug as Task 5.

Read the enclosing function before editing — `text_rules` is a list of `(method, value)` tuples built at :6828-6840, and non-numeric `id_exact` values fall into it. After this change they match nothing, which is what the SQL path already does.

`_matches_device` is a closure inside `get_physical_inventory_customer`, so it cannot be imported or tested on its own. Extract the name-rule loop to a module-level function first — otherwise the only test you can write is one that re-implements the loop and asserts against itself, which would pass even if the service were never changed.

- [ ] **Step 1: Write the failing test**

Create `services/datacenter-api/tests/test_dc_service_alias_match.py`:

```python
"""The physical-inventory tenant filter must use the shared match semantics.

Imports the real function from dc_service — a mirror of the loop would pass
even if the service still had its own hand-rolled copy.
"""
from __future__ import annotations

from app.services.dc_service import tenant_matches_text_rules


def test_underscore_is_literal():
    assert tenant_matches_text_rules("Boyner_Dr_Prod", [("contains", "Boyner_Dr")]) is True
    assert tenant_matches_text_rules("BoynerXDr", [("contains", "Boyner_Dr")]) is False


def test_exact_does_not_match_substring():
    assert tenant_matches_text_rules("Boyner", [("exact", "Boyner")]) is True
    assert tenant_matches_text_rules("Boyner_Dr", [("exact", "Boyner")]) is False


def test_prefix_and_suffix():
    assert tenant_matches_text_rules("Boyner-vm01", [("prefix", "Boyner")]) is True
    assert tenant_matches_text_rules("x-Boyner", [("prefix", "Boyner")]) is False
    assert tenant_matches_text_rules("Boyner-vm01", [("suffix", "vm01")]) is True


def test_non_numeric_id_exact_matches_nothing():
    # Used to fall through to `key in tenant_key` and behave like contains.
    assert tenant_matches_text_rules("tenant-5", [("id_exact", "5")]) is False


def test_case_insensitive():
    assert tenant_matches_text_rules("BOYNER", [("exact", "boyner")]) is True


def test_empty_inputs():
    assert tenant_matches_text_rules("", [("contains", "Boyner")]) is False
    assert tenant_matches_text_rules("Boyner", []) is False
    assert tenant_matches_text_rules("Boyner", [("contains", "  ")]) is False


def test_any_rule_matching_is_enough():
    rules = [("exact", "nope"), ("contains", "Boyner")]
    assert tenant_matches_text_rules("x-Boyner-y", rules) is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd $W/services/datacenter-api && PYTHONPATH=$W $PY -m pytest tests/test_dc_service_alias_match.py -q
```
Expected: FAIL — `ImportError: cannot import name 'tenant_matches_text_rules' from 'app.services.dc_service'`

- [ ] **Step 3: Write the implementation**

In `services/datacenter-api/app/services/dc_service.py`, add to the `shared.*` import block (near :37-43):

```python
from shared.customer import match as alias_match
```

Add a module-level function next to the other module-level helpers (above the `DatabaseService` class):

```python
def tenant_matches_text_rules(tenant_name: str, text_rules: Sequence[tuple[str, str]]) -> bool:
    """Does a NetBox tenant name satisfy any of the customer's name rules?

    Module-level rather than a closure so it can be tested directly. The
    semantics come from shared.customer.match, so this path cannot drift from
    the SQL one — which is exactly how id_exact ended up being matched as a
    substring here.
    """
    tenant_key = (tenant_name or "").casefold()
    return any(alias_match.predicate(method, value)(tenant_key) for method, value in text_rules)
```

Check that `Sequence` is already imported from `typing` at the top of the file; add it if not.

Then replace `_matches_device` (:6753-6771) in `get_physical_inventory_customer` with:

```python
        def _matches_device(device: dict) -> bool:
            if tenant_ids and device.get("tenant_id") in tenant_ids:
                return True
            return tenant_matches_text_rules(str(device.get("tenant_name") or ""), text_rules)
```

The `if not needle: continue` guard is gone on purpose: `match.predicate` already returns a never-matching predicate for a blank value, so the guard would be dead code.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd $W/services/datacenter-api && PYTHONPATH=$W $PY -m pytest tests/ -q
```
Expected: the new file passes; the suite stays at its baseline of 230 passed / 2 failed / 29 skipped (those two failures are pre-existing — see Global Constraints).

- [ ] **Step 5: Commit**

```bash
git add services/datacenter-api/app/services/dc_service.py services/datacenter-api/tests/test_dc_service_alias_match.py
git commit -m "fix(match): physical inventory filter uses the shared predicate

Third hand-rolled copy of the four methods; it also matched id_exact as a
substring. Now delegates to shared.customer.match.predicate."
```

---

### Task 7: Reject `id_exact` on name sources at the UI, API and DB

**Files:**
- Modify: `src/utils/crm_source_mapping_ui.py:14-20`
- Modify: `src/pages/settings/integrations/crm_aliases.py:76-77`
- Modify: `services/customer-api/app/routers/customers.py` (the mapping write endpoint — locate it with the grep in Step 3)
- Create: `services/customer-api/migrations/webui/028_source_mapping_method_check.sql`
- Modify: `tests/test_crm_source_mapping_auranotify.py` (append)

**Interfaces:**
- Consumes: `shared.customer.match.allowed_methods`, `shared.customer.match.is_allowed` (Task 1).
- Produces: `method_options_for_source(data_source: str) -> list[dict]` in `src/utils/crm_source_mapping_ui.py`.

Defence in depth: the UI stops offering the option, the API rejects it if something else writes it, and the DB refuses it as a last resort. The constraint is added `NOT VALID` so existing rows are not blocked — Task 2's report tells you which rows to clean before validating it.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_crm_source_mapping_auranotify.py`:

```python
def test_method_options_exclude_id_exact_for_name_sources():
    from src.utils.crm_source_mapping_ui import method_options_for_source

    for source in ("virtualization", "netbox_vm_customer", "backup_veeam", "s3_icos"):
        values = [o["value"] for o in method_options_for_source(source)]
        assert "id_exact" not in values, f"{source} must not offer id_exact"
        assert values == ["contains", "prefix", "suffix", "exact"]


def test_method_options_are_id_only_for_id_sources():
    from src.utils.crm_source_mapping_ui import method_options_for_source

    for source in ("physical_device", "auranotify"):
        values = [o["value"] for o in method_options_for_source(source)]
        assert values == ["id_exact"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PY -m pytest tests/test_crm_source_mapping_auranotify.py -q`
Expected: FAIL — `ImportError: cannot import name 'method_options_for_source'`

- [ ] **Step 3: Write the implementation**

In `src/utils/crm_source_mapping_ui.py`, add the import and the new helper, keeping `MATCH_METHOD_OPTIONS` for backward compatibility:

```python
from shared.customer import match as alias_match

_METHOD_LABELS: dict[str, str] = {
    "contains": "Contains",
    "prefix": "Prefix",
    "suffix": "Suffix",
    "exact": "Exact",
    "id_exact": "ID exact",
}


def method_options_for_source(data_source: str) -> list[dict]:
    """Only the methods that mean something for this source.

    id_exact correlates by numeric tenant id, so it is meaningless on a
    name-matched source — offering it there produced rules that the SQL path
    dropped and the in-memory path read as `contains`.
    """
    return [
        {"label": _METHOD_LABELS[m], "value": m}
        for m in alias_match.allowed_methods(data_source)
    ]
```

In `src/pages/settings/integrations/crm_aliases.py`, replace the `data=` and `value=` arguments of `method_control` (:76-77) with:

```python
        data=method_options_for_source(_COLUMN_SOURCE_DEFAULTS.get(section_key, section_key)),
        value=alias_match.normalize_method(
            _COLUMN_SOURCE_DEFAULTS.get(section_key, section_key),
            entry.get("match_method") or "",
        ),
```

and add `from src.utils.crm_source_mapping_ui import method_options_for_source` plus `from shared.customer import match as alias_match` to its imports. Import `_COLUMN_SOURCE_DEFAULTS` from `src.utils.crm_source_mapping_ui` as well. Keep `disabled=is_auranotify` — auranotify still has exactly one legal method, so the select stays locked.

Find the API write path:

```bash
grep -rn "match_method" services/customer-api/app/routers/ | head
```

In whichever handler writes `gui_crm_customer_source_mapping`, reject the combination before the INSERT/UPDATE:

```python
from shared.customer import match as alias_match

if not alias_match.is_allowed(data_source, match_method):
    raise HTTPException(
        status_code=422,
        detail=(
            f"match_method '{match_method}' is not valid for data_source "
            f"'{data_source}'; allowed: {list(alias_match.allowed_methods(data_source))}"
        ),
    )
```

Create `services/customer-api/migrations/webui/028_source_mapping_method_check.sql`:

```sql
-- Reject match_method values that are meaningless for their data_source.
-- id_exact correlates by numeric tenant id: valid only for physical_device and
-- auranotify. On a name-matched source it produced a rule the SQL path dropped
-- and the in-memory classifier read as `contains`, hiding resources from both
-- the customer view and the Unmapped page.
--
-- NOT VALID: new and updated rows are checked immediately; pre-existing rows are
-- left alone so this migration cannot fail on live data. Clean the violators
-- listed by scripts/alias_match_impact_report.py, then run:
--     ALTER TABLE gui_crm_customer_source_mapping
--         VALIDATE CONSTRAINT chk_source_mapping_method_for_source;

ALTER TABLE gui_crm_customer_source_mapping
    DROP CONSTRAINT IF EXISTS chk_source_mapping_method_for_source;

ALTER TABLE gui_crm_customer_source_mapping
    ADD CONSTRAINT chk_source_mapping_method_for_source CHECK (
        CASE
            WHEN data_source IN ('physical_device', 'auranotify')
                THEN match_method = 'id_exact'
            ELSE match_method IN ('contains', 'prefix', 'suffix', 'exact')
        END
    ) NOT VALID;
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$PY -m pytest tests/test_crm_source_mapping_auranotify.py tests/test_crm_aliases_page.py tests/test_crm_internal_aliases_page.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/utils/crm_source_mapping_ui.py src/pages/settings/integrations/crm_aliases.py services/customer-api/app/routers/ services/customer-api/migrations/webui/028_source_mapping_method_check.sql tests/test_crm_source_mapping_auranotify.py
git commit -m "fix(match): reject id_exact on name sources at UI, API and DB

id_exact was offered for every column, unvalidated by the API and unconstrained
in the DB. Adds method_options_for_source, a 422 on the write path, and a
NOT VALID CHECK constraint."
```

---

### Task 8: Full-suite verification

**Files:** none — this task only runs things.

**Interfaces:**
- Consumes: everything above.
- Produces: a green suite, or a list of real regressions.

- [ ] **Step 1: Run each suite from its own directory**

The three cannot share one pytest run (see Global Constraints).

```bash
# root — the two known-broken files are excluded; they fail to collect at baseline
cd $W && $PY -m pytest tests/ -q \
  --ignore=tests/test_backup_sidebar_helpers.py \
  --ignore=tests/test_zabbix_query_deduplication.py

cd $W/services/customer-api && $PY -m pytest tests/ -q

cd $W/services/datacenter-api && PYTHONPATH=$W $PY -m pytest tests/ -q
```

Expected, compared against the baseline in Global Constraints:
- root: no new failures beyond the two excluded collection errors
- customer-api: 368 passed / 1 failed — same single pre-existing failure, nothing new
- datacenter-api: 230 passed / 2 failed / 29 skipped — same two pre-existing failures, nothing new

Any *additional* failure is yours. The pre-existing five are not.

- [ ] **Step 2: Confirm the four bugs are actually dead**

```bash
# 1. exact_by_source must be gone entirely
grep -rn "exact_by_source" --include="*.py" . | grep -v ".venv" || echo "OK: exact_by_source removed"

# 2. no hand-rolled match branches left outside the shared module
grep -rn 'method == "prefix"\|method == "suffix"\|kind == "prefix"' --include="*.py" . \
  | grep -v ".venv" | grep -v "shared/customer/match.py" || echo "OK: no duplicate implementations"

# 3. the re-deriving helper is gone
grep -rn "_normalize_ilike_pattern" --include="*.py" . | grep -v ".venv" || echo "OK: adapter no longer re-derives"
```

Expected: all three print their OK line.

- [ ] **Step 3: Re-run the impact report and compare**

```bash
$PY scripts/alias_match_impact_report.py
```

Expected: same counts as Task 2 — the report reads rules, not behaviour, so it must not have shifted. If `invalid` is still greater than zero, those rows need cleaning before the CHECK constraint is validated.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "test(match): full-suite verification for the alias match fix"
```

---

## What this plan deliberately does not do

- **It does not validate the CHECK constraint.** `NOT VALID` means live rows are untouched. Validating it is a follow-up once Task 2's `invalid` list is cleaned, so a migration can never fail on production data.
- **It does not touch `query-api`.** Its Dockerfile does not copy `shared/`, and it has no alias match code.
- **It does not restructure `dc_service.py`.** The file is ~7k lines and that is a real problem, but splitting it is unrelated to this fix.
- **It does not add tenant-id correlation to name sources.** That was the rejected "make id_exact meaningful everywhere" option.

