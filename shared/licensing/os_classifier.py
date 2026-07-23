"""Deterministic guest-OS classifier for licensed-OS detection (TASK-81).

Turns a raw guest-OS signal (vSphere ``guest_full_name`` display string and/or
``guest_id`` enum, Nutanix ``guest_os``, NetBox ``custom_fields_guest_os``) into
a licensing family + a confidence level. Same rule-table style as
``shared/sellable/panel_mapping.py`` and
``datalake/collectors/Zabbix/Linux-Hana/lib/template_filter.py``: ordered,
first-match-wins, most-specific-first, lowercase substring matching.

We never fabricate a licensed guess: anything unrecognised is ``unknown`` with
confidence ``none``, surfaced honestly for manual review.

Public API:
    classify(raw, *, guest_id=None) -> OsClass
    is_licensed(family) -> bool
    LICENSED_FAMILIES: frozenset[str]
"""
from __future__ import annotations

from dataclasses import dataclass

LICENSED_FAMILIES: frozenset[str] = frozenset({"rhel", "suse", "windows"})


@dataclass(frozen=True)
class OsClass:
    family: str       # rhel | suse | windows | free | unknown
    confidence: str   # confirmed | probable | none


# Ordered, most-specific-first. Each entry: (family, substrings-any).
# A rule matches when ANY of its substrings is present in the lowercased
# haystack (display string + guest_id enum, space-joined). Windows is checked
# before the Linux families; the free families are checked last before the
# unknown fallback so a licensed vendor name always wins.
_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("windows", ("windows",)),
    ("rhel",    ("red hat", "rhel")),
    ("suse",    ("suse", "sles")),
    ("free",    (
        "ubuntu", "centos", "debian", "rocky", "almalinux", "alma linux",
        "oracle linux", "oraclelinux", "amazon linux", "amazonlinux",
        "fedora", "freebsd", "free bsd", "photon", "coreos",
    )),
)


def classify(raw: str | None, *, guest_id: str | None = None) -> OsClass:
    """Classify a guest OS. See module docstring."""
    hay = f"{raw or ''} {guest_id or ''}".strip().lower()
    if not hay:
        return OsClass("unknown", "none")
    for family, needles in _RULES:
        if any(n in hay for n in needles):
            return OsClass(family, "confirmed")
    return OsClass("unknown", "none")


def is_licensed(family: str) -> bool:
    return family in LICENSED_FAMILIES
