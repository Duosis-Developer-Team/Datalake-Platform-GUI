"""Guard: sold-by-category must prefer CRM line UoM over mapping view resource_unit."""

from __future__ import annotations

from app.db.queries import crm_sales


def test_sales_sold_by_category_coalesce_prefers_uomid_first():
    sql = crm_sales.SALES_SOLD_BY_CATEGORY
    assert "NULLIF(TRIM(d.uomid_name), '')" in sql
    assert "NULLIF(TRIM(m.resource_unit), '')" in sql
    pos_u = sql.index("d.uomid_name")
    pos_m = sql.index("m.resource_unit")
    assert pos_u < pos_m
