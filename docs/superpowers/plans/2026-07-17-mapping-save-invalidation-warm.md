# Mapping Save Invalidation + Warm Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a saved customer alias source-mapping take effect immediately instead of staying invisible for up to ~24h, by invalidating the resolved resource cache on every mapping write and warming the affected customer in the background.

**Architecture:** One new pure module, `app/services/mapping_cache_invalidator.py`, owns the invalidation decision: it parses `customer_assets:*` keys with a tail-anchored regex, resolves each key's customer name to a CRM account id **using the read path's own resolver**, and deletes the keys whose account matches. Because the same resolver decides both "which rules build this view" and "which keys this account owns", the two can never drift. All I/O (Redis scan/delete, name resolution) is injected, so the module is testable with no Redis and no DB. `CustomerService` binds it to the real resolver and cache; `SalesService` calls it through an injected callable from `main.py` — the existing `get_customer_assets` wiring pattern — so no circular import appears.

**Tech Stack:** Python 3.11, pytest, Redis (redis-py), FastAPI, psycopg2, Dash/Mantine UI.

## Global Constraints

- Worktree root: `/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI/.claude/worktrees/mapping-cache-invalidation`. Branch: `worktree-mapping-cache-invalidation`. Base: `origin/main` @ `3de24d83`. All paths below are relative to the worktree root.
- **Python interpreter for every command: `../../../.venv/bin/python`** (the main checkout's venv, Python 3.11.15). System `python3` is 3.9 and fails on `X | None` syntax. There is no `.venv` inside the worktree — this is expected, do not create one.
- Run tests from the worktree root. Both suites work from there: `../../../.venv/bin/python -m pytest services/customer-api/tests/... -q` and `../../../.venv/bin/python -m pytest tests/... -q`.
- **Pre-existing baseline:** `pytest --collect-only` reports **21 collection errors** on this base. They exist identically on `main` and are NOT your problem. Do not fix them. Do not let them block you. Verify your own test files run clean.
- All line numbers cited below are against base `3de24d83`. If a line has moved, find the symbol by name rather than trusting the number.
- `shared/` is importable from every service: each Dockerfile does `COPY shared/ ./shared/`, and `services/customer-api/tests/conftest.py` appends the GUI root to `sys.path`. Do not duplicate code into a service.
- Code and comments in English (matches the codebase). Turkish is fine in commit messages.
- **Never hardcode the cache version token.** `CUSTOMER_ASSETS_CACHE_VERSION` is `cpu-usage-v3` on this base but is being changed to `netbackup-policy-v4` by parallel in-flight work. Match it with `[^:]+`.
- **Out of scope — do not touch:** the `last_good` read-through root cause in `cache_backend.cache_run_singleflight`; the hardcoded `WARMED_CUSTOMERS = ("Boyner",)` in `src/services/db_service.py:45`; `sql_pattern_for_match`, `ResolvedSourcePatterns` and `build_resolved_patterns` in `customer_mapping_resolver.py` (`:95-186`) — the parallel `customer-alias-matching` plan rewrites those, so stay off them. Task 12 touches only `DATA_SOURCES` (`:10-20`) in that same file, which that plan never mentions.

## Product decisions (already made — do not re-litigate)

1. **Targeted, not global.** 352 customers exist and 0 mappings are configured yet, so a rollout will save hundreds of mappings back to back. Nuking all of `customer_assets:` on each save would keep the whole system cold for the entire rollout.
2. **Resolve names from the cache, never enumerate them.** A single account is cached under multiple display names (`Boyner` and `BOYNER BÜYÜK MAĞAZACILIK A.Ş.` both exist live), and `Boyner` is not derivable from the alias table. Any name-list approach silently misses keys.
3. **Invalidation failure warns, it does not 500.** The DB commit already happened, so raising would report "failed" about a mapping that was saved. Silently succeeding is the bug being fixed.
4. **Backend targeted, GUI blunt.** Rebuilding a backend key costs a DB query; rebuilding a GUI key costs an HTTP call to an already-warm backend.
5. **Version-agnostic prefixes everywhere.** Both `customer_assets:` and `api:customer_resources:` are scanned/deleted without the version token.

## Background: what is broken

Measured on the live dev Redis (DB 1) on 2026-07-16:

| Evidence | Meaning |
|---|---|
| 11 `customer_assets:*` keys: 3 primary, 8 `:last_good`. **5 are zombies** (primary gone, shadow alive ~18h) | `cache_get` (`app/core/cache_backend.py:107-112`) falls back to the shadow, so `cache_run_singleflight` (`:219-222`) returns it and the factory never runs. The scheduled warm jobs are therefore no-ops. |
| `customer_assets:cpu-usage-v3:Boyner:…` **and** `customer_assets:cpu-usage-v3:BOYNER BÜYÜK MAĞAZACILIK A.Ş.:…` both live | One account, two display names. `Boyner` comes from the hardcoded `WARMED_CUSTOMERS` in `src/services/db_service.py:45`, not from the alias table (its `canonical_customer_key` is null). |
| `save_source_mappings` deletes only `ALIASES_SNAPSHOT_KEY` + `CATALOG_SNAPSHOT_KEY` (`sales_service.py:686-687`) | The resolved-resource cache (`customer_assets:*`) is never touched. |

## File Structure

| File | Responsibility |
|---|---|
| **Create** `services/customer-api/app/services/mapping_cache_invalidator.py` | Pure invalidation logic: key parsing + account matching. All I/O injected. No Redis, no DB, no FastAPI imports. |
| **Create** `services/customer-api/app/services/mapping_warm_scheduler.py` | Debounced background warm scheduling. Timer + dict, no business logic. |
| **Modify** `services/customer-api/app/services/webui_db.py` | Add `execute_all` — multiple statements, one transaction, one commit. |
| **Modify** `services/customer-api/app/services/customer_service.py` | Add `resolve_account_id_strict` (non-swallowing) and `invalidate_mapping_caches` — binds the pure invalidator to the real resolver/cache and triggers the warm. |
| **Modify** `services/customer-api/app/services/sales_service.py` | Call the injected invalidator from all 5 write paths; make `save_source_mappings` atomic. |
| **Modify** `services/customer-api/app/main.py` | Inject `invalidate_mapping_caches` into `SalesService`. |
| **Modify** `services/customer-api/app/routers/sales.py` | Widen the save response to `{mappings, cache_warning}`. |
| **Modify** `src/services/api_client.py` | Clear the GUI's own namespace on mapping writes; adapt to the new response shape. |
| **Modify** `src/pages/settings/integrations/crm_aliases_callbacks.py` | Surface `cache_warning` to the user. |

---

### Task 1: Cache key parser

**Files:**
- Create: `services/customer-api/app/services/mapping_cache_invalidator.py`
- Test: `services/customer-api/tests/test_mapping_cache_invalidator.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ParsedKey` (frozen dataclass with fields `version: str`, `name: str`, `start: str`, `end: str`, `is_shadow: bool`) and `parse_customer_assets_key(key: str) -> ParsedKey | None`. Task 2 depends on both.

Why a regex and not `split(":")`: customer names contain spaces, dots and Turkish characters (`BOYNER BÜYÜK MAĞAZACILIK A.Ş.`), and the `1h` preset embeds a timestamp that itself contains colons (`Boyner:2026-07-16T13:54:18Z:2026-07-16T14:54:18Z`). Anchoring the two date fields at the tail makes the name unambiguous even when it contains colons.

- [ ] **Step 1: Write the failing test**

Create `services/customer-api/tests/test_mapping_cache_invalidator.py`:

```python
import pytest

from app.services.mapping_cache_invalidator import parse_customer_assets_key


@pytest.mark.parametrize(
    "key,version,name,is_shadow",
    [
        (
            "customer_assets:cpu-usage-v3:Boyner:2026-07-09:2026-07-16",
            "cpu-usage-v3",
            "Boyner",
            False,
        ),
        (
            "customer_assets:cpu-usage-v3:Boyner:2026-07-09:2026-07-16:last_good",
            "cpu-usage-v3",
            "Boyner",
            True,
        ),
        # Version token must not be pinned: a bump is already in flight.
        (
            "customer_assets:netbackup-policy-v4:Boyner:2026-07-09:2026-07-16",
            "netbackup-policy-v4",
            "Boyner",
            False,
        ),
        # Spaces, dots, Turkish characters.
        (
            "customer_assets:cpu-usage-v3:BOYNER BÜYÜK MAĞAZACILIK A.Ş.:2026-07-10:2026-07-16",
            "cpu-usage-v3",
            "BOYNER BÜYÜK MAĞAZACILIK A.Ş.",
            False,
        ),
        # 1h preset: timestamps contain colons, so split(":") cannot work here.
        (
            "customer_assets:cpu-usage-v3:Boyner:2026-07-16T13:54:18Z:2026-07-16T14:54:18Z",
            "cpu-usage-v3",
            "Boyner",
            False,
        ),
        # Name itself contains colons.
        (
            "customer_assets:cpu-usage-v3:Weird:Name:2026-07-09:2026-07-16",
            "cpu-usage-v3",
            "Weird:Name",
            False,
        ),
    ],
)
def test_parses_real_key_shapes(key, version, name, is_shadow):
    parsed = parse_customer_assets_key(key)
    assert parsed is not None
    assert parsed.version == version
    assert parsed.name == name
    assert parsed.is_shadow is is_shadow


def test_captures_date_bounds():
    parsed = parse_customer_assets_key(
        "customer_assets:cpu-usage-v3:Boyner:2026-07-09:2026-07-16"
    )
    assert parsed.start == "2026-07-09"
    assert parsed.end == "2026-07-16"


@pytest.mark.parametrize(
    "key",
    [
        "unmapped_resources:2026-07-09:2026-07-16",
        "customer_assets:cpu-usage-v3:Boyner:not-a-date:2026-07-16",
        "api:customer_resources:cpu-usage-v3:Boyner:x",
        "customer_assets:cpu-usage-v3:Boyner",
        "",
    ],
)
def test_rejects_foreign_keys(key):
    assert parse_customer_assets_key(key) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `../../../.venv/bin/python -m pytest services/customer-api/tests/test_mapping_cache_invalidator.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.mapping_cache_invalidator'`

- [ ] **Step 3: Write minimal implementation**

Create `services/customer-api/app/services/mapping_cache_invalidator.py`:

```python
"""Pure mapping-cache invalidation logic.

Deliberately free of Redis, DB and FastAPI imports: every side effect is
injected, so this module is unit-testable on its own. See
docs/superpowers/specs/2026-07-17-mapping-save-invalidation-warm-design.md.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Key shape: customer_assets:{version}:{name}:{start}:{end}[:last_good]
#
# The name is matched greedily and the two date fields are anchored to the tail,
# because names legitimately contain colons (and spaces, dots, Turkish chars),
# and the 1h preset's timestamps contain colons too. split(":") cannot do this.
#
# The version is matched as [^:]+ rather than pinned to
# CUSTOMER_ASSETS_CACHE_VERSION: a bump to netbackup-policy-v4 is already in
# flight, and pinning would make invalidation silently match nothing after it
# lands — reintroducing the exact bug this module fixes. Matching any version
# also cleans up orphaned keys left behind by a bump.
_DATE = r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}Z)?"
KEY_RE = re.compile(
    r"^customer_assets:"
    r"(?P<version>[^:]+):"
    r"(?P<name>.+):"
    rf"(?P<start>{_DATE}):"
    rf"(?P<end>{_DATE})"
    r"(?P<shadow>:last_good)?$"
)

CUSTOMER_ASSETS_SCAN_PREFIX = "customer_assets:"


@dataclass(frozen=True)
class ParsedKey:
    version: str
    name: str
    start: str
    end: str
    is_shadow: bool


def parse_customer_assets_key(key: str) -> ParsedKey | None:
    """Split a customer_assets cache key, or return None if it is not one."""
    if not key:
        return None
    match = KEY_RE.match(key)
    if not match:
        return None
    return ParsedKey(
        version=match.group("version"),
        name=match.group("name"),
        start=match.group("start"),
        end=match.group("end"),
        is_shadow=bool(match.group("shadow")),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `../../../.venv/bin/python -m pytest services/customer-api/tests/test_mapping_cache_invalidator.py -q`
Expected: PASS — 8 passed

- [ ] **Step 5: Commit**

```bash
git add services/customer-api/app/services/mapping_cache_invalidator.py services/customer-api/tests/test_mapping_cache_invalidator.py
git commit -m "feat(cache): parse customer_assets keys without pinning the version"
```

---

### Task 2: Invalidation core

**Files:**
- Modify: `services/customer-api/app/services/mapping_cache_invalidator.py`
- Test: `services/customer-api/tests/test_mapping_cache_invalidator.py` (append)

**Interfaces:**
- Consumes: `ParsedKey`, `parse_customer_assets_key`, `CUSTOMER_ASSETS_SCAN_PREFIX` from Task 1.
- Produces:
  - `class ResolutionError(Exception)` — raised by a caller's resolver when it cannot tell.
  - `InvalidationResult` (frozen dataclass: `deleted_count: int`, `matched_names: tuple[str, ...]`, `scanned_count: int`).
  - `invalidate_for_accounts(account_ids: set[str], *, resolve_account_id: Callable[[str], str | None], scan_keys: Callable[[str], Iterable[str]], delete_keys: Callable[[list[str]], None]) -> InvalidationResult`.

  Task 5 calls `invalidate_for_accounts` and catches `ResolutionError`.

The resolver contract is the crux. `resolve_account_id(name)` returns the account id, or `None` meaning *"this name belongs to no account"* — a clean answer. It must raise `ResolutionError` when it **could not determine** the answer. Those two cases must never collapse into one: today's `_lookup_alias_for_display_name` swallows exceptions and returns `None`, so a transient DB hiccup would look like "belongs to nobody", the key would be skipped, and the mapping would stay stale forever — the same bug in a new costume.

- [ ] **Step 1: Write the failing test**

Append to `services/customer-api/tests/test_mapping_cache_invalidator.py`:

```python
from app.services.mapping_cache_invalidator import (
    ResolutionError,
    invalidate_for_accounts,
)

ACCT_A = "aaaa-1111"
ACCT_B = "bbbb-2222"

# One account, two display names — this is real: "Boyner" (hardcoded pilot name)
# and the CRM legal name both hold live cache entries for the same account.
NAME_TO_ACCOUNT = {
    "Boyner": ACCT_A,
    "BOYNER BÜYÜK MAĞAZACILIK A.Ş.": ACCT_A,
    "4A KOZMETİK SANAYİ VE TİCARET ANONİM ŞİRKETİ": ACCT_B,
}

KEYS = [
    "customer_assets:cpu-usage-v3:Boyner:2026-07-09:2026-07-16",
    "customer_assets:cpu-usage-v3:Boyner:2026-07-09:2026-07-16:last_good",
    "customer_assets:cpu-usage-v3:BOYNER BÜYÜK MAĞAZACILIK A.Ş.:2026-07-10:2026-07-16",
    "customer_assets:cpu-usage-v3:4A KOZMETİK SANAYİ VE TİCARET ANONİM ŞİRKETİ:2026-07-09:2026-07-16",
    "some_other_namespace:junk",
]


def _fakes(keys=None, resolver=None):
    deleted: list[str] = []

    def scan_keys(prefix):
        return [k for k in (KEYS if keys is None else keys) if k.startswith(prefix)]

    def delete_keys(batch):
        deleted.extend(batch)

    def default_resolver(name):
        return NAME_TO_ACCOUNT.get(name)

    return deleted, scan_keys, delete_keys, (resolver or default_resolver)


def test_deletes_every_name_belonging_to_the_account():
    deleted, scan_keys, delete_keys, resolver = _fakes()

    result = invalidate_for_accounts(
        {ACCT_A},
        resolve_account_id=resolver,
        scan_keys=scan_keys,
        delete_keys=delete_keys,
    )

    # Both display names of account A, primary and shadow alike.
    assert set(deleted) == {
        "customer_assets:cpu-usage-v3:Boyner:2026-07-09:2026-07-16",
        "customer_assets:cpu-usage-v3:Boyner:2026-07-09:2026-07-16:last_good",
        "customer_assets:cpu-usage-v3:BOYNER BÜYÜK MAĞAZACILIK A.Ş.:2026-07-10:2026-07-16",
    }
    assert result.deleted_count == 3
    assert set(result.matched_names) == {"Boyner", "BOYNER BÜYÜK MAĞAZACILIK A.Ş."}


def test_leaves_other_accounts_untouched():
    deleted, scan_keys, delete_keys, resolver = _fakes()

    invalidate_for_accounts(
        {ACCT_A},
        resolve_account_id=resolver,
        scan_keys=scan_keys,
        delete_keys=delete_keys,
    )

    assert not any("4A KOZMETİK" in k for k in deleted)


def test_shadow_is_deleted_with_its_primary():
    # A surviving :last_good shadow is exactly what makes a mapping change
    # invisible: cache_get falls back to it and the factory never re-runs.
    deleted, scan_keys, delete_keys, resolver = _fakes()

    invalidate_for_accounts(
        {ACCT_A},
        resolve_account_id=resolver,
        scan_keys=scan_keys,
        delete_keys=delete_keys,
    )

    assert "customer_assets:cpu-usage-v3:Boyner:2026-07-09:2026-07-16:last_good" in deleted


def test_unknown_name_is_skipped_not_fatal():
    keys = ["customer_assets:cpu-usage-v3:Ghost Corp:2026-07-09:2026-07-16"]
    deleted, scan_keys, delete_keys, resolver = _fakes(keys=keys)

    result = invalidate_for_accounts(
        {ACCT_A},
        resolve_account_id=resolver,
        scan_keys=scan_keys,
        delete_keys=delete_keys,
    )

    # Resolving to None is a clean answer: the read path would also find no
    # rules for it, so this account's mapping cannot affect that view.
    assert deleted == []
    assert result.deleted_count == 0


def test_resolver_failure_aborts_instead_of_skipping():
    def exploding_resolver(name):
        raise ResolutionError("webui pool down")

    deleted, scan_keys, delete_keys, _ = _fakes()

    with pytest.raises(ResolutionError):
        invalidate_for_accounts(
            {ACCT_A},
            resolve_account_id=exploding_resolver,
            scan_keys=scan_keys,
            delete_keys=delete_keys,
        )

    assert deleted == []


def test_resolves_each_distinct_name_once():
    calls: list[str] = []

    def counting_resolver(name):
        calls.append(name)
        return NAME_TO_ACCOUNT.get(name)

    _, scan_keys, delete_keys, _ = _fakes()

    invalidate_for_accounts(
        {ACCT_A},
        resolve_account_id=counting_resolver,
        scan_keys=scan_keys,
        delete_keys=delete_keys,
    )

    # "Boyner" appears in two keys but must cost one lookup.
    assert calls.count("Boyner") == 1


def test_no_matching_keys_reports_zero():
    deleted, scan_keys, delete_keys, resolver = _fakes(keys=["junk:key"])

    result = invalidate_for_accounts(
        {ACCT_A},
        resolve_account_id=resolver,
        scan_keys=scan_keys,
        delete_keys=delete_keys,
    )

    assert result.deleted_count == 0
    assert result.matched_names == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `../../../.venv/bin/python -m pytest services/customer-api/tests/test_mapping_cache_invalidator.py -q`
Expected: FAIL — `ImportError: cannot import name 'ResolutionError'`

- [ ] **Step 3: Write minimal implementation**

Append to `services/customer-api/app/services/mapping_cache_invalidator.py`:

```python
from typing import Callable, Iterable


class ResolutionError(Exception):
    """A display name could not be resolved to an account.

    Distinct from resolving to None. None means "this name belongs to no
    account" — a clean answer we can act on. This exception means "we could not
    tell", and we must never treat that as None: skipping a key we were unsure
    about is precisely how a mapping stays silently stale.
    """


@dataclass(frozen=True)
class InvalidationResult:
    deleted_count: int
    matched_names: tuple[str, ...]
    scanned_count: int


def invalidate_for_accounts(
    account_ids: set[str],
    *,
    resolve_account_id: Callable[[str], str | None],
    scan_keys: Callable[[str], Iterable[str]],
    delete_keys: Callable[[list[str]], None],
) -> InvalidationResult:
    """Delete every customer_assets key owned by any of account_ids.

    Names are read out of the cache and resolved with the read path's own
    resolver, so "which keys does this account own" is answered by the same code
    that answers "which rules build this view". They cannot drift apart.

    Raises ResolutionError if any name cannot be resolved.
    """
    if not account_ids:
        return InvalidationResult(deleted_count=0, matched_names=(), scanned_count=0)

    targets = {a for a in account_ids if a}
    resolved: dict[str, str | None] = {}
    doomed: list[str] = []
    matched: list[str] = []
    scanned = 0

    for key in scan_keys(CUSTOMER_ASSETS_SCAN_PREFIX):
        scanned += 1
        parsed = parse_customer_assets_key(key)
        if parsed is None:
            continue
        name = parsed.name
        if name not in resolved:
            resolved[name] = resolve_account_id(name)  # may raise ResolutionError
        account_id = resolved[name]
        if account_id is not None and account_id in targets:
            doomed.append(key)
            if name not in matched:
                matched.append(name)

    if doomed:
        delete_keys(doomed)

    return InvalidationResult(
        deleted_count=len(doomed),
        matched_names=tuple(matched),
        scanned_count=scanned,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `../../../.venv/bin/python -m pytest services/customer-api/tests/test_mapping_cache_invalidator.py -q`
Expected: PASS — 15 passed

- [ ] **Step 5: Commit**

```bash
git add services/customer-api/app/services/mapping_cache_invalidator.py services/customer-api/tests/test_mapping_cache_invalidator.py
git commit -m "feat(cache): invalidate customer_assets keys by resolved account"
```

---

### Task 3: One-transaction multi-statement execute

**Files:**
- Modify: `services/customer-api/app/services/webui_db.py` (add after `execute_batch`, which ends at `:124`)
- Test: `services/customer-api/tests/test_webui_db_execute_all.py`

**Interfaces:**
- Consumes: `WebuiPool._get_connection` (the existing `@contextmanager` at `webui_db.py:74`).
- Produces: `WebuiPool.execute_all(statements: Iterable[tuple[str, Iterable[Any] | None]]) -> int`. Task 4 uses it.

Today `execute` commits per statement (`webui_db.py:105-111`). `save_source_mappings` runs `DELETE` then a loop of `UPSERT`s through it, so the `DELETE` is already committed when the loop raises — the account's mappings end up deleted but not rewritten. `execute_batch` (`:113`) cannot help: it runs one statement over many parameter sets, not two different statements.

Atomicity holds because psycopg2's pool rolls back a non-idle transaction when `putconn` returns the connection, and `_get_connection` returns it in a `finally`.

- [ ] **Step 1: Write the failing test**

Create `services/customer-api/tests/test_webui_db_execute_all.py`:

```python
from contextlib import contextmanager
from unittest.mock import MagicMock

from app.services.webui_db import WebuiPool


def _pool_with_fake_conn(conn):
    pool = WebuiPool.__new__(WebuiPool)  # bypass __init__ / real pool creation

    @contextmanager
    def fake_get_connection():
        yield conn

    pool._get_connection = fake_get_connection
    return pool


def _fake_conn():
    conn = MagicMock()
    cur = MagicMock()
    cur.rowcount = 1
    conn.cursor.return_value.__enter__.return_value = cur
    return conn, cur


def test_runs_every_statement_on_one_connection():
    conn, cur = _fake_conn()
    pool = _pool_with_fake_conn(conn)

    total = pool.execute_all([("DELETE FROM t WHERE a=%s", ("x",)), ("INSERT INTO t VALUES (%s)", ("y",))])

    assert cur.execute.call_count == 2
    assert total == 2


def test_commits_once_at_the_end_not_per_statement():
    conn, _ = _fake_conn()
    pool = _pool_with_fake_conn(conn)

    pool.execute_all([("DELETE FROM t", None), ("INSERT INTO t VALUES (1)", None)])

    # One commit for the whole batch — this is what makes it atomic.
    assert conn.commit.call_count == 1


def test_does_not_commit_when_a_statement_raises():
    conn, cur = _fake_conn()
    cur.execute.side_effect = [None, RuntimeError("boom")]
    pool = _pool_with_fake_conn(conn)

    try:
        pool.execute_all([("DELETE FROM t", None), ("INSERT INTO t VALUES (1)", None)])
    except RuntimeError:
        pass

    # No commit -> the pool rolls the whole thing back on putconn.
    assert conn.commit.call_count == 0


def test_empty_statement_list_is_a_noop():
    conn, _ = _fake_conn()
    pool = _pool_with_fake_conn(conn)

    assert pool.execute_all([]) == 0
    assert conn.commit.call_count == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `../../../.venv/bin/python -m pytest services/customer-api/tests/test_webui_db_execute_all.py -q`
Expected: FAIL — `AttributeError: 'WebuiPool' object has no attribute 'execute_all'`

- [ ] **Step 3: Write minimal implementation**

Add to `services/customer-api/app/services/webui_db.py`, immediately after `execute_batch`:

```python
    def execute_all(self, statements: Iterable[tuple[str, Iterable[Any] | None]]) -> int:
        """Execute several different statements in ONE transaction.

        `execute` commits per statement and `execute_batch` runs a single
        statement over many params; neither can make a DELETE + INSERT pair
        atomic. On exception we never commit, and the pool rolls the connection
        back when `_get_connection` returns it.
        """
        stmts = list(statements)
        if not stmts:
            return 0
        total = 0
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                for sql, params in stmts:
                    cur.execute(sql, params)
                    total += int(cur.rowcount or 0)
            conn.commit()
        return total
```

- [ ] **Step 4: Run test to verify it passes**

Run: `../../../.venv/bin/python -m pytest services/customer-api/tests/test_webui_db_execute_all.py -q`
Expected: PASS — 4 passed

- [ ] **Step 5: Commit**

```bash
git add services/customer-api/app/services/webui_db.py services/customer-api/tests/test_webui_db_execute_all.py
git commit -m "feat(webui-db): execute_all runs multiple statements in one transaction"
```

---

### Task 4: Make save_source_mappings atomic

**Files:**
- Modify: `services/customer-api/app/services/sales_service.py:659-684`
- Test: `services/customer-api/tests/test_save_source_mappings_atomic.py`

**Interfaces:**
- Consumes: `WebuiPool.execute_all` from Task 3.
- Produces: no new symbols; `save_source_mappings` keeps its current signature and return type for now (Task 8 changes the return).

- [ ] **Step 1: Write the failing test**

Create `services/customer-api/tests/test_save_source_mappings_atomic.py`:

```python
from unittest.mock import MagicMock

import pytest

from app.services.sales_service import SalesService


def _service(webui):
    svc = SalesService.__new__(SalesService)
    svc._webui = webui
    svc._invalidate_mapping_caches = None
    svc.list_source_mappings_for_account = lambda account_id: []
    return svc


def test_delete_and_upserts_go_through_one_transaction():
    webui = MagicMock()
    svc = _service(webui)

    svc.save_source_mappings(
        "acct-1",
        crm_account_name="Acme",
        mappings=[
            {"data_source": "virtualization", "match_method": "contains", "match_value": "acme"},
        ],
    )

    # One execute_all call carrying DELETE + UPSERT, not two separate commits.
    webui.execute_all.assert_called_once()
    statements = list(webui.execute_all.call_args[0][0])
    assert len(statements) == 2
    webui.execute.assert_not_called()


def test_bad_data_source_writes_nothing_at_all():
    webui = MagicMock()
    svc = _service(webui)

    with pytest.raises(ValueError, match="Unsupported data_source"):
        svc.save_source_mappings(
            "acct-1",
            crm_account_name="Acme",
            mappings=[{"data_source": "nope", "match_method": "contains", "match_value": "x"}],
        )

    # The DELETE must not have been committed on its own.
    webui.execute_all.assert_not_called()
    webui.execute.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `../../../.venv/bin/python -m pytest services/customer-api/tests/test_save_source_mappings_atomic.py -q`
Expected: FAIL — `execute_all.assert_called_once()` fails (still uses `execute`), and the second test fails because the DELETE already ran.

- [ ] **Step 3: Write minimal implementation**

Replace `services/customer-api/app/services/sales_service.py:659-684` (from the `self._webui.execute(smq.DELETE_SOURCE_MAPPINGS_FOR_ACCOUNT, ...)` line through the end of the `for` loop) with:

```python
        statements: list[tuple[str, tuple[Any, ...]]] = [
            (smq.DELETE_SOURCE_MAPPINGS_FOR_ACCOUNT, (crm_accountid,))
        ]
        for entry in mappings or []:
            data_source = str(entry.get("data_source") or "").strip()
            match_method = str(entry.get("match_method") or "").strip()
            match_value = str(entry.get("match_value") or "").strip()
            if not data_source or not match_method or not match_value:
                continue
            if data_source not in allowed_sources:
                raise ValueError(f"Unsupported data_source: {data_source}")
            if match_method not in allowed_methods:
                raise ValueError(f"Unsupported match_method: {match_method}")
            statements.append(
                (
                    smq.UPSERT_SOURCE_MAPPING,
                    (
                        crm_accountid,
                        cleaned_name,
                        data_source,
                        match_method,
                        match_value,
                        entry.get("display_label"),
                        int(entry.get("priority") or 100),
                        bool(entry.get("enabled", True)),
                        entry.get("notes") or notes,
                        "manual",
                    ),
                )
            )
        # Validation happens while building, so a bad row aborts before the
        # DELETE is ever sent — previously the DELETE was already committed.
        self._webui.execute_all(statements)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `../../../.venv/bin/python -m pytest services/customer-api/tests/test_save_source_mappings_atomic.py -q`
Expected: PASS — 2 passed

- [ ] **Step 5: Commit**

```bash
git add services/customer-api/app/services/sales_service.py services/customer-api/tests/test_save_source_mappings_atomic.py
git commit -m "fix(crm): make save_source_mappings atomic"
```

---

### Task 5: Strict resolver + CustomerService.invalidate_mapping_caches

**Files:**
- Modify: `services/customer-api/app/services/customer_service.py` (add after `resolve_source_patterns`, which ends at `:790`)
- Test: `services/customer-api/tests/test_customer_service_invalidate_mapping.py`

**Interfaces:**
- Consumes: `invalidate_for_accounts`, `ResolutionError`, `InvalidationResult` (Task 2); the existing `_lookup_alias_for_display_name` (`customer_service.py:726`) and `cache_service` wrapper (`app.services.cache_service`, which exposes `delete_prefix` at `:41`).
- Produces: `CustomerService.resolve_account_id_strict(display_name: str) -> str | None` (raises `ResolutionError`) and `CustomerService.invalidate_mapping_caches(account_ids: set[str]) -> str | None` — returns `None` on success, or a user-facing Turkish warning string on failure. Tasks 6 and 7 use `invalidate_mapping_caches`.

`unmapped_resources:*` is dropped globally, not per account: that view is the complement of every mapping, so any mapping write changes it.

- [ ] **Step 1: Write the failing test**

Create `services/customer-api/tests/test_customer_service_invalidate_mapping.py`:

```python
from unittest.mock import MagicMock, patch

import pytest

from app.services.customer_service import CustomerService
from app.services.mapping_cache_invalidator import ResolutionError


def _svc():
    svc = CustomerService.__new__(CustomerService)
    svc._webui = MagicMock()
    return svc


def test_strict_resolver_raises_instead_of_swallowing():
    svc = _svc()
    with patch.object(
        CustomerService, "_lookup_alias_for_display_name", side_effect=RuntimeError("db down")
    ):
        with pytest.raises(ResolutionError):
            svc.resolve_account_id_strict("Boyner")


def test_strict_resolver_returns_none_for_unknown_name():
    svc = _svc()
    with patch.object(
        CustomerService, "_lookup_alias_for_display_name", return_value=(None, None, None)
    ):
        assert svc.resolve_account_id_strict("Ghost Corp") is None


def test_invalidate_drops_unmapped_resources_too():
    svc = _svc()
    with patch("app.services.customer_service.cache") as cache, patch(
        "app.services.customer_service.invalidate_for_accounts"
    ) as inv, patch.object(CustomerService, "_schedule_mapping_warm"):
        inv.return_value = MagicMock(deleted_count=2, matched_names=("Boyner",), scanned_count=9)
        warning = svc.invalidate_mapping_caches({"acct-1"})

    assert warning is None
    cache.delete_prefix.assert_any_call("unmapped_resources:")


def test_invalidate_returns_warning_when_cache_fails():
    svc = _svc()
    with patch("app.services.customer_service.cache"), patch(
        "app.services.customer_service.invalidate_for_accounts",
        side_effect=ResolutionError("webui down"),
    ), patch.object(CustomerService, "_schedule_mapping_warm"):
        warning = svc.invalidate_mapping_caches({"acct-1"})

    # A warning string, not an exception: the DB write already committed.
    assert warning is not None
    assert "cache" in warning.lower()


def test_invalidate_warms_the_matched_names():
    svc = _svc()
    with patch("app.services.customer_service.cache"), patch(
        "app.services.customer_service.invalidate_for_accounts"
    ) as inv, patch.object(CustomerService, "_schedule_mapping_warm") as warm:
        inv.return_value = MagicMock(
            deleted_count=2, matched_names=("Boyner", "BOYNER A.Ş."), scanned_count=9
        )
        svc.invalidate_mapping_caches({"acct-1"})

    warm.assert_called_once_with(("Boyner", "BOYNER A.Ş."))


def test_invalidate_with_no_accounts_is_a_noop():
    svc = _svc()
    with patch("app.services.customer_service.cache"), patch(
        "app.services.customer_service.invalidate_for_accounts"
    ) as inv:
        assert svc.invalidate_mapping_caches(set()) is None
        inv.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `../../../.venv/bin/python -m pytest services/customer-api/tests/test_customer_service_invalidate_mapping.py -q`
Expected: FAIL — `AttributeError: 'CustomerService' object has no attribute 'resolve_account_id_strict'`

- [ ] **Step 3: Write minimal implementation**

Add to `services/customer-api/app/services/customer_service.py` imports (near the other `app.services` imports at the top):

```python
from app.services.mapping_cache_invalidator import (
    ResolutionError,
    invalidate_for_accounts,
)
```

(`CUSTOMER_ASSETS_SCAN_PREFIX` is not imported here — `invalidate_for_accounts` passes it to the injected `scan_keys` itself.)

Add these methods to `CustomerService`, right after `resolve_source_patterns`:

```python
    # CORRECTION (found in review, after this plan was written): the snippet below
    # is WRONG as originally drafted and must not be copied verbatim. Wrapping
    # _lookup_alias_for_display_name in try/except accomplishes nothing — that method
    # swallows its own exceptions and returns (None, None, None), so the guard can never
    # fire. Extract a raising core (_lookup_alias_for_display_name_raising) holding the
    # body verbatim, leave _lookup_alias_for_display_name as a thin swallowing wrapper for
    # existing callers, call the raising core here, and ALSO raise when webui is
    # unavailable — that is "cannot tell", not "belongs to nobody". See commit a56107e5.
    def resolve_account_id_strict(self, display_name: str) -> str | None:
        """Resolve a display name to a CRM account id, or raise if we cannot tell.

        _lookup_alias_for_display_name swallows exceptions and returns
        (None, None, None), which conflates "belongs to nobody" with "lookup
        failed". Invalidation must not act on that ambiguity: skipping a key we
        were unsure about leaves it silently stale.
        """
        try:
            _netbox_value, _canonical_key, account_id = self._lookup_alias_for_display_name(
                display_name
            )
        except Exception as exc:  # noqa: BLE001
            raise ResolutionError(f"Could not resolve display name {display_name!r}") from exc
        return account_id

    def _scan_cache_keys(self, prefix: str) -> list[str]:
        return cache.scan_prefix(prefix)

    def _delete_cache_keys(self, keys: list[str]) -> None:
        for key in keys:
            cache.delete(key)

    def invalidate_mapping_caches(self, account_ids: set[str]) -> str | None:
        """Drop every cached view affected by a mapping change for these accounts.

        Returns None on success, or a user-facing warning when the cache could
        not be cleared. It never raises: the DB write has already committed by
        the time this runs, so failing the request would report "not saved"
        about a mapping that was in fact saved.
        """
        targets = {a for a in account_ids if a}
        if not targets:
            return None
        try:
            result = invalidate_for_accounts(
                targets,
                resolve_account_id=self.resolve_account_id_strict,
                scan_keys=self._scan_cache_keys,
                delete_keys=self._delete_cache_keys,
            )
            # The unmapped view is the complement of every mapping, so any
            # mapping write changes it regardless of which account moved.
            cache.delete_prefix("unmapped_resources:")
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Mapping cache invalidation failed for accounts=%s: %s",
                sorted(targets),
                exc,
            )
            return "Mapping kaydedildi, ancak cache temizlenemedi — lütfen tekrar kaydedin."

        if result.deleted_count == 0:
            # Not necessarily a bug (the customer may never have been viewed),
            # but a silent miss looks identical to success, so say so out loud.
            logger.warning(
                "Mapping cache invalidation deleted nothing for accounts=%s (scanned=%d)",
                sorted(targets),
                result.scanned_count,
            )
        else:
            logger.info(
                "Mapping cache invalidation deleted %d keys for names=%s",
                result.deleted_count,
                list(result.matched_names),
            )

        if result.matched_names:
            self._schedule_mapping_warm(result.matched_names)
        return None
```

`cache.scan_prefix` does not exist yet. `services/customer-api/app/services/cache_service.py` imports backend functions by name (`from app.core.cache_backend import cache_get, cache_set, ...` at `:4-14`), not as a module — so add `cache_scan_prefix` to that import list:

```python
from app.core.cache_backend import (
    cache_get,
    cache_get_last_good,
    cache_get_stale,
    cache_set,
    cache_delete,
    cache_delete_prefix,
    cache_flush_pattern,
    cache_run_singleflight,
    cache_scan_prefix,
    cache_stats as _backend_stats,
)
```

and add the wrapper after `delete_prefix` (`:41-43`), matching the surrounding style:

```python
def scan_prefix(prefix: str) -> list[str]:
    """Return every cache key starting with prefix."""
    return cache_scan_prefix(prefix)
```

and to `services/customer-api/app/core/cache_backend.py`, after `cache_delete_prefix` (`:167-188`):

```python
def cache_scan_prefix(prefix: str) -> list[str]:
    """List keys starting with prefix, from Redis (SCAN) and the memory tier."""
    found: set[str] = set()
    redis_client = get_redis_client()
    if redis_client and prefix:
        try:
            cursor = 0
            pattern = f"{prefix}*"
            while True:
                scan_result = cast(
                    tuple[int, list[str]],
                    redis_client.scan(cursor=cursor, match=pattern, count=100),
                )
                cursor, keys = scan_result
                for key in keys:
                    found.add(key.decode() if isinstance(key, bytes) else str(key))
                if cursor == 0:
                    break
        except Exception as exc:
            logger.warning("Redis SCAN scan_prefix error: %s", exc)
    with _memory_lock:
        for key in list(_memory_cache.keys()):
            if isinstance(key, str) and key.startswith(prefix):
                found.add(key)
    return sorted(found)
```

`_schedule_mapping_warm` is added in Task 6. For this task, add a temporary stub to `CustomerService` so the tests can patch it:

```python
    def _schedule_mapping_warm(self, names: tuple[str, ...]) -> None:
        # Replaced by the debounced scheduler in Task 6.
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `../../../.venv/bin/python -m pytest services/customer-api/tests/test_customer_service_invalidate_mapping.py -q`
Expected: PASS — 6 passed

- [ ] **Step 5: Commit**

```bash
git add services/customer-api/app/services/customer_service.py services/customer-api/app/services/cache_service.py services/customer-api/app/core/cache_backend.py services/customer-api/tests/test_customer_service_invalidate_mapping.py
git commit -m "feat(cache): invalidate_mapping_caches with a strict resolver"
```

---

### Task 6: Debounced background warm

**Files:**
- Create: `services/customer-api/app/services/mapping_warm_scheduler.py`
- Modify: `services/customer-api/app/services/customer_service.py` (replace the `_schedule_mapping_warm` stub from Task 5)
- Test: `services/customer-api/tests/test_mapping_warm_scheduler.py`

**Interfaces:**
- Consumes: `CustomerService._rebuild_customer_caches_for_customer` (`customer_service.py:853`).
- Produces: `MappingWarmScheduler(warm_fn: Callable[[str], None], delay_seconds: float = 10.0)` with methods `schedule(names: Iterable[str]) -> None` and `cancel_all() -> None`.

Debounce reason: with 352 customers and 0 mappings configured, a rollout means hundreds of back-to-back saves, and correcting one customer three times in a row should not fire three warms. Invalidation stays synchronous (correctness); only the warm is deferred. A user who opens the page immediately still sees correct data — their own read-through recomputes it; only that first hit is slow.

The debounce is process-local (timer + dict). That is safe today: customer-api runs as a single uvicorn process (`services/customer-api/Dockerfile:24`, no `--workers`). If it is ever scaled to replicas the worst case is one warm per replica — harmless, since warming is idempotent.

- [ ] **Step 1: Write the failing test**

Create `services/customer-api/tests/test_mapping_warm_scheduler.py`:

```python
import threading
import time

from app.services.mapping_warm_scheduler import MappingWarmScheduler


def test_warms_the_name_after_the_delay():
    warmed: list[str] = []
    done = threading.Event()

    def warm(name):
        warmed.append(name)
        done.set()

    sched = MappingWarmScheduler(warm_fn=warm, delay_seconds=0.05)
    sched.schedule(["Boyner"])

    assert done.wait(timeout=2.0)
    assert warmed == ["Boyner"]


def test_does_not_warm_before_the_delay_elapses():
    warmed: list[str] = []
    sched = MappingWarmScheduler(warm_fn=warmed.append, delay_seconds=5.0)
    sched.schedule(["Boyner"])

    time.sleep(0.05)
    assert warmed == []
    sched.cancel_all()


def test_second_save_within_the_window_cancels_the_first():
    warmed: list[str] = []
    done = threading.Event()

    def warm(name):
        warmed.append(name)
        done.set()

    sched = MappingWarmScheduler(warm_fn=warm, delay_seconds=0.1)
    sched.schedule(["Boyner"])
    time.sleep(0.02)
    sched.schedule(["Boyner"])  # rollout: correcting the same customer again

    assert done.wait(timeout=2.0)
    time.sleep(0.15)
    # Debounced to a single warm, not one per save.
    assert warmed == ["Boyner"]


def test_distinct_names_each_get_warmed():
    warmed: list[str] = []
    lock = threading.Lock()

    def warm(name):
        with lock:
            warmed.append(name)

    sched = MappingWarmScheduler(warm_fn=warm, delay_seconds=0.05)
    sched.schedule(["Boyner", "BOYNER BÜYÜK MAĞAZACILIK A.Ş."])

    time.sleep(0.5)
    assert sorted(warmed) == sorted(["Boyner", "BOYNER BÜYÜK MAĞAZACILIK A.Ş."])


def test_warm_failure_does_not_propagate():
    done = threading.Event()

    def warm(name):
        done.set()
        raise RuntimeError("query timed out")

    sched = MappingWarmScheduler(warm_fn=warm, delay_seconds=0.05)
    sched.schedule(["Boyner"])  # must not raise

    assert done.wait(timeout=2.0)
    time.sleep(0.05)


def test_cancel_all_stops_pending_warms():
    warmed: list[str] = []
    sched = MappingWarmScheduler(warm_fn=warmed.append, delay_seconds=0.2)
    sched.schedule(["Boyner"])
    sched.cancel_all()

    time.sleep(0.35)
    assert warmed == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `../../../.venv/bin/python -m pytest services/customer-api/tests/test_mapping_warm_scheduler.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.mapping_warm_scheduler'`

- [ ] **Step 3: Write minimal implementation**

Create `services/customer-api/app/services/mapping_warm_scheduler.py`:

```python
"""Debounced background warm for customers whose mapping just changed."""
from __future__ import annotations

import logging
import threading
from typing import Callable, Iterable

logger = logging.getLogger(__name__)

DEFAULT_WARM_DELAY_SECONDS = 10.0


class MappingWarmScheduler:
    """Warm a customer once, shortly after their mapping settles.

    Debounced per name: a rollout that corrects the same customer several times
    in a row should fire one warm, not one per save. Process-local by design —
    customer-api runs as a single uvicorn process, and if that ever changes the
    worst case is a duplicate warm, which is idempotent.
    """

    def __init__(
        self,
        warm_fn: Callable[[str], None],
        delay_seconds: float = DEFAULT_WARM_DELAY_SECONDS,
    ) -> None:
        self._warm_fn = warm_fn
        self._delay = delay_seconds
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def schedule(self, names: Iterable[str]) -> None:
        for raw in names or []:
            name = str(raw or "").strip()
            if not name:
                continue
            with self._lock:
                existing = self._timers.pop(name, None)
                if existing is not None:
                    existing.cancel()
                timer = threading.Timer(self._delay, self._run, args=(name,))
                timer.daemon = True
                self._timers[name] = timer
                timer.start()

    def _run(self, name: str) -> None:
        with self._lock:
            self._timers.pop(name, None)
        try:
            self._warm_fn(name)
        except Exception as exc:  # noqa: BLE001
            # Warming is an optimisation. A failure leaves the cache empty, and
            # the next read recomputes it — correctness is unaffected.
            logger.warning("Mapping warm failed for customer=%s: %s", name, exc)

    def cancel_all(self) -> None:
        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()
```

Then in `services/customer-api/app/services/customer_service.py`, add the import:

```python
from app.services.mapping_warm_scheduler import MappingWarmScheduler
```

and replace the Task 5 stub with a real lazy scheduler:

```python
    def _get_warm_scheduler(self) -> MappingWarmScheduler:
        scheduler = getattr(self, "_mapping_warm_scheduler", None)
        if scheduler is None:
            scheduler = MappingWarmScheduler(
                warm_fn=lambda name: self._rebuild_customer_caches_for_customer(name)
            )
            self._mapping_warm_scheduler = scheduler
        return scheduler

    def _schedule_mapping_warm(self, names: tuple[str, ...]) -> None:
        self._get_warm_scheduler().schedule(names)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `../../../.venv/bin/python -m pytest services/customer-api/tests/test_mapping_warm_scheduler.py services/customer-api/tests/test_customer_service_invalidate_mapping.py -q`
Expected: PASS — 12 passed

- [ ] **Step 5: Commit**

```bash
git add services/customer-api/app/services/mapping_warm_scheduler.py services/customer-api/app/services/customer_service.py services/customer-api/tests/test_mapping_warm_scheduler.py
git commit -m "feat(cache): debounced background warm after a mapping change"
```

---

### Task 7: Wire the invalidator into all five write paths

**Files:**
- Modify: `services/customer-api/app/services/sales_service.py` (`__init__` at `:62`; `save_source_mappings` `:685-690`; `seed_boyner_source_mappings` `:720-721`; `resync_aliases_from_datalake` `:731`; `upsert_alias` `:836`; `delete_alias` `:851`)
- Modify: `services/customer-api/app/main.py:48-56`
- Test: `services/customer-api/tests/test_mapping_write_paths_invalidate.py`

**Interfaces:**
- Consumes: `CustomerService.invalidate_mapping_caches` (Task 5).
- Produces: `SalesService.__init__` gains keyword `invalidate_mapping_caches: Callable[[set[str]], str | None] | None = None`, stored as `self._invalidate_mapping_caches`; and `SalesService._invalidate_for(account_ids: set[str]) -> str | None`. Task 8 reads the returned warning.

All five paths change what a mapping resolves to. `upsert_alias`/`delete_alias` qualify because `netbox_musteri_value` and `canonical_customer_key` feed `resolve_infra_search_name`, which supplies the fallback pattern when a source has no explicit rule. Today only `save_source_mappings` (`:686-687`) and `seed_boyner_source_mappings` (`:720-721`) invalidate anything at all, and only the two snapshot keys; `resync`, `upsert_alias` and `delete_alias` invalidate nothing.

- [ ] **Step 1: Write the failing test**

Create `services/customer-api/tests/test_mapping_write_paths_invalidate.py`:

```python
from unittest.mock import MagicMock

from app.services.sales_service import SalesService


def _service():
    invalidate = MagicMock(return_value=None)
    svc = SalesService.__new__(SalesService)
    svc._webui = MagicMock()
    svc._invalidate_mapping_caches = invalidate
    svc.list_source_mappings_for_account = lambda account_id: []
    return svc, invalidate


def test_save_source_mappings_invalidates_its_account():
    svc, invalidate = _service()

    svc.save_source_mappings("acct-1", crm_account_name="Acme", mappings=[])

    invalidate.assert_called_once_with({"acct-1"})


def test_upsert_alias_invalidates():
    svc, invalidate = _service()

    svc.upsert_alias("acct-1", "Acme", None, "acme-netbox", None)

    invalidate.assert_called_once_with({"acct-1"})


def test_delete_alias_invalidates():
    svc, invalidate = _service()
    svc._webui.execute.return_value = 1

    svc.delete_alias("acct-1")

    invalidate.assert_called_once_with({"acct-1"})


def test_invalidation_is_optional_when_not_injected():
    svc, _ = _service()
    svc._invalidate_mapping_caches = None

    # Must not blow up when the callable was never wired (e.g. unit tests).
    assert svc._invalidate_for({"acct-1"}) is None


def test_invalidation_warning_is_returned_not_raised():
    svc, invalidate = _service()
    invalidate.return_value = "Mapping kaydedildi, ancak cache temizlenemedi."

    warning = svc._invalidate_for({"acct-1"})

    assert warning == "Mapping kaydedildi, ancak cache temizlenemedi."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `../../../.venv/bin/python -m pytest services/customer-api/tests/test_mapping_write_paths_invalidate.py -q`
Expected: FAIL — `AttributeError: 'SalesService' object has no attribute '_invalidate_for'`

- [ ] **Step 3: Write minimal implementation**

In `services/customer-api/app/services/sales_service.py`, add the parameter to `__init__` (after `get_customer_assets=None` at `:67`):

```python
        invalidate_mapping_caches=None,
```

and store it alongside the other injected callables (after `self._get_customer_assets = get_customer_assets`):

```python
        self._invalidate_mapping_caches = invalidate_mapping_caches
```

Add this helper to `SalesService` (immediately before `save_source_mappings`):

```python
    def _invalidate_for(self, account_ids: set[str]) -> str | None:
        """Drop cached views for these accounts. Returns a warning, or None.

        Injected from main.py rather than imported, so SalesService never has to
        know about CustomerService.
        """
        if self._invalidate_mapping_caches is None:
            return None
        return self._invalidate_mapping_caches(account_ids)
```

Replace `save_source_mappings`'s tail (`:685-690`, the `try/except: pass` block and the return):

```python
        try:
            cache.delete(ALIASES_SNAPSHOT_KEY)
            cache.delete(CATALOG_SNAPSHOT_KEY)
        except Exception:  # noqa: BLE001
            pass
        self._invalidate_for({crm_accountid})
        return self.list_source_mappings_for_account(crm_accountid)
```

In `seed_boyner_source_mappings`, after the existing `cache.delete(CATALOG_SNAPSHOT_KEY)` at `:721`, add:

```python
        self._invalidate_for({account_id})
```

In `resync_aliases_from_datalake`, the function already builds `name_to_ids: dict[str, set[str]]` (populated by `name_to_ids.setdefault(account_name.casefold(), set()).add(account_id)` in its first loop over `project_rows`), so every reconciled account id is already collected. Immediately before its `return {` statement — after `self._account_ids_cache.clear()` — add:

```python
        # Resync can rewrite mappings for many accounts at once; name_to_ids
        # already holds every account the reconcile walked.
        self._invalidate_for({aid for ids in name_to_ids.values() for aid in ids})
```

In `upsert_alias`, after the existing `self._webui.execute(smq.UPSERT_ALIAS, ...)` call:

```python
        self._invalidate_for({crm_accountid})
```

In `delete_alias`, capture the rowcount, invalidate, then return:

```python
    def delete_alias(self, crm_accountid: str) -> int:
        if not self._webui:
            raise RuntimeError("WebUI pool not configured")
        deleted = self._webui.execute(smq.DELETE_ALIAS, (crm_accountid,))
        self._invalidate_for({crm_accountid})
        return deleted
```

Finally wire it in `services/customer-api/app/main.py:48-56`:

```python
    app.state.sales = SalesService(
        get_connection=svc._get_connection,
        run_row=svc._run_row,
        run_rows=svc._run_rows,
        get_customer_assets=lambda name, time_range=None: svc.get_customer_resources(
            name, time_range
        ),
        invalidate_mapping_caches=lambda account_ids: svc.invalidate_mapping_caches(
            account_ids
        ),
        webui=webui,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `../../../.venv/bin/python -m pytest services/customer-api/tests/test_mapping_write_paths_invalidate.py services/customer-api/tests/test_save_source_mappings_atomic.py -q`
Expected: PASS — 7 passed

- [ ] **Step 5: Commit**

```bash
git add services/customer-api/app/services/sales_service.py services/customer-api/app/main.py services/customer-api/tests/test_mapping_write_paths_invalidate.py
git commit -m "feat(crm): invalidate mapping caches from all five write paths"
```

---

### Task 8: Carry the cache warning to the API response

**Files:**
- Modify: `services/customer-api/app/services/sales_service.py` (`save_source_mappings` signature and return)
- Modify: `services/customer-api/app/routers/sales.py:166-180`
- Test: `services/customer-api/tests/test_save_source_mappings_response.py`

**Interfaces:**
- Consumes: `SalesService._invalidate_for` (Task 7).
- Produces: `save_source_mappings` now returns `dict` shaped `{"mappings": list[dict], "cache_warning": str | None}`. The route's `response_model` becomes `SourceMappingSaveResult`. Task 9's GUI client consumes this shape.

The endpoint currently returns a bare `List[dict]` (`sales.py:166`, `response_model=List[dict]`), which has nowhere to put a warning.

- [ ] **Step 1: Write the failing test**

Create `services/customer-api/tests/test_save_source_mappings_response.py`:

```python
from unittest.mock import MagicMock

from app.services.sales_service import SalesService


def _service(warning=None):
    svc = SalesService.__new__(SalesService)
    svc._webui = MagicMock()
    svc._invalidate_mapping_caches = MagicMock(return_value=warning)
    svc.list_source_mappings_for_account = lambda account_id: [{"data_source": "virtualization"}]
    return svc


def test_happy_path_has_no_warning():
    svc = _service(warning=None)

    out = svc.save_source_mappings("acct-1", crm_account_name="Acme", mappings=[])

    assert out["cache_warning"] is None
    assert out["mappings"] == [{"data_source": "virtualization"}]


def test_cache_failure_surfaces_as_a_warning_and_still_saves():
    svc = _service(warning="Mapping kaydedildi, ancak cache temizlenemedi — lütfen tekrar kaydedin.")

    out = svc.save_source_mappings("acct-1", crm_account_name="Acme", mappings=[])

    # Saved (mappings returned) AND warned — not an exception.
    assert out["mappings"] == [{"data_source": "virtualization"}]
    assert "cache" in out["cache_warning"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `../../../.venv/bin/python -m pytest services/customer-api/tests/test_save_source_mappings_response.py -q`
Expected: FAIL — `TypeError: list indices must be integers or slices, not str`

- [ ] **Step 3: Write minimal implementation**

In `services/customer-api/app/services/sales_service.py`, change `save_source_mappings`'s return annotation from `-> list[dict[str, Any]]` to `-> dict[str, Any]`, and replace its final two lines with:

```python
        cache_warning = self._invalidate_for({crm_accountid})
        return {
            "mappings": self.list_source_mappings_for_account(crm_accountid),
            "cache_warning": cache_warning,
        }
```

In `services/customer-api/app/models/schemas.py` — **not** `app/models.py`, which does not exist — add this next to the other CRM alias models (`CustomerSourceMappingUpdate` is at `:133`, `CustomerAliasWithMappings` at `:139`). `BaseModel`, `List` and `Optional` are already imported at the top of that file:

```python
class SourceMappingSaveResult(BaseModel):
    mappings: List[dict]
    cache_warning: Optional[str] = None
```

In `services/customer-api/app/routers/sales.py`, add `SourceMappingSaveResult` to the existing `from app.models.schemas import (...)` block (alphabetically, after `SalesOrderHeader`) and change the route:

```python
@router.put("/crm/aliases/{crm_accountid}/source-mappings", response_model=SourceMappingSaveResult)
def save_source_mappings(
    crm_accountid: str,
    body: CustomerSourceMappingUpdate,
    svc: SalesService = Depends(get_sales_service),
):
    """Replace all source mappings for a CRM account.

    Returns cache_warning when the mappings were saved but their cached views
    could not be dropped — the save has already committed, so this is a warning
    rather than an error.
    """
    mappings = [m.model_dump() for m in (body.mappings or [])]
    return svc.save_source_mappings(
        crm_accountid,
        crm_account_name=body.crm_account_name or crm_accountid,
        mappings=mappings,
        notes=body.notes,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `../../../.venv/bin/python -m pytest services/customer-api/tests/test_save_source_mappings_response.py -q`
Expected: PASS — 2 passed

- [ ] **Step 5: Commit**

```bash
git add services/customer-api/app/services/sales_service.py services/customer-api/app/models.py services/customer-api/app/routers/sales.py services/customer-api/tests/test_save_source_mappings_response.py
git commit -m "feat(api): return cache_warning from the source-mappings save"
```

---

### Task 9: GUI — clear its own cache and show the warning

**Files:**
- Modify: `src/services/api_client.py` (`put_crm_source_mappings` at `:2233`, `seed_boyner_source_mappings` just below it)
- Modify: `src/pages/settings/integrations/crm_aliases_callbacks.py` (`save_editor_mappings_cb` at `:317`)
- Test: `tests/test_api_client_mapping_invalidation.py`

**Interfaces:**
- Consumes: the `{mappings, cache_warning}` response from Task 8.
- Produces: `put_crm_source_mappings(...) -> tuple[list[dict], str | None]` — returns `(mappings, cache_warning)`.

The GUI keeps its own cache in the `dl:fecache:` namespace, a **different Redis database** from customer-api's, so the backend's invalidation cannot reach it. Worse, GUI entries carry **no TTL at all** (`src/services/cache_service.py:137`) — nothing expires them. Clearing them is blunt on purpose: refetching costs one HTTP call to an already-warm backend, whereas a backend key costs a DB query.

Prefixes are version-agnostic (`api:customer_resources:`, not `api:customer_resources:cpu-usage-v3:`). The GUI currently hardcodes the version at `api_client.py:709`, and parallel work is replacing it with the shared constant; a version-free prefix is correct either way and conflicts with neither.

- [ ] **Step 1: Write the failing test**

Create `tests/test_api_client_mapping_invalidation.py`:

```python
from unittest.mock import MagicMock, patch

from src.services import api_client


def test_put_returns_mappings_and_warning():
    payload = {"mappings": [{"data_source": "virtualization"}], "cache_warning": None}
    with patch.object(api_client, "_put_json", return_value=payload), patch.object(
        api_client, "_api_response_cache"
    ):
        mappings, warning = api_client.put_crm_source_mappings("acct-1", mappings=[])

    assert mappings == [{"data_source": "virtualization"}]
    assert warning is None


def test_put_surfaces_backend_cache_warning():
    payload = {"mappings": [], "cache_warning": "cache temizlenemedi"}
    with patch.object(api_client, "_put_json", return_value=payload), patch.object(
        api_client, "_api_response_cache"
    ):
        _mappings, warning = api_client.put_crm_source_mappings("acct-1", mappings=[])

    assert warning == "cache temizlenemedi"


def test_put_clears_the_gui_resource_cache():
    payload = {"mappings": [], "cache_warning": None}
    cache = MagicMock()
    with patch.object(api_client, "_put_json", return_value=payload), patch.object(
        api_client, "_api_response_cache", cache
    ):
        api_client.put_crm_source_mappings("acct-1", mappings=[])

    # Version-agnostic prefix: the version token is being bumped elsewhere.
    cache.delete_prefix.assert_any_call("api:customer_resources:")
    cache.delete.assert_any_call("api:crm_aliases")
    cache.delete.assert_any_call("api:customer_catalog")
    cache.delete.assert_any_call("api:customer_overview")


def test_put_tolerates_a_malformed_response():
    with patch.object(api_client, "_put_json", return_value="nonsense"), patch.object(
        api_client, "_api_response_cache"
    ):
        mappings, warning = api_client.put_crm_source_mappings("acct-1", mappings=[])

    assert mappings == []
    assert warning is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `../../../.venv/bin/python -m pytest tests/test_api_client_mapping_invalidation.py -q`
Expected: FAIL — `TypeError: cannot unpack non-sequence` (the function still returns a list)

- [ ] **Step 3: Write minimal implementation**

Replace `put_crm_source_mappings` in `src/services/api_client.py:2233`:

```python
def put_crm_source_mappings(
    crm_accountid: str,
    *,
    crm_account_name: Optional[str] = None,
    mappings: Optional[list[dict[str, Any]]] = None,
    notes: Optional[str] = None,
) -> tuple[list[dict[str, Any]], Optional[str]]:
    """Save source mappings. Returns (mappings, cache_warning)."""
    enc = quote(crm_accountid, safe="")
    body = {
        "crm_account_name": crm_account_name,
        "mappings": mappings or [],
        "notes": notes,
    }
    out = _put_json(_get_client_cust(), f"/api/v1/crm/aliases/{enc}/source-mappings", body)
    _invalidate_customer_views_cache()
    if not isinstance(out, dict):
        return [], None
    saved = out.get("mappings")
    return (saved if isinstance(saved, list) else []), out.get("cache_warning")
```

Add this helper just above it:

```python
def _invalidate_customer_views_cache() -> None:
    """Drop the front-end's own copies of anything a mapping change affects.

    This namespace lives in a different Redis database from customer-api's and
    its entries carry no TTL, so nothing else will ever clear them. The prefix
    is deliberately version-free: the version token is being bumped by parallel
    work, and a pinned prefix would silently stop matching.
    """
    _api_response_cache.delete_prefix("api:customer_resources:")
    _api_response_cache.delete("api:crm_aliases")
    _api_response_cache.delete("api:customer_catalog")
    _api_response_cache.delete("api:customer_overview")
```

Update `seed_boyner_source_mappings` in the same file to reuse it:

```python
def seed_boyner_source_mappings() -> dict[str, Any]:
    out = _post_json(_get_client_cust(), "/api/v1/crm/aliases/seed-boyner", {})
    _invalidate_customer_views_cache()
    return out if isinstance(out, dict) else {}
```

Then update the caller in `src/pages/settings/integrations/crm_aliases_callbacks.py:317` (`save_editor_mappings_cb`). It currently unpacks a bare list and always returns a green `dmc.Alert`:

```python
        saved = api.put_crm_source_mappings(
            account_id,
            crm_account_name=account_name,
            mappings=mappings,
            notes=note_text,
        )
```

Change that call to unpack the tuple:

```python
        saved, cache_warning = api.put_crm_source_mappings(
            account_id,
            crm_account_name=account_name,
            mappings=mappings,
            notes=note_text,
        )
```

`merge_alias_after_save(..., saved_mappings=saved or mappings, ...)` below it keeps working unchanged — `saved` is still the mappings list.

Then replace the green success alert in the returned tuple's first slot:

```python
            dmc.Alert(color="green", title="Saved", children=f"Mappings updated for {account_name}."),
```

with a conditional built just above the `return`:

```python
        if cache_warning:
            # Saved, but the cached views may still show the old mapping.
            save_alert = dmc.Alert(
                color="yellow",
                title="Saved — cache warning",
                children=cache_warning,
            )
        else:
            save_alert = dmc.Alert(
                color="green",
                title="Saved",
                children=f"Mappings updated for {account_name}.",
            )
```

and use `save_alert` in that slot. Leave the red `dmc.Alert(color="red", title="Save failed", ...)` in the `except` branch untouched — a genuine save failure is still an error.

**Note:** this page uses `dmc.Alert` for save feedback, not `dmc.Notification`. Follow the existing pattern.

- [ ] **Step 4: Run test to verify it passes**

Run: `../../../.venv/bin/python -m pytest tests/test_api_client_mapping_invalidation.py -q`
Expected: PASS — 4 passed

Then confirm the existing alias-page tests still pass:

Run: `../../../.venv/bin/python -m pytest tests/test_crm_aliases_page.py tests/test_api_client_auranotify_mapping.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/services/api_client.py src/pages/settings/integrations/crm_aliases_callbacks.py tests/test_api_client_mapping_invalidation.py
git commit -m "feat(gui): clear front-end caches and surface the cache warning"
```

---

### Task 10: Regression test — the bug itself

**Files:**
- Test: `services/customer-api/tests/test_mapping_takes_effect_regression.py`

**Interfaces:**
- Consumes: everything above. Adds no production code.

This is the test that would have caught the original bug: a warm cache entry plus a mapping change must not keep serving the old attribution. It fails on the base commit and passes once Tasks 1-9 land. The key detail is the `:last_good` shadow — deleting only the primary is not enough, because `cache_get` falls back to the shadow and the factory never re-runs.

- [ ] **Step 1: Write the failing test**

Create `services/customer-api/tests/test_mapping_takes_effect_regression.py`:

```python
from unittest.mock import MagicMock, patch

from app.services.customer_service import CustomerService

ACCOUNT = "acct-boyner"

# Mirrors production: one account cached under two display names, primary and
# shadow, exactly as observed on the live Redis.
SEEDED_KEYS = [
    "customer_assets:cpu-usage-v3:Boyner:2026-07-09:2026-07-16",
    "customer_assets:cpu-usage-v3:Boyner:2026-07-09:2026-07-16:last_good",
    "customer_assets:cpu-usage-v3:BOYNER BÜYÜK MAĞAZACILIK A.Ş.:2026-07-09:2026-07-16",
    "customer_assets:cpu-usage-v3:BOYNER BÜYÜK MAĞAZACILIK A.Ş.:2026-07-09:2026-07-16:last_good",
    "customer_assets:cpu-usage-v3:Other Corp:2026-07-09:2026-07-16",
]


def test_saving_a_mapping_evicts_every_cached_view_of_that_account():
    store = {k: {"stale": True} for k in SEEDED_KEYS}
    svc = CustomerService.__new__(CustomerService)
    svc._webui = MagicMock()

    def fake_resolve(name):
        return ACCOUNT if name.lower().startswith("boyner") else "other-acct"

    with patch("app.services.customer_service.cache") as cache, patch.object(
        CustomerService, "resolve_account_id_strict", side_effect=fake_resolve
    ), patch.object(CustomerService, "_schedule_mapping_warm"):
        cache.scan_prefix.side_effect = lambda p: [k for k in store if k.startswith(p)]
        cache.delete.side_effect = store.pop

        warning = svc.invalidate_mapping_caches({ACCOUNT})

    assert warning is None
    # Both display names gone, primary AND shadow.
    assert not [k for k in store if "Boyner" in k or "BOYNER" in k]
    # The unrelated account is untouched.
    assert "customer_assets:cpu-usage-v3:Other Corp:2026-07-09:2026-07-16" in store


def test_the_last_good_shadow_is_not_left_behind():
    # A surviving shadow is what made the mapping invisible for ~24h: cache_get
    # falls back to it, so run_singleflight never calls the factory.
    store = {k: {"stale": True} for k in SEEDED_KEYS}
    svc = CustomerService.__new__(CustomerService)
    svc._webui = MagicMock()

    with patch("app.services.customer_service.cache") as cache, patch.object(
        CustomerService, "resolve_account_id_strict", return_value=ACCOUNT
    ), patch.object(CustomerService, "_schedule_mapping_warm"):
        cache.scan_prefix.side_effect = lambda p: [k for k in store if k.startswith(p)]
        cache.delete.side_effect = store.pop

        svc.invalidate_mapping_caches({ACCOUNT})

    assert not [k for k in store if k.endswith(":last_good")]
```

- [ ] **Step 2: Confirm the guard is real, without touching the stash**

**Do not use `git stash` here.** The stash stack is shared with the main checkout and the two other active worktrees (`customer-alias-matching`, `fix+overview-metrics-and-loading`); popping it could restore someone else's work into this tree.

Verify against the base commit in a throwaway checkout instead:

```bash
git worktree add /tmp/mapping-regression-check 3de24d83
cp services/customer-api/tests/test_mapping_takes_effect_regression.py \
   /tmp/mapping-regression-check/services/customer-api/tests/
cd /tmp/mapping-regression-check && \
  /Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI/.venv/bin/python \
  -m pytest services/customer-api/tests/test_mapping_takes_effect_regression.py -q
cd - && git worktree remove --force /tmp/mapping-regression-check
```

Expected: FAIL on the base — `AttributeError: 'CustomerService' object has no attribute 'invalidate_mapping_caches'`. That is the proof the guard catches the real bug.

If you would rather skip this, Step 4 plus Task 11's live verification still cover it; the tests in Tasks 1-9 each ran red before their implementation.

- [ ] **Step 3: No implementation needed**

Tasks 1-9 already provide the behaviour. This task only adds the regression guard.

- [ ] **Step 4: Run the whole feature's tests**

Run:
```bash
../../../.venv/bin/python -m pytest \
  services/customer-api/tests/test_mapping_cache_invalidator.py \
  services/customer-api/tests/test_webui_db_execute_all.py \
  services/customer-api/tests/test_save_source_mappings_atomic.py \
  services/customer-api/tests/test_customer_service_invalidate_mapping.py \
  services/customer-api/tests/test_mapping_warm_scheduler.py \
  services/customer-api/tests/test_mapping_write_paths_invalidate.py \
  services/customer-api/tests/test_save_source_mappings_response.py \
  services/customer-api/tests/test_mapping_takes_effect_regression.py \
  tests/test_api_client_mapping_invalidation.py -q
```
Expected: PASS — 33 passed

- [ ] **Step 5: Commit**

```bash
git add services/customer-api/tests/test_mapping_takes_effect_regression.py
git commit -m "test(cache): regression guard for mapping saves taking effect"
```

---

### Task 11: Verify against the running stack

**Files:** none — verification only.

**Interfaces:** consumes the whole feature.

Unit tests use fakes, so they cannot prove the Redis key shapes are right. The dev stack is live (`bulutistan-redis`, `bulutistan-customer-api` on :8001, `datalake-platform-gui-app` on :8050), and the pre-fix zombie state is measurable there — so the fix is measurable too.

- [ ] **Step 1: Record the pre-change state**

```bash
docker exec bulutistan-redis redis-cli -n 1 --scan --pattern "customer_assets:*" | wc -l
```
Note the count. Confirm the API is healthy:
```bash
curl -s http://localhost:8001/health
```
Expected: `{"status":"ok",...}`

- [ ] **Step 2: Rebuild and restart customer-api with the change**

```bash
docker compose up -d --build customer-api
docker compose logs --tail=30 customer-api
```
Expected: no import errors; health returns ok.

- [ ] **Step 3: Warm one customer, then save a mapping for it**

Pick an account id from `curl -s http://localhost:8001/api/v1/crm/aliases | head -c 400`, open that customer in the GUI (http://localhost:8050) so a `customer_assets:` key exists, then confirm:

```bash
docker exec bulutistan-redis redis-cli -n 1 --scan --pattern "customer_assets:*"
```
Expected: at least one primary key and its `:last_good` sibling for that customer.

Save a mapping for the same account through the GUI's alias editor.

- [ ] **Step 4: Confirm the keys are gone and the log says so**

```bash
docker exec bulutistan-redis redis-cli -n 1 --scan --pattern "customer_assets:*"
docker compose logs --tail=20 customer-api | grep -i "invalidation"
```
Expected: that customer's keys — **primary and `:last_good`** — are gone; other customers' keys remain; the log shows `Mapping cache invalidation deleted N keys for names=[...]` with N > 0.

If it logs `deleted nothing`, the name resolution missed. Do not paper over it: capture the account id and the key list and report back.

- [ ] **Step 5: Confirm the warm repopulates**

Wait ~15 seconds (10s debounce + query time), then:

```bash
docker exec bulutistan-redis redis-cli -n 1 --scan --pattern "customer_assets:*"
```
Expected: keys for that customer reappear, rebuilt with the new mapping applied.

- [ ] **Step 6: Commit nothing; report the observed output**

This task produces evidence, not code. Paste the before/after key lists and the log line into the PR description.

---

### Task 12: Register `auranotify` as a real data source

**Files:**
- Modify: `services/customer-api/app/services/customer_mapping_resolver.py:10-20` (`DATA_SOURCES`) and `:44-51` (`UI_COLUMN_SOURCES`)
- Test: `services/customer-api/tests/test_auranotify_data_source.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `"auranotify"` becomes a member of `DATA_SOURCES`, so `save_source_mappings`'s `allowed_sources` check (`sales_service.py:655`, `:666-667`) accepts it.

**Why this is here and not in the other plan.** The front end already offers an AuraNotify section and sends `data_source: "auranotify"` (`src/utils/crm_source_mapping_ui.py:11`, rendered as a real populated `dmc.Select` in `crm_aliases.py:72-86`), but `DATA_SOURCES` (`customer_mapping_resolver.py:10-20`) has no such member, so `save_source_mappings` raises `ValueError` and — with no handler for it in `main.py` — the user gets a **500**. The `2026-07-10-customer-availability-auranotify-mapping` plan landed the front-end half and not the back-end half; no backend test mentions `auranotify`, which is why CI is green.

The `customer-alias-matching` plan **assumes** `auranotify` is already legal — it defines `ID_SOURCES = ("physical_device", "auranotify")` in the new `shared/customer/match.py` and adds migration `028` with `WHEN data_source IN ('physical_device', 'auranotify')` — but it never touches `DATA_SOURCES` (verified: the string appears nowhere in that plan). So without this task, that plan lands and AuraNotify still 500s: the DB constraint would permit a value the API rejects before the statement is ever sent. This one line is the seam neither plan owned.

Only `DATA_SOURCES` and `UI_COLUMN_SOURCES` (`:10-20`, `:44-51`) are edited here. The other plan's Task 3 rewrites `sql_pattern_for_match` / `ResolvedSourcePatterns` / `build_resolved_patterns` (`:95-186`) — different regions of the same file, so a merge conflict is unlikely, and a textual one would be trivial to resolve.

- [ ] **Step 1: Write the failing test**

Create `services/customer-api/tests/test_auranotify_data_source.py`:

```python
from unittest.mock import MagicMock

from app.services.customer_mapping_resolver import DATA_SOURCES, UI_COLUMN_SOURCES
from app.services.sales_service import SalesService


def test_auranotify_is_a_known_data_source():
    # The UI has shipped an AuraNotify section that posts this value.
    assert "auranotify" in DATA_SOURCES


def test_auranotify_maps_to_a_ui_column():
    assert UI_COLUMN_SOURCES["auranotify"] == ("auranotify",)


def test_saving_an_auranotify_mapping_does_not_raise():
    svc = SalesService.__new__(SalesService)
    svc._webui = MagicMock()
    svc._invalidate_mapping_caches = MagicMock(return_value=None)
    svc.list_source_mappings_for_account = lambda account_id: []

    # Before this task this raised ValueError -> unhandled -> HTTP 500.
    out = svc.save_source_mappings(
        "acct-1",
        crm_account_name="Acme",
        mappings=[
            {"data_source": "auranotify", "match_method": "id_exact", "match_value": "42"}
        ],
    )

    assert out["cache_warning"] is None
    svc._webui.execute_all.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `../../../.venv/bin/python -m pytest services/customer-api/tests/test_auranotify_data_source.py -q`
Expected: FAIL — `assert 'auranotify' in DATA_SOURCES`, and the save test fails with `ValueError: Unsupported data_source: auranotify`

- [ ] **Step 3: Write minimal implementation**

In `services/customer-api/app/services/customer_mapping_resolver.py`, add `auranotify` to `DATA_SOURCES` (`:10-20`):

```python
DATA_SOURCES: tuple[str, ...] = (
    "virtualization",
    "backup_veeam",
    "backup_zerto",
    "backup_netbackup",
    "storage_ibm",
    "s3_icos",
    "physical_device",
    "netbox_vm_customer",
    "itsm_servicecore",
    "auranotify",
)
```

and add its UI column to `UI_COLUMN_SOURCES` (`:44-51`):

```python
UI_COLUMN_SOURCES: dict[str, tuple[str, ...]] = {
    "virtualization": ("virtualization", "netbox_vm_customer"),
    "backup": ("backup_veeam", "backup_zerto", "backup_netbackup"),
    "physical_device": ("physical_device",),
    "storage": ("storage_ibm",),
    "s3": ("s3_icos",),
    "itsm": ("itsm_servicecore",),
    "auranotify": ("auranotify",),
}
```

`DATA_SOURCE_UI_COLUMN` (`:54-56`) is derived from `UI_COLUMN_SOURCES` by comprehension, so it picks this up with no further edit.

- [ ] **Step 4: Run test to verify it passes**

Run: `../../../.venv/bin/python -m pytest services/customer-api/tests/test_auranotify_data_source.py services/customer-api/tests/test_customer_mapping_resolver.py -q`
Expected: PASS

Also confirm the front-end side still agrees:

Run: `../../../.venv/bin/python -m pytest tests/test_api_client_auranotify_mapping.py tests/test_crm_aliases_auranotify_render.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/customer-api/app/services/customer_mapping_resolver.py services/customer-api/tests/test_auranotify_data_source.py
git commit -m "fix(crm): register auranotify as a data source so its save stops 500ing"
```

---

## Notes for the reviewer

- **Root cause deliberately untouched.** `cache_run_singleflight` still falls back to the `last_good` shadow (`app/core/cache_backend.py:219-222`), so the 15-minute and 6-hour scheduled warms remain no-ops. Fixing that would make hundreds of never-before-run queries fire at once against a DB whose queries already carry a 120s timeout, and nobody has measured that load. It gets its own spec. This plan does not depend on it: explicitly deleting both the primary and the shadow leaves nothing to fall back to, so the next read genuinely recomputes.
- **Known gap.** A customer whose cache was never populated has no keys to delete, so `deleted_count` is legitimately 0 and the WARNING is noise in that case. It is kept anyway: a silent miss and a genuine miss look identical from the outside, and only the log can tell them apart.
