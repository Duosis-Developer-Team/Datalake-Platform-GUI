"""Guard: the colocation/rack SQL must not reference stale or nonexistent tables."""
from app.db.queries import crm_potential
from shared.colocation import occupancy as occ

_FORBIDDEN = ("discovery_loki_racks", "discovery_netbox_inventory_device_type", "loki_devices")


def test_shared_occupancy_sql_has_no_forbidden_tables():
    sql = occ.OCCUPANCY_SQL.lower()
    for bad in _FORBIDDEN:
        assert bad not in sql, f"occupancy SQL references forbidden table {bad}"


def test_crm_potential_has_no_forbidden_rack_tables():
    # Concatenate every module-level SQL string constant and scan it.
    blob = " ".join(
        v for v in vars(crm_potential).values() if isinstance(v, str)
    ).lower()
    for bad in _FORBIDDEN:
        assert bad not in blob, f"crm_potential still references forbidden table {bad}"
