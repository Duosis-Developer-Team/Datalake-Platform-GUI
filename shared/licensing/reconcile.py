"""Reconcile detected licensed-OS counts against CRM sold counts (TASK-81)."""
from __future__ import annotations

FAMILY_TO_SOLD_CATEGORIES: dict[str, tuple[str, ...]] = {
    "rhel": ("license_redhat",),
    "suse": ("license_suse", "mgmt_os_sap"),
    "windows": ("license_microsoft_spla", "license_microsoft_csp", "mgmt_os_windows"),
}
_LABELS = {"rhel": "RHEL", "suse": "SUSE", "windows": "Windows"}


def _sold_qty(row: dict) -> float:
    q = row.get("entitled_qty")
    if q is None:
        q = row.get("sold_qty")
    return float(q or 0)


def reconcile(detected: dict[str, int], sold_rows: list[dict]) -> list[dict]:
    """Return one row per licensed family: detected vs sold vs delta (=detected-sold)."""
    sold_by_key: dict[str, float] = {}
    for r in sold_rows or []:
        key = str(r.get("page_key") or r.get("category_code") or "")
        if key:
            sold_by_key[key] = sold_by_key.get(key, 0.0) + _sold_qty(r)

    out: list[dict] = []
    for family, keys in FAMILY_TO_SOLD_CATEGORIES.items():
        det = int(detected.get(family, 0) or 0)
        sold = int(round(sum(sold_by_key.get(k, 0.0) for k in keys)))
        out.append({
            "family": family, "label": _LABELS[family],
            "detected": det, "sold": sold, "delta": det - sold,
        })
    return out
