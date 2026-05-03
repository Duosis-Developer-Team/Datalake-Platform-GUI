"""Guard: raw-by-product sold query must surface line-level UoM (uomid_name).

After ADR-0012/0013 the cross-DB mapping JOIN moved into Python; this query
only emits raw sold quantities by productid + resource_unit.
"""

from __future__ import annotations

from app.db.queries import crm_sales


def test_sales_sold_raw_by_product_uses_uomid_first():
    sql = crm_sales.SALES_SOLD_RAW_BY_PRODUCT
    assert "NULLIF(TRIM(d.uomid_name), '')" in sql
    assert "GROUP BY d.productid" in sql
    # No cross-DB references (mapping is resolved in webui-db / Python)
    assert "v_gui_crm_product_mapping" not in sql
    assert "discovery_crm_customer_alias" not in sql
