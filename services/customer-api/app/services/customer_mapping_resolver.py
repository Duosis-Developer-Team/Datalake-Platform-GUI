#!/usr/bin/env python3
"""Resolve CRM customer source mappings into query parameters and dedupe helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional, Sequence

from app.utils.customer_needle import customer_to_email_needle
from shared.customer import match as alias_match

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

# Re-exported from the shared module so there is one list, not two.
MATCH_METHODS: tuple[str, ...] = alias_match.ALL_METHODS

# Reserved pseudo-account for Bulutistan's own (internal) resources. Not a real
# CRM account; source mappings under this id identify infra owned by Bulutistan
# itself so it can be separated from real customer resources.
INTERNAL_ACCOUNT_ID: str = "INTERNAL"
INTERNAL_ACCOUNT_NAME: str = "Bulutistan (Internal)"

# Reserved pseudo-account for resources that match NO customer at all. Unlike
# INTERNAL, this account has no mapping rules — its contents are computed as the
# complement (see UnmappedService): every infra resource claimed by no customer.
# Surfaces the "orphan resource" blind spot the name-ILIKE ownership model hides.
UNMAPPED_ACCOUNT_ID: str = "UNMAPPED"
UNMAPPED_ACCOUNT_NAME: str = "Eşleşmeyen Veriler"

# UI column -> backend data_source keys
UI_COLUMN_SOURCES: dict[str, tuple[str, ...]] = {
    "virtualization": ("virtualization", "netbox_vm_customer"),
    "backup": ("backup_veeam", "backup_zerto", "backup_netbackup"),
    "physical_device": ("physical_device",),
    "storage": ("storage_ibm",),
    "s3": ("s3_icos",),
    "itsm": ("itsm_servicecore",),
    "auranotify": ("auranotify",),
}

# Reverse lookup: data_source -> UI column key
DATA_SOURCE_UI_COLUMN: dict[str, str] = {
    source: column for column, sources in UI_COLUMN_SOURCES.items() for source in sources
}

BOYNER_DEFAULT_MAPPINGS: tuple[dict[str, Any], ...] = (
    {"data_source": "physical_device", "match_method": "id_exact", "match_value": "5", "priority": 10},
    {"data_source": "virtualization", "match_method": "contains", "match_value": "Boyner", "priority": 20},
    {"data_source": "backup_veeam", "match_method": "contains", "match_value": "Boyner", "priority": 20},
    {"data_source": "backup_zerto", "match_method": "contains", "match_value": "Boyner", "priority": 20},
    {"data_source": "backup_netbackup", "match_method": "contains", "match_value": "Boyner", "priority": 20},
    {"data_source": "storage_ibm", "match_method": "contains", "match_value": "Boyner", "priority": 20},
    {"data_source": "s3_icos", "match_method": "contains", "match_value": "Boyner", "priority": 20},
    {"data_source": "itsm_servicecore", "match_method": "contains", "match_value": "boyner", "priority": 20},
    {"data_source": "netbox_vm_customer", "match_method": "exact", "match_value": "Boyner", "priority": 30},
    {"data_source": "netbox_vm_customer", "match_method": "exact", "match_value": "Boyner_Dr", "priority": 31},
    {"data_source": "netbox_vm_customer", "match_method": "exact", "match_value": "boynerdr2_boynerdr2", "priority": 32},
    {"data_source": "netbox_vm_customer", "match_method": "exact", "match_value": "Boyner_Dr_Test", "priority": 33},
    {"data_source": "netbox_vm_customer", "match_method": "exact", "match_value": "Boyner_Equinix", "priority": 34},
    {"data_source": "netbox_vm_customer", "match_method": "exact", "match_value": "Boyner_Sap", "priority": 35},
)


@dataclass(frozen=True)
class MappingRule:
    data_source: str
    match_method: str
    match_value: str
    enabled: bool = True
    priority: int = 100

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> MappingRule:
        return cls(
            data_source=str(row.get("data_source") or "").strip(),
            match_method=str(row.get("match_method") or "").strip(),
            match_value=str(row.get("match_value") or "").strip(),
            enabled=bool(row.get("enabled", True)),
            priority=int(row.get("priority") or 100),
        )


@dataclass
class ResolvedSourcePatterns:
    """Query-ready patterns grouped by infra data source."""

    ilike_by_source: dict[str, list[str]] = field(default_factory=dict)
    physical_tenant_ids: list[int] = field(default_factory=list)
    itsm_needles: list[str] = field(default_factory=list)

    def ilike_patterns(self, data_source: str) -> list[str]:
        return list(self.ilike_by_source.get(data_source) or [])

    def primary_ilike(self, data_source: str, fallback: str = "") -> str:
        patterns = self.ilike_patterns(data_source)
        if patterns:
            return patterns[0]
        return fallback

    def has_mappings(self) -> bool:
        return bool(
            self.ilike_by_source
            or self.physical_tenant_ids
            or self.itsm_needles
        )


def sql_pattern_for_match(method: str, value: str) -> tuple[str, str]:
    """Return (kind, pattern) where kind is 'ilike' or 'id_exact'.

    Thin wrapper: shared.customer.match owns the semantics so the SQL and
    in-memory paths cannot drift. Kept as a named function because existing
    call sites and tests import it.
    """
    return alias_match.sql_pattern(method, value)


def build_resolved_patterns(
    rules: Iterable[MappingRule],
    *,
    fallback_search_name: str = "",
) -> ResolvedSourcePatterns:
    """Convert enabled mapping rules into grouped SQL / ID parameters."""
    resolved = ResolvedSourcePatterns()
    sorted_rules = sorted(
        [r for r in rules if r.enabled and r.data_source and r.match_value],
        key=lambda r: (r.data_source, r.priority, r.match_value.lower()),
    )
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

    if fallback_search_name:
        fallback = fallback_search_name.strip()
        if fallback:
            for source in (
                "virtualization",
                "backup_veeam",
                "backup_zerto",
                "backup_netbackup",
                "storage_ibm",
                "s3_icos",
            ):
                if not resolved.ilike_patterns(source):
                    resolved.ilike_by_source.setdefault(source, []).append(f"%{fallback}%")
            if not resolved.itsm_needles:
                resolved.itsm_needles.append(customer_to_email_needle(fallback))

    return resolved


def dedupe_by_key(items: Sequence[dict[str, Any]], key_fn: Callable[[dict[str, Any]], str]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        key = key_fn(item)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def dedupe_vm_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return dedupe_by_key(rows, lambda r: str(r.get("name") or "").strip().lower())


def dedupe_zerto_vpgs(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return dedupe_by_key(rows, lambda r: str(r.get("name") or "").strip().lower())


def dedupe_count_rows(rows: Sequence[dict[str, Any]], key_fields: tuple[str, ...]) -> list[dict[str, Any]]:
    def _key(row: dict[str, Any]) -> str:
        return "|".join(str(row.get(f) or "").strip().lower() for f in key_fields)

    return dedupe_by_key(rows, _key)


def merge_numeric_dicts(dicts: Sequence[dict[str, float]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for d in dicts:
        for key, value in d.items():
            out[key] = out.get(key, 0.0) + float(value or 0.0)
    return out


def boyner_seed_rows(crm_accountid: str, crm_account_name: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in BOYNER_DEFAULT_MAPPINGS:
        rows.append(
            {
                "crm_accountid": crm_accountid,
                "crm_account_name": crm_account_name,
                "data_source": spec["data_source"],
                "match_method": spec["match_method"],
                "match_value": spec["match_value"],
                "display_label": spec.get("display_label"),
                "priority": spec.get("priority", 100),
                "enabled": True,
                "notes": spec.get("notes"),
                "source": "seed",
            }
        )
    return rows


def group_mappings_by_account(rows: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        account_id = str(row.get("crm_accountid") or "").strip()
        if not account_id:
            continue
        grouped.setdefault(account_id, []).append(row)
    return grouped
