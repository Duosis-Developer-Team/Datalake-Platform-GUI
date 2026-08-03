"""Datalake coverage logic — derive Location (DC) from names, per-row status/reason.

The coverage tables (`hmdl.hmdl_datalake_coverage_cluster` / `_ibm_host`) carry
`dc_code`, but readers still fall back to name parsing when it is UNKNOWN.
The per-row ``status`` collapses the (collected, expected, is_live) triple into a
single label (plus ``offline`` when NetBox says so), and ``reason`` is a
human-readable Turkish explanation. For *missing* rows the reason is enriched
with unreachable collector targets. Orphan clusters also carry
``unmatched_reason`` explaining why no parent was assigned.
"""

from __future__ import annotations

import re
from typing import Any

# coverage `source` value → `platform` value in the target table.
SOURCE_PLATFORM = {"vmware": "VmWare", "nutanix": "Nutanix"}
IBM_PLATFORM = "IBM-HMC"

_DC_RE = re.compile(r"(DC\d+|AZ\d+|ICT\d+|UZ\d+)", re.IGNORECASE)

UNMATCHED_REASON_LABELS = {
    "unknown_dc": "DC bilinmiyor",
    "no_hint": "Parent ipucu yok",
    "ambiguous": "Birden fazla vCenter, hangisi belirsiz",
    "unresolved_parent": "Parent çözülemedi",
    "no_collector": "Envanterde var, collector yok",
}


def derive_dc(name: str | None) -> str:
    """Best-effort DC/Location code from a cluster or server name."""
    if not name:
        return "Diğer"
    m = _DC_RE.search(name)
    return m.group(1).upper() if m else "Diğer"


def row_status(
    collected: bool, expected: bool, is_live: bool, *, is_offline: bool = False
) -> str:
    """Collapse the coverage triple into a single status label."""
    if is_offline:
        return "offline"
    if expected and collected:
        return "live" if is_live else "stale"
    if expected and not collected:
        return "missing"
    if collected and not expected:
        return "extra"
    return "unknown"


def _fmt_date(dt: Any) -> str | None:
    if dt is None:
        return None
    try:
        # Include clock so "today but outside the live window" is obvious.
        if hasattr(dt, "hour"):
            return dt.strftime("%d.%m.%Y %H:%M")
        return dt.strftime("%d.%m.%Y")
    except Exception:
        return str(dt)


def reason_text(
    status: str,
    last_collected: Any,
    target_issues: list[dict],
    *,
    source: str | None = None,
) -> str:
    """Human-readable Turkish reason for a coverage row."""
    if status == "live":
        return "Canlı"
    if status == "offline":
        return "Offline (envanterde kapalı)"
    if status == "stale":
        d = _fmt_date(last_collected)
        return f"Bayat — son veri {d}" if d else "Bayat"
    if status == "extra":
        return "Envanter dışı (toplanıyor)"
    if status == "missing":
        if (source or "").lower() == "ibm":
            return "Envanterde var, collector yok"
        if target_issues:
            n = len(target_issues)
            statuses = ", ".join(
                sorted({(t.get("check_status") or "erişim yok") for t in target_issues})
            )
            dc = target_issues[0].get("dc_code") or ""
            plat = target_issues[0].get("platform") or ""
            return f"Toplanmıyor — {dc}/{plat}: {n} collector erişilemiyor ({statuses})"
        return "Toplanmıyor (envanterde var, veri gelmiyor)"
    return "—"


def unmatched_reason_for(
    cluster: dict[str, Any], *, parents_in_dc: int
) -> str | None:
    """Why this cluster has no resolved parent (code for the GUI Neden column)."""
    if cluster.get("parent_key"):
        return None
    if (cluster.get("source") or "").lower() == "ibm":
        return "no_collector"
    dc = str(cluster.get("dc") or "").strip().upper()
    if not dc or dc in {"UNKNOWN", "DİĞER", "DIGER"}:
        return "unknown_dc"
    if str(cluster.get("parent_name") or "").strip():
        return "unresolved_parent"
    if cluster.get("collected") and parents_in_dc > 1:
        return "ambiguous"
    return "no_hint"


def empty_bucket() -> dict[str, int]:
    return {"total": 0, "collected": 0, "missing": 0, "live": 0, "offline": 0}


def tally(
    bucket: dict[str, int],
    collected: bool,
    expected: bool,
    is_live: bool,
    *,
    is_offline: bool = False,
) -> None:
    bucket["total"] += 1
    if is_offline:
        bucket["offline"] = bucket.get("offline", 0) + 1
        return
    if collected:
        bucket["collected"] += 1
    if expected and not collected:
        bucket["missing"] += 1
    if is_live:
        bucket["live"] += 1
