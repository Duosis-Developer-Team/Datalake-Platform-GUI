"""CRM-backed customer list helpers for the GUI selector.

Customer screen list scope (product rule):
  - Include CRM accounts that have at least one sales order with ordernumber LIKE 'PRJ-%'.
  - Pin Boyner when configured as legacy pilot customer even if it has no PRJ order yet.
  - Display Boyner using the CRM account name when a Boyner CRM account exists.

Sales/finance endpoints keep their own realized-only filters (statecode IN 3,4) — see ADR-0010.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

_BOYNER_TOKEN = "boyner"
_LEGACY_PINNED_CUSTOMERS = ("Boyner",)
_LEGAL_SUFFIX_RE = re.compile(
    r"\b("
    r"a\.?ş\.?|a\.?s\.?|anonim|şirketi|sirketi|limited|ltd\.?|san\.?|tic\.?|"
    r"ticaret|holding|group|grup"
    r")\b",
    re.IGNORECASE,
)


def normalize_lookup_key(value: str) -> str:
    """Lower-case alphanumeric key for fuzzy tenant/account matching."""
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def resolve_infra_search_name(
    display_name: str,
    *,
    alias_netbox_value: Optional[str] = None,
    alias_canonical_key: Optional[str] = None,
    netbox_tenant_names: Optional[Iterable[str]] = None,
) -> str:
    """Map a CRM display name to the substring used for infra ILIKE queries."""
    if alias_netbox_value and str(alias_netbox_value).strip():
        return str(alias_netbox_value).strip()
    if alias_canonical_key and str(alias_canonical_key).strip():
        return str(alias_canonical_key).strip()
    if _BOYNER_TOKEN in (display_name or "").lower():
        return "Boyner"

    tenants = [str(t).strip() for t in (netbox_tenant_names or []) if t and str(t).strip()]
    display_key = normalize_lookup_key(display_name)
    if display_key and tenants:
        for tenant in tenants:
            tenant_key = normalize_lookup_key(tenant)
            if tenant_key and (tenant_key in display_key or display_key in tenant_key):
                return tenant

    tokens = _significant_name_tokens(display_name)
    if tokens:
        return tokens[0]
    return (display_name or "").strip()


def build_crm_project_customer_list(
    project_customer_names: Iterable[str],
    *,
    boyner_crm_name: Optional[str] = None,
    pin_legacy_customers: Iterable[str] = _LEGACY_PINNED_CUSTOMERS,
) -> list[str]:
    """Merge CRM project customers with legacy pinned entries and Boyner CRM naming."""
    names: list[str] = []
    seen: set[str] = set()

    def _add(name: str) -> None:
        cleaned = (name or "").strip()
        if not cleaned:
            return
        key = cleaned.casefold()
        if key in seen:
            return
        seen.add(key)
        names.append(cleaned)

    for name in project_customer_names:
        _add(name)

    boyner_display = (boyner_crm_name or "").strip()
    if boyner_display:
        # Replace legacy Boyner label with CRM account name when available.
        names = [boyner_display if n.casefold() == _BOYNER_TOKEN else n for n in names]
        seen = {n.casefold() for n in names}
        if boyner_display.casefold() not in seen:
            names.append(boyner_display)
            seen.add(boyner_display.casefold())
    else:
        for legacy in pin_legacy_customers:
            legacy_name = (legacy or "").strip()
            if legacy_name and legacy_name.casefold() not in seen:
                names.append(legacy_name)
                seen.add(legacy_name.casefold())

    return sorted(names, key=lambda n: n.casefold())


def _significant_name_tokens(display_name: str) -> list[str]:
    raw = (display_name or "").strip()
    if not raw:
        return []
    scrubbed = _LEGAL_SUFFIX_RE.sub(" ", raw)
    tokens = [t for t in re.split(r"\s+", scrubbed) if len(t) >= 3]
    return tokens or [raw]
