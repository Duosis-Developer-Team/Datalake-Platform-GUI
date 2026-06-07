"""Map CRM product sales lines to GUI service categories."""
from __future__ import annotations

from typing import Any


def map_service_sales_lines(
    raw_lines: list[dict[str, Any]],
    product_mapping: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    agg: dict[str, dict[str, Any]] = {}
    for line in raw_lines or []:
        pid = str(line.get("productid") or "")
        mapping = product_mapping.get(pid) or {}
        code = (mapping.get("category_code") if mapping else None) or "unmatched"
        label = (mapping.get("category_label") if mapping else None) or "Unmatched"
        key = str(code)
        bucket = agg.setdefault(
            key,
            {
                "service_code": code,
                "service_label": label,
                "amount_tl": 0.0,
            },
        )
        bucket["amount_tl"] += float(line.get("amount_tl") or 0.0)
    return sorted(agg.values(), key=lambda r: -float(r.get("amount_tl") or 0.0))
