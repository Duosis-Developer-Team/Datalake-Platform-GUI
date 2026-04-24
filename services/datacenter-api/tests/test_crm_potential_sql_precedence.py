"""Guard: DC CRM potential queries must prefer sales line uomid over mapping.resource_unit."""

from __future__ import annotations

from app.db.queries import crm_potential as crm_q


def test_dc_sold_by_category_prefers_uomid_first():
    sql = crm_q.DC_SOLD_BY_CATEGORY_FOR_DC
    assert "NULLIF(TRIM(d.uomid_name), '')" in sql
    pos_u = sql.index("d.uomid_name")
    pos_m = sql.index("m.resource_unit")
    assert pos_u < pos_m


def test_dc_sold_virtualization_unit_coalesce_orders_uomid_first():
    sql = crm_q.DC_SOLD_VIRTUALIZATION_FOR_DC
    assert "NULLIF(TRIM(d.uomid_name), '')" in sql
    assert "m.resource_unit" in sql
