"""Datalake coverage logic — derive Location (DC) from names, per-row status/reason.

The coverage tables (`hmdl.hmdl_datalake_coverage_cluster` / `_ibm_host`) carry no
`dc_code` column, so the Location is derived from the entity name:
  - cluster_name embeds the DC as a token, e.g. ``DC13-G3-CLS`` (prefix).
  - IBM servername embeds the DC inline, e.g. ``G2HV12DC13`` (suffix).
A single regex covers both. Names with no recognizable DC token fall under "Diğer"
(e.g. ``Mg-CLS``, ``PRISM-…``, ``ISTAHV-…``).

The per-row ``status`` collapses the (collected, expected, is_live) triple into a
single label, and ``reason`` is a human-readable Turkish explanation. For *missing*
rows (expected but not collected) the reason is enriched with unreachable collector
targets for the same DC + platform (from `hmdl.hmdl_datalake_coverage_target`), which
is the actionable "why can't I collect this" signal.
"""

from __future__ import annotations

import re
from typing import Any

# coverage `source` value → `platform` value in the target table.
SOURCE_PLATFORM = {"vmware": "VmWare", "nutanix": "Nutanix"}
IBM_PLATFORM = "IBM-HMC"

_DC_RE = re.compile(r"(DC\d+|AZ\d+|ICT\d+|UZ\d+)", re.IGNORECASE)


def derive_dc(name: str | None) -> str:
    """Best-effort DC/Location code from a cluster or server name."""
    if not name:
        return "Diğer"
    m = _DC_RE.search(name)
    return m.group(1).upper() if m else "Diğer"


def row_status(collected: bool, expected: bool, is_live: bool) -> str:
    """Collapse the coverage triple into a single status label."""
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
        return dt.strftime("%d.%m.%Y")
    except Exception:
        return str(dt)


def reason_text(status: str, last_collected: Any, target_issues: list[dict]) -> str:
    """Human-readable Turkish reason for a coverage row."""
    if status == "live":
        return "Canlı"
    if status == "stale":
        d = _fmt_date(last_collected)
        return f"Bayat — son veri {d}" if d else "Bayat"
    if status == "extra":
        return "Envanter dışı (toplanıyor)"
    if status == "missing":
        if target_issues:
            n = len(target_issues)
            statuses = ", ".join(sorted({(t.get("check_status") or "erişim yok") for t in target_issues}))
            dc = target_issues[0].get("dc_code") or ""
            plat = target_issues[0].get("platform") or ""
            return f"Toplanmıyor — {dc}/{plat}: {n} collector erişilemiyor ({statuses})"
        return "Toplanmıyor (envanterde var, veri gelmiyor)"
    return "—"


def empty_bucket() -> dict[str, int]:
    return {"total": 0, "collected": 0, "missing": 0, "live": 0}


def tally(bucket: dict[str, int], collected: bool, expected: bool, is_live: bool) -> None:
    bucket["total"] += 1
    if collected:
        bucket["collected"] += 1
    if expected and not collected:
        bucket["missing"] += 1
    if is_live:
        bucket["live"] += 1
