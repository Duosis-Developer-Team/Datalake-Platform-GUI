"""Seed backup_netbackup alias rules from backup-musteri-isim.xlsx.

The naming standard (shared/customer/backup_policy.py) derives a customer's
policy prefix in 87% of live cases, but 27% of those match more than one CRM
account — 'avro' addresses both AVROMED and AVRORA LLC. The spreadsheet
resolves exactly those, so it is loaded as ground truth alongside the
heuristic rather than instead of it.

Candidates are always decided against the FULL CRM roster (api.get_crm_accounts()),
never the project-customer subset (api.get_crm_aliases()) — restricting the pool
up front manufactures false single matches: 'Sabancı' has 5 real candidates, but
only one carries a PRJ-* sales order, so a project-scoped lookup finds exactly
one and calls it resolved. Project membership only decides whether a genuinely
unambiguous match may be WRITTEN (an alias on a non-project account is invisible
on the Customer Aliases admin page — see resolve_accounts() below).

Idempotent: rules already present are not rewritten. Rows that cannot be
resolved to a CRM account, resolve to more than one, or resolve to exactly one
non-project account, are reported by name, never dropped in silence — a silent
skip is indistinguishable from a successful seed.

Usage:
    ./.venv/bin/python -m scripts.seed_backup_policy_aliases <xlsx> [--apply]

Without --apply it prints the plan and writes nothing.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

from shared.customer.unmapped_classifier import norm

SHEET_NAME = "AD-KARŞILIĞI"
DATA_SOURCE = "backup_netbackup"
MATCH_METHOD = "prefix"

_HEADER_CELLS = {"musteri adi", "policy adi"}


@dataclass
class SeedPlan:
    # (accountid, sheet_name, crm_account_name, tokens) — exactly one full-roster
    # candidate AND that candidate is a project customer. Writable.
    matched: list[tuple[str, str, str, list[str]]] = field(default_factory=list)
    # sheet names with zero full-roster candidates.
    not_found: list[str] = field(default_factory=list)
    # (sheet_name, [crm_account_name, ...]) — 2+ full-roster candidates. Needs a human.
    ambiguous: list[tuple[str, list[str]]] = field(default_factory=list)
    # (accountid, sheet_name, crm_account_name, tokens) — exactly one full-roster
    # candidate, but it carries no PRJ-* sales order, so it is invisible on the
    # Customer Aliases admin page (SalesService.get_all_aliases() only ever
    # iterates project rows + the legacy alias index — no third loop for
    # orphaned mappings). Real customer, correctly identified, but the alias
    # system cannot address it yet. Reported, never written.
    not_addressable: list[tuple[str, str, str, list[str]]] = field(default_factory=list)


def parse_sheet_rows(raw_rows) -> list[tuple[str, list[str]]]:
    """(customer, [token, ...]) per sheet row; headers and blanks dropped.

    A cell may hold several comma-separated tokens ('aksu,aksular'); each
    becomes its own rule, because they are alternative prefixes rather than
    one compound value.
    """
    out: list[tuple[str, list[str]]] = []
    for name_cell, policy_cell in raw_rows:
        name = str(name_cell or "").strip()
        policy = str(policy_cell or "").strip()
        if not name or not policy:
            continue
        if norm(name) in {norm(h) for h in _HEADER_CELLS}:
            continue
        tokens = [t.strip().lower() for t in policy.split(",") if t.strip()]
        if tokens:
            out.append((name, tokens))
    return out


def resolve_accounts(sheet_rows, crm_accounts, project_account_ids: Iterable[str]) -> SeedPlan:
    """Match short sheet names against the FULL CRM roster, then gate writes.

    `crm_accounts` must be the full roster (api.get_crm_accounts(), backed by
    discovery_crm_accounts) — NOT the project-customer subset api.get_crm_aliases()
    returns. Candidates are decided against that full set first; only after
    ambiguity has already been resolved does `project_account_ids` narrow the
    result to what may actually be written. Deciding project membership before
    counting candidates would silently manufacture false single matches: e.g.
    'Sabancı' has 5 real candidates and only one carries a PRJ-* sales order —
    scoping the pool to project customers up front finds exactly one of them
    and calls it resolved, when the real answer is "ambiguous, ask a human."

    Uses the same Turkish folding as the classifier so this path and the
    runtime path cannot disagree about what two names being "the same" means.
    """
    project_ids = {str(a).strip() for a in (project_account_ids or ()) if str(a).strip()}

    by_key: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for acc in crm_accounts:
        name = str(acc.get("name") or "").strip()
        accountid = str(acc.get("accountid") or "").strip()
        if name and accountid:
            by_key[norm(name)].append((name, accountid))

    plan = SeedPlan()
    for sheet_name, tokens in sheet_rows:
        key = norm(sheet_name)
        exact = by_key.get(key, [])
        # Startswith fallback for short sheet names ('Aksular' -> 'AKSULAR GIDA
        # SANAYİ A.Ş.'). This is a wide net on purpose — 'Azer' alone starts 5
        # full-roster account names in production, AZERSUN HOLDİNG among them.
        # That is now SAFE: excess candidates land in `ambiguous`, never picked
        # for the caller. Do NOT tighten this to shrink a large ambiguous
        # count — narrowing the candidate pool (e.g. to project customers, as
        # this function used to) is exactly what hid that real ambiguity
        # behind a false single match before.
        candidates = exact or [
            entry
            for k, entries in by_key.items()
            if k.startswith(key) and len(key) >= 4
            for entry in entries
        ]
        if not candidates:
            plan.not_found.append(sheet_name)
        elif len(candidates) > 1:
            plan.ambiguous.append((sheet_name, sorted(c[0] for c in candidates)))
        else:
            name, accountid = candidates[0]
            if accountid in project_ids:
                plan.matched.append((accountid, sheet_name, name, tokens))
            else:
                plan.not_addressable.append((accountid, sheet_name, name, tokens))
    return plan


def format_report(plan: SeedPlan) -> str:
    lines = [
        f"Matched:         {len(plan.matched)} customers",
        f"Not found:       {len(plan.not_found)} customers",
        f"Ambiguous:       {len(plan.ambiguous)} customers",
        f"Not addressable: {len(plan.not_addressable)} customers",
        "",
    ]
    if plan.matched:
        lines.append("Matched (sheet name -> CRM account; written on --apply) — check these by eye:")
        for _accountid, sheet_name, crm_name, tokens in plan.matched:
            lines.append(f"  - {sheet_name} -> {crm_name} [{', '.join(tokens)}]")
        lines.append("")
    if plan.not_found:
        lines.append("No CRM account for these sheet names:")
        lines += [f"  - {n}" for n in plan.not_found]
        lines.append("")
    if plan.ambiguous:
        lines.append("These sheet names match more than one CRM account (pick one by hand):")
        for sheet_name, names in plan.ambiguous:
            lines.append(f"  - {sheet_name}: {', '.join(names)}")
        lines.append("")
    if plan.not_addressable:
        lines.append(
            "These sheet names resolve to exactly one real CRM account, but it has no "
            "PRJ-* sales order, so an alias on it would be invisible on the Customer "
            "Aliases admin page. Not written:"
        )
        for _accountid, sheet_name, crm_name, tokens in plan.not_addressable:
            lines.append(f"  - {sheet_name} -> {crm_name} [{', '.join(tokens)}]")
        lines.append("")
    return "\n".join(lines)


def load_sheet(path: str) -> list[tuple[str, list[str]]]:
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[SHEET_NAME]
    return parse_sheet_rows(
        (row[0], row[1]) for row in ws.iter_rows(values_only=True) if row and len(row) >= 2
    )


def group_matched_by_account(matched) -> dict[str, tuple[str, list[str]]]:
    """accountid -> (crm_account_name, every token any sheet row asked for).

    Two sheet rows can resolve to the same CRM account — resolve_accounts()'s
    startswith fallback makes that easy ('Azer' and 'Azersun' both land on
    AZERSUN HOLDİNG). Writing them as two independent PUTs would make the
    second one, built from the same pre-write snapshot, drop the first's
    tokens. One account, one union, one write.
    """
    grouped: dict[str, tuple[str, list[str]]] = {}
    for accountid, _sheet_name, account_name, tokens in matched:
        name, existing = grouped.get(accountid, (account_name, []))
        merged = list(existing)
        for token in tokens:
            if token not in merged:
                merged.append(token)
        grouped[accountid] = (name, merged)
    return grouped


def apply_plan(plan: SeedPlan) -> tuple[int, int]:
    """Write the matched rules. Returns (accounts_written, rules_added).

    Read-modify-write over a replace-all endpoint, so each account is read
    immediately before its own write, one account at a time — never from a
    snapshot of every alias taken once up front. See
    api_client.put_crm_source_mappings for the cross-process limit that
    remains.
    """
    from src.services import api_client as api
    from src.utils.crm_source_mapping_ui import merge_source_mapping

    accounts_written = rules_added = 0

    for accountid, (account_name, tokens) in group_matched_by_account(plan.matched).items():
        # This account's OWN mappings, uncached. get_crm_aliases() is scoped to
        # project customers and cached for 300s behind an SWR TTL; either would
        # hand this loop a set that is missing rules the replace-all PUT then
        # deletes.
        mappings = list(api.get_crm_account_source_mappings(accountid) or [])
        account_name = next(
            (str(m.get("crm_account_name")).strip() for m in mappings
             if str(m.get("crm_account_name") or "").strip()),
            account_name,
        )
        added_here = 0
        for token in tokens:
            mappings, changed = merge_source_mapping(mappings, {
                "data_source": DATA_SOURCE,
                "match_method": MATCH_METHOD,
                "match_value": token,
                "enabled": True,
                "priority": 100,
                "notes": "backup-musteri-isim.xlsx seed",
            })
            added_here += int(changed)
        if not added_here:
            continue
        # The save endpoint replaces the account's whole mapping set, so the
        # union built above is what goes out.
        api.put_crm_source_mappings(
            accountid,
            crm_account_name=account_name,
            mappings=mappings,
        )
        accounts_written += 1
        rules_added += added_here

    return accounts_written, rules_added


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xlsx", help="path to backup-musteri-isim.xlsx")
    parser.add_argument("--apply", action="store_true",
                        help="write the rules; without it, only the plan is printed")
    args = parser.parse_args(argv)

    from src.services import api_client as api

    sheet_rows = load_sheet(args.xlsx)
    # Full roster for candidate-matching (must NOT be scoped to project customers —
    # see resolve_accounts()'s docstring for why that manufactures false matches).
    crm_accounts = api.get_crm_accounts() or []
    # Separately: which of those accounts are actually writable today.
    project_account_ids = {
        str(a.get("crm_accountid") or "").strip()
        for a in (api.get_crm_aliases() or [])
        if a.get("crm_accountid")
    }
    plan = resolve_accounts(sheet_rows, crm_accounts, project_account_ids)

    print(f"Sheet rows: {len(sheet_rows)}")
    print(format_report(plan))

    if not args.apply:
        print("Dry run — nothing written. Re-run with --apply to seed.")
        return 0

    accounts_written, rules_added = apply_plan(plan)
    print(f"Wrote {rules_added} rules across {accounts_written} accounts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
