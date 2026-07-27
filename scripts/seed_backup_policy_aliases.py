"""Seed backup_netbackup alias rules from backup-musteri-isim.xlsx.

The naming standard (shared/customer/backup_policy.py) derives a customer's
policy prefix in 87% of live cases, but 27% of those match more than one CRM
account — 'avro' addresses both AVROMED and AVRORA LLC. The spreadsheet
resolves exactly those, so it is loaded as ground truth alongside the
heuristic rather than instead of it.

Idempotent: rules already present are not rewritten. Rows that cannot be
resolved to a CRM account are reported by name, never dropped in silence —
a silent skip is indistinguishable from a successful seed.

Usage:
    ./.venv/bin/python -m scripts.seed_backup_policy_aliases <xlsx> [--apply]

Without --apply it prints the plan and writes nothing.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass, field

from shared.customer.unmapped_classifier import norm

SHEET_NAME = "AD-KARŞILIĞI"
DATA_SOURCE = "backup_netbackup"
MATCH_METHOD = "prefix"

_HEADER_CELLS = {"musteri adi", "policy adi"}


@dataclass
class SeedPlan:
    matched: list[tuple[str, str, list[str]]] = field(default_factory=list)
    not_found: list[str] = field(default_factory=list)
    ambiguous: list[tuple[str, list[str]]] = field(default_factory=list)


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


def resolve_accounts(sheet_rows, crm_accounts) -> SeedPlan:
    """Match short sheet names to full CRM legal names.

    Uses the same Turkish folding as the classifier so this path and the
    runtime path cannot disagree about what two names being "the same" means.
    """
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
            plan.matched.append((accountid, name, tokens))
    return plan


def format_report(plan: SeedPlan) -> str:
    lines = [
        f"Matched:    {len(plan.matched)} customers",
        f"Not found:  {len(plan.not_found)} customers",
        f"Ambiguous:  {len(plan.ambiguous)} customers",
        "",
    ]
    if plan.not_found:
        lines.append("No CRM account for these sheet names:")
        lines += [f"  - {n}" for n in plan.not_found]
        lines.append("")
    if plan.ambiguous:
        lines.append("These sheet names match more than one CRM account (pick one by hand):")
        for sheet_name, names in plan.ambiguous:
            lines.append(f"  - {sheet_name}: {', '.join(names)}")
        lines.append("")
    return "\n".join(lines)


def load_sheet(path: str) -> list[tuple[str, list[str]]]:
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[SHEET_NAME]
    return parse_sheet_rows(
        (row[0], row[1]) for row in ws.iter_rows(values_only=True) if row and len(row) >= 2
    )


def apply_plan(plan: SeedPlan) -> tuple[int, int]:
    """Write the matched rules. Returns (accounts_written, rules_added)."""
    from src.services import api_client as api
    from src.utils.crm_source_mapping_ui import find_alias, merge_source_mapping

    aliases = api.get_crm_aliases() or []
    accounts_written = rules_added = 0

    for accountid, account_name, tokens in plan.matched:
        alias = find_alias(aliases, accountid)
        mappings = list((alias or {}).get("source_mappings") or [])
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
            crm_account_name=(alias or {}).get("crm_account_name") or account_name,
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
    crm_accounts = [
        {"name": a.get("crm_account_name"), "accountid": a.get("crm_accountid")}
        for a in (api.get_crm_aliases() or [])
    ]
    plan = resolve_accounts(sheet_rows, crm_accounts)

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
