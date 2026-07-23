"""Canonical colocation occupancy module — the single source of truth for
used/free rack-U. Verified against prod (over_capacity=0) on 2026-07-23."""
from shared.colocation import occupancy as occ


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self.executed = None

    def execute(self, sql, params=None):
        self.executed = (sql, params)

    def fetchall(self):
        return self._rows


def test_sql_uses_current_tables_only():
    sql = occ.OCCUPANCY_SQL.lower()
    assert "discovery_netbox_inventory_device" in sql
    assert "loki_device_types" in sql
    assert "discovery_loki_rack" in sql
    assert "discovery_loki_location" in sql
    # The stale / nonexistent tables must never appear.
    assert "loki_devices" not in sql
    assert "discovery_loki_racks" not in sql
    assert "discovery_netbox_inventory_device_type" not in sql


def test_sql_scopes_by_name_and_site_and_front_face():
    sql = occ.OCCUPANCY_SQL.lower()
    assert "s.rack_name = r.rack_name" in sql
    assert "coalesce(s.site_name, '') = coalesce(r.site_name, '')" in sql
    assert "in ('front', '')" in sql
    assert "coalesce(l.parent_name, l.name)" in sql  # DC label


def test_row_to_dict_maps_and_coerces():
    row = ("R1", "116", "DC13", "DH1", 47, 35, 12, ["Boyner", "Bulutistan - Linux TEAM"])
    d = occ.row_to_dict(row)
    assert d == {
        "rack_id": "R1", "rack_name": "116", "dc": "DC13", "hall": "DH1",
        "capacity_u": 47, "used_u": 35, "free_u": 12,
        "tenants": ["Boyner", "Bulutistan - Linux TEAM"],
    }


def test_row_to_dict_handles_nulls():
    d = occ.row_to_dict(("R2", "117", "DC13", None, 47, None, None, None))
    assert d["used_u"] == 0 and d["free_u"] == 0 and d["tenants"] == []


def test_occupancy_rows_executes_with_dc_pattern():
    cur = _FakeCursor([("R1", "116", "DC13", "DH1", 47, 35, 12, ["Boyner"])])
    rows = occ.occupancy_rows(cur, dc_pattern="%DC13%")
    assert cur.executed[1] == {"dc_pattern": "%DC13%"}
    assert rows[0]["rack_name"] == "116" and rows[0]["free_u"] == 12


def test_aggregate_by_dc_rolls_up():
    rows = [
        {"dc": "DC13", "capacity_u": 47, "used_u": 35, "free_u": 12},
        {"dc": "DC13", "capacity_u": 47, "used_u": 20, "free_u": 27},
        {"dc": "DC14", "capacity_u": 45, "used_u": 10, "free_u": 35},
    ]
    agg = occ.aggregate_by_dc(rows)
    assert agg["DC13"] == {"total_u": 94, "used_u": 55, "free_u": 39, "rack_count": 2}
    assert agg["DC14"] == {"total_u": 45, "used_u": 10, "free_u": 35, "rack_count": 1}


def test_is_internal_tenant():
    assert occ.is_internal_tenant("Bulutistan - Virtualization")
    assert occ.is_internal_tenant("Bulut Broker")
    assert occ.is_internal_tenant("CPE-Tenant")
    assert not occ.is_internal_tenant("AytemizBank")
    assert not occ.is_internal_tenant("Boyner")
    assert not occ.is_internal_tenant("")
