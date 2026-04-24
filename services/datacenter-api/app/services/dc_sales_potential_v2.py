"""
Datacenter sales potential v2 — 80%% sellable ceiling vs realized CRM sales (ADR-0010).

Capacity proxy: latest Nutanix cluster metrics per DC name pattern.
Sold proxy: CRM sales order lines for customers mapped to VMs in the DC (rolling 12 months).
"""
from __future__ import annotations

from typing import Any

from app.db.queries import crm_potential as crm_q

SELLABLE_LIMIT_PCT = 80.0


def _resource_view(total: float, sold: float, unit_price: float) -> dict[str, Any]:
    if total and total > 0:
        sold_pct = min(100.0, max(0.0, sold / total * 100.0))
        rem_pct = max(0.0, SELLABLE_LIMIT_PCT - sold_pct)
        rem_qty = rem_pct / 100.0 * total
    else:
        if sold > 0:
            sold_pct = 100.0
            rem_pct = 0.0
            rem_qty = 0.0
        else:
            sold_pct = 0.0
            rem_pct = SELLABLE_LIMIT_PCT
            rem_qty = 0.0
    pot = rem_qty * float(unit_price or 0.0)
    return {
        "total_capacity": float(total or 0.0),
        "sold_qty": float(sold or 0.0),
        "sold_pct_of_ceiling": round(sold_pct, 2),
        "remaining_sellable_pct": round(rem_pct, 2),
        "remaining_sellable_qty": round(rem_qty, 4),
        "catalog_unit_price_tl": float(unit_price or 0.0),
        "potential_revenue_tl": round(pot, 2),
    }


def compute_sales_potential_v2(cur, dc_code: str) -> dict[str, Any]:
    dc_pattern = f"%{dc_code}%"

    cur.execute(crm_q.DC_NUTANIX_CLUSTER_CAPACITY, (dc_pattern,))
    cap = cur.fetchone() or (0.0, 0.0)
    total_cpu = float(cap[0] or 0.0)
    total_ram_gb = float(cap[1] or 0.0)

    cur.execute(crm_q.DC_SOLD_VIRTUALIZATION_FOR_DC, (dc_pattern,))
    sold_row = cur.fetchone() or (0.0, 0.0)
    sold_vcpu = float(sold_row[0] or 0.0)
    sold_ram_gb = float(sold_row[1] or 0.0)

    cur.execute(crm_q.DC_CATALOG_AVG_UNIT_PRICE, ("%vcpu%",))
    pr_cpu = float((cur.fetchone() or (0.0,))[0] or 0.0)
    cur.execute(crm_q.DC_CATALOG_AVG_UNIT_PRICE, ("%gb%",))
    pr_ram = float((cur.fetchone() or (0.0,))[0] or 0.0)

    cpu_block = _resource_view(total_cpu, sold_vcpu, pr_cpu)
    ram_block = _resource_view(total_ram_gb, sold_ram_gb, pr_ram)

    rem_cpu = cpu_block["remaining_sellable_pct"]
    rem_ram = ram_block["remaining_sellable_pct"]
    if total_cpu > 0 and total_ram_gb > 0:
        general_remaining_pct = round(min(rem_cpu, rem_ram), 2)
    elif total_cpu > 0:
        general_remaining_pct = round(rem_cpu, 2)
    elif total_ram_gb > 0:
        general_remaining_pct = round(rem_ram, 2)
    else:
        general_remaining_pct = round(min(rem_cpu, rem_ram), 2)

    total_potential_tl = float(cpu_block["potential_revenue_tl"]) + float(ram_block["potential_revenue_tl"])

    cur.execute(crm_q.DC_SOLD_BY_CATEGORY_FOR_DC, (dc_pattern,))
    cols = [d[0] for d in cur.description]
    per_category: list[dict[str, Any]] = []
    for row in cur.fetchall() or []:
        rec = dict(zip(cols, row))
        cc = str(rec.get("category_code") or "").lower()
        if cc.startswith("virt"):
            rec["remaining_sellable_pct"] = general_remaining_pct
        else:
            rec["remaining_sellable_pct"] = None
        per_category.append(rec)

    return {
        "dc_code": dc_code,
        "sellable_limit_pct": SELLABLE_LIMIT_PCT,
        "general_remaining_pct": general_remaining_pct,
        "potential_revenue_tl": round(total_potential_tl, 2),
        "per_resource": {
            "cpu": cpu_block,
            "ram": ram_block,
            "storage": {
                "total_capacity": 0.0,
                "sold_qty": 0.0,
                "remaining_sellable_pct": None,
                "catalog_unit_price_tl": 0.0,
                "potential_revenue_tl": 0.0,
            },
            "backup_gb": {
                "total_capacity": 0.0,
                "sold_qty": 0.0,
                "remaining_sellable_pct": None,
                "catalog_unit_price_tl": 0.0,
                "potential_revenue_tl": 0.0,
            },
            "rack_u": {
                "total_capacity": 0.0,
                "sold_qty": 0.0,
                "remaining_sellable_pct": None,
                "catalog_unit_price_tl": 0.0,
                "potential_revenue_tl": 0.0,
            },
            "power_kw": {
                "total_capacity": 0.0,
                "sold_qty": 0.0,
                "remaining_sellable_pct": None,
                "catalog_unit_price_tl": 0.0,
                "potential_revenue_tl": 0.0,
            },
        },
        "per_category": per_category,
    }
