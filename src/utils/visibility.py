"""Reusable visibility helpers — hide zero/empty UI values across Customer View and future pages."""

from __future__ import annotations

from typing import Any, Iterable

_EMPTY_STRINGS = frozenset({"", "-", "—", "n/a", "na", "none", "no data"})


def is_meaningful_value(value: Any, *, treat_zero_as_empty: bool = True) -> bool:
    """Return True when a scalar or collection should be shown in the UI."""
    if value is None:
        return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if not normalized or normalized in _EMPTY_STRINGS:
            return False
        return True
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) > 0
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if treat_zero_as_empty:
            if value == 0:
                return False
            if isinstance(value, float) and abs(value) < 1e-12:
                return False
        return True
    return True


def visible_kv_rows(rows: Iterable[tuple[str, Any]], *, treat_zero_as_empty: bool = True) -> list[tuple[str, Any]]:
    """Keep key-value rows whose values are meaningful."""
    return [(label, value) for label, value in rows if is_meaningful_value(value, treat_zero_as_empty=treat_zero_as_empty)]


def visible_metrics(metrics: Iterable[dict[str, Any]], *, value_key: str = "value") -> list[dict[str, Any]]:
    """Filter metric dicts (title/icon/color/value) to meaningful values only."""
    out: list[dict[str, Any]] = []
    for metric in metrics:
        if not isinstance(metric, dict):
            continue
        if is_meaningful_value(metric.get(value_key)):
            out.append(metric)
    return out


def asset_has_usage(asset: dict[str, Any] | None, *, instance_keys: tuple[str, ...] = ("vm_count", "lpar_count")) -> bool:
    """True when a compute platform dict has any provisioned instances or resources."""
    block = asset or {}
    for key in instance_keys:
        if int(block.get(key, 0) or 0) > 0:
            return True
    for key in ("cpu_total", "memory_gb", "memory_total_gb", "disk_gb"):
        if float(block.get(key, 0) or 0) > 0:
            return True
    vm_list = block.get("vm_list") or []
    if vm_list:
        return True
    return False


def backup_vendor_has_data(
    backup_totals: dict[str, Any] | None,
    backup_assets: dict[str, Any] | None,
    vendor: str,
) -> bool:
    """True when a backup vendor tab should be visible."""
    totals = backup_totals or {}
    assets = (backup_assets or {}).get(vendor, {}) or {}
    if vendor == "veeam":
        if int(totals.get("veeam_defined_sessions", 0) or 0) > 0:
            return True
        return bool(assets.get("session_types"))
    if vendor == "zerto":
        if int(totals.get("zerto_protected_vms", 0) or 0) > 0:
            return True
        if float(totals.get("zerto_provisioned_gib", 0) or 0) > 0:
            return True
        return bool(assets.get("vpgs"))
    if vendor == "netbackup":
        if float(totals.get("netbackup_pre_dedup_gib", 0) or 0) > 0:
            return True
        if float(totals.get("netbackup_post_dedup_gib", 0) or 0) > 0:
            return True
        return bool(assets)
    return False


def filter_compliance_rows_for_display(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Drop compliance rows with no entitlement, usage, or overage signal."""
    out: list[dict[str, Any]] = []
    for row in rows or []:
        status = str(row.get("status") or "").lower()
        entitled = float(row.get("entitled_qty") or 0)
        used = float(row.get("used_qty") or 0)
        overage = float(row.get("overage_qty") or 0)
        loss = float(row.get("overage_loss_tl") or 0)
        if status in ("no_sales", "no_usage") and entitled <= 0 and used <= 0 and overage <= 0:
            continue
        if entitled <= 0 and used <= 0 and overage <= 0 and loss <= 0:
            continue
        out.append(row)
    return out


def filter_efficiency_rows_for_display(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Drop sold-vs-used rows with no entitlement, usage, or overage."""
    out: list[dict[str, Any]] = []
    for row in rows or []:
        status = str(row.get("status") or "").lower()
        entitled = float(
            row.get("entitled_qty") if row.get("entitled_qty") is not None else row.get("sold_qty") or 0
        )
        used = float(row.get("used_qty") or 0)
        overage = float(row.get("overage_qty") or 0)
        if status in ("no_sales", "no_usage") and entitled <= 0 and used <= 0 and overage <= 0:
            continue
        if entitled <= 0 and used <= 0 and overage <= 0:
            continue
        out.append(row)
    return out


def count_outage_vms(vm_outage_counts: dict[str, Any] | None) -> int:
    """Total VMs with at least one outage record in the report period."""
    counts = vm_outage_counts or {}
    return sum(1 for _name, c in counts.items() if int(c or 0) > 0)


def filter_overusage_rows(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Keep rows with resource overage or unsold usage."""
    out: list[dict[str, Any]] = []
    for row in rows or []:
        status = str(row.get("status") or "").lower()
        overage = float(row.get("overage_qty") or 0)
        if status in ("over", "unsold_usage") or overage > 0:
            out.append(row)
    return out


def compute_total_overage_loss_tl(
    compliance_payload: dict[str, Any] | None = None,
    efficiency_rows: list[dict[str, Any]] | None = None,
) -> float:
    """Resolve total estimated overage loss from compliance summary or row sums."""
    summary = (compliance_payload or {}).get("summary") or {}
    total = summary.get("total_overage_loss_tl")
    if total is not None:
        try:
            return float(total)
        except (TypeError, ValueError):
            pass
    rows = (compliance_payload or {}).get("rows") or efficiency_rows or []
    over_rows = filter_overusage_rows(rows)
    source = over_rows if over_rows else rows
    return sum(float(r.get("overage_loss_tl") or 0) for r in source)


def compute_sla_compliance_pct(itsm_summary: dict[str, Any] | None) -> float | None:
    """ITSM SLA compliance rate from breach count vs total records."""
    sm = itsm_summary or {}
    total = int(sm.get("total_count") or 0)
    if total <= 0:
        return None
    breaches = int(sm.get("sla_breach_count") or 0)
    return round(max(0.0, 100.0 * (1.0 - breaches / total)), 1)
