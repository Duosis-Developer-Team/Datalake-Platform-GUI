"""Guard: raw-by-product DC sold query surfaces line-level UoM and avoids cross-DB joins."""

from __future__ import annotations

from app.db.queries import crm_potential as crm_q


def test_dc_sold_raw_by_product_uses_line_uomid_first():
    sql = crm_q.DC_SOLD_RAW_BY_PRODUCT_FOR_DC
    assert "NULLIF(TRIM(d.uomid_name), '')" in sql
    assert "GROUP BY d.productid" in sql


def test_no_cross_db_references_in_potential_queries():
    """After ADR-0012/0013, datalake-side queries must not reference webui-db tables."""
    forbidden = ("v_gui_crm_product_mapping", "discovery_crm_customer_alias")
    for sql_name in (
        "DC_SALES_POTENTIAL",
        "DC_POTENTIAL_SUMMARY",
        "DC_NUTANIX_CLUSTER_CAPACITY",
        "DC_SOLD_RAW_BY_PRODUCT_FOR_DC",
        "DC_TENANT_VALUES",
    ):
        sql = getattr(crm_q, sql_name)
        for token in forbidden:
            assert token not in sql, f"{sql_name} must not reference {token}"
