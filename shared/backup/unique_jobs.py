"""Pure, DB-free helpers for "unique job" inventory rows (Backup & Replication).

A "unique job" row is the *latest state per unique job/VPG identity* — produced
by the ``*_UNIQUE_*_LATEST`` SQL queries in
``services/datacenter-api/app/db/queries/backup.py`` (and the customer-scoped
ILIKE variants), then mapped tuple → dict by the caller (one dict key per SQL
column, matching the column name verbatim).

This module performs no further deduplication — callers hand it an
already-latest-per-id row set and get aggregation / filtering / pagination
back. Row shape is vendor-specific; the few keys each vendor is expected to
carry are documented next to ``_TYPE_FIELD`` below.

Mirrors the style of :mod:`shared.nutanix.snapshot_helpers` (plain functions
over plain dicts, no DB/network access, fully unit-testable).
"""
from __future__ import annotations

from typing import Any, Iterable

from shared.backup.policy_classification import classify_netbackup_policy

VENDOR_VEEAM = "veeam"
VENDOR_ZERTO = "zerto"
VENDOR_NETBACKUP = "netbackup"

_SUPPORTED_VENDORS = (VENDOR_VEEAM, VENDOR_ZERTO, VENDOR_NETBACKUP)

_STATUS_FIELD = "status"
_NETBACKUP_POLICY_TYPE_FIELD = "policytype"

# Which row key holds the job "type" dimension used for `by_type`, per vendor.
#   veeam      -> "type"     (job type column: VSphereReplica / Backup / ...)
#   netbackup  -> "jobtype"  (kept for shape parity across vendors — the
#                 NETBACKUP_UNIQUE_JOBS_LATEST query already filters to
#                 jobtype='BACKUP', so `by_type` degenerates to one bucket;
#                 `by_policy_type` / `by_category` below carry the meaningful
#                 NetBackup dimension instead)
#   zerto      -> None       (VPGs have no distinct "type" column; all rows
#                 collapse into a single "vpg" bucket)
_TYPE_FIELD: dict[str, str | None] = {
    VENDOR_VEEAM: "type",
    VENDOR_ZERTO: None,
    VENDOR_NETBACKUP: "jobtype",
}

# Row keys tried (in priority order) for the `platforms` filter dimension —
# whichever backup-server/host field is present and non-empty on the row wins.
# `workload` is listed last because it usually holds a coarse constant (e.g.
# Veeam's 'vm') rather than a distinguishing platform/host value.
_PLATFORM_FIELDS = (
    "source_ip", "zerto_host", "source_site", "target_site",
    "destinationmediaservername", "clientname", "workload",
)

# Row keys searched (in order, all joined) for the free-text `search` filter.
_SEARCH_FIELDS = (
    "name",
    "policyname",
    "workloaddisplayname",
    "clientname",
    "destinationmediaservername",
    "source_site",
    "target_site",
    "workload",
    "zerto_host",
    "source_ip",
)


def _normalize_status(value: Any) -> str:
    """Lowercase/trim a status value; empty/None becomes 'unknown'."""
    text = str(value).strip() if value not in (None, "") else ""
    return text.lower() if text else "unknown"


def _normalize_bucket_label(value: Any, default: str = "Unknown") -> str:
    text = str(value).strip() if value not in (None, "") else ""
    return text if text else default


def normalize_unique_job_row(row: dict) -> dict:
    """Return a shallow copy of ``row`` with its ``status`` field lowercased.

    Non-destructive — every other field keeps its original casing/value. A
    missing ``status`` key is added as ``"unknown"`` so downstream grouping
    never has to special-case its absence.
    """
    out = dict(row)
    out[_STATUS_FIELD] = _normalize_status(out.get(_STATUS_FIELD))
    return out


def normalize_unique_job_rows(rows: list[dict]) -> list[dict]:
    """Bulk version of :func:`normalize_unique_job_row`."""
    return [normalize_unique_job_row(r) for r in rows or []]


def _platform_value(row: dict) -> str:
    """First non-empty field from :data:`_PLATFORM_FIELDS` on ``row``."""
    for key in _PLATFORM_FIELDS:
        value = row.get(key)
        if value:
            return str(value)
    return ""


def aggregate_unique_jobs(rows: list[dict], vendor: str) -> dict:
    """Aggregate a unique-jobs row set into status/type (+ category/policy) totals.

    Returns::

        {
            "total_jobs": int,
            "by_status": {status: count},   # status lowercased
            "by_type": {type: count},
            # netbackup only:
            "by_category": {"image": count, "application": count},
            "by_policy_type": {policytype: count},
        }

    Unknown/empty vendors are treated like an unrecognized vendor: rows are
    still counted and status-bucketed, but `by_type` falls back to a single
    "unknown" bucket (no vendor-specific type field to read).
    """
    vendor_key = (vendor or "").strip().lower()
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    by_category: dict[str, int] = {}
    by_policy_type: dict[str, int] = {}

    type_field = _TYPE_FIELD.get(vendor_key) if vendor_key in _SUPPORTED_VENDORS else None
    total = 0
    for row in rows or []:
        if not row:
            continue
        total += 1

        status = _normalize_status(row.get(_STATUS_FIELD))
        by_status[status] = by_status.get(status, 0) + 1

        if vendor_key == VENDOR_ZERTO:
            type_label = "vpg"
        elif type_field:
            type_label = _normalize_bucket_label(row.get(type_field))
        else:
            type_label = "unknown"
        by_type[type_label] = by_type.get(type_label, 0) + 1

        if vendor_key == VENDOR_NETBACKUP:
            policy_type = _normalize_bucket_label(row.get(_NETBACKUP_POLICY_TYPE_FIELD))
            by_policy_type[policy_type] = by_policy_type.get(policy_type, 0) + 1
            category = classify_netbackup_policy(row.get(_NETBACKUP_POLICY_TYPE_FIELD))
            by_category[category] = by_category.get(category, 0) + 1

    result: dict[str, Any] = {
        "total_jobs": total,
        "by_status": by_status,
        "by_type": by_type,
    }
    if vendor_key == VENDOR_NETBACKUP:
        result["by_category"] = by_category
        result["by_policy_type"] = by_policy_type
    return result


def filter_unique_job_rows(
    rows: list[dict],
    *,
    search: str = "",
    statuses: Iterable[str] | None = None,
    types: Iterable[str] | None = None,
    policy_types: Iterable[str] | None = None,
    categories: Iterable[str] | None = None,
    platforms: Iterable[str] | None = None,
) -> list[dict]:
    """Multi-value filter over a unique-jobs row set (Grafana-style semantics).

    Every filter dimension is optional/multi-value: a row matches a dimension
    if its value is in the selected set (or the set is empty/None, meaning "no
    filter" for that dimension). All dimensions are AND-ed together.
    """
    out = list(rows or [])

    q = (search or "").strip().lower()
    if q:
        out = [
            r for r in out
            if q in " ".join(str(r.get(k) or "") for k in _SEARCH_FIELDS).lower()
        ]

    status_set = {_normalize_status(s) for s in statuses or [] if s not in (None, "")}
    if status_set:
        out = [r for r in out if _normalize_status(r.get(_STATUS_FIELD)) in status_set]

    type_set = {str(t) for t in types or [] if t not in (None, "")}
    if type_set:
        out = [
            r for r in out
            if str(r.get("type") if r.get("type") is not None else r.get("jobtype") or "") in type_set
        ]

    policy_type_set = {str(p) for p in policy_types or [] if p not in (None, "")}
    if policy_type_set:
        out = [r for r in out if str(r.get(_NETBACKUP_POLICY_TYPE_FIELD) or "") in policy_type_set]

    category_set = {str(c).lower() for c in categories or [] if c not in (None, "")}
    if category_set:
        out = [
            r for r in out
            if classify_netbackup_policy(r.get(_NETBACKUP_POLICY_TYPE_FIELD)) in category_set
        ]

    platform_set = {str(p) for p in platforms or [] if p not in (None, "")}
    if platform_set:
        out = [r for r in out if _platform_value(r) in platform_set]

    return out


def paginate_rows(items: list[Any], page: int, page_size: int) -> dict:
    """Slice ``items`` into a page; ``page_size`` is capped to [1, 200].

    Returns ``{"items": [...], "total": int, "page": int, "page_size": int}``.
    """
    try:
        page_int = int(page or 1)
    except (TypeError, ValueError):
        page_int = 1
    page_int = max(1, page_int)

    try:
        page_size_int = int(page_size or 50)
    except (TypeError, ValueError):
        page_size_int = 50
    page_size_int = max(1, min(200, page_size_int))

    safe_items = items or []
    total = len(safe_items)
    start = (page_int - 1) * page_size_int
    return {
        "items": safe_items[start:start + page_size_int],
        "total": total,
        "page": page_int,
        "page_size": page_size_int,
    }
