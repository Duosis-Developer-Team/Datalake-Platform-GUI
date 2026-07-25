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


def test_sql_tenants_filter_is_u_range_bounded():
    """The tenants ARRAY_AGG must only count devices within the rack's own U
    range, so a device positioned outside the rack height (which already
    contributes 0 to used_u) cannot list a phantom tenant."""
    sql = occ.OCCUPANCY_SQL.lower()
    assert "array_agg(distinct s.tenant_name)" in sql
    # The bare U-range guard appears 3x total: used_u's COUNT FILTER, free_u's
    # COUNT FILTER, and (new) the tenants ARRAY_AGG FILTER.
    assert sql.count("s.u between 1 and r.capacity_u") >= 3
    # And specifically: within the tenants FILTER clause (after the
    # ARRAY_AGG), the U-range guard is AND-ed onto the existing tenant-name
    # conditions rather than replacing them.
    tenants_clause = sql.split("array_agg(distinct s.tenant_name)", 1)[1]
    assert "tenant_name is not null" in tenants_clause
    assert "and s.u between 1 and r.capacity_u" in tenants_clause


def test_row_to_dict_maps_and_coerces():
    row = ("R1", "116", "DC13", "DH1", 47, 35, 12, ["Boyner", "Bulutistan - Linux TEAM"], "ISTANBUL")
    d = occ.row_to_dict(row)
    assert d == {
        "rack_id": "R1", "rack_name": "116", "dc": "DC13", "hall": "DH1",
        "capacity_u": 47, "used_u": 35, "free_u": 12,
        "tenants": ["Boyner", "Bulutistan - Linux TEAM"], "site_name": "ISTANBUL",
    }


def test_row_to_dict_handles_nulls():
    d = occ.row_to_dict(("R2", "117", "DC13", None, 47, None, None, None, None))
    assert d["used_u"] == 0 and d["free_u"] == 0 and d["tenants"] == []
    assert d["site_name"] is None


def test_occupancy_rows_executes_with_dc_pattern():
    cur = _FakeCursor([("R1", "116", "DC13", "DH1", 47, 35, 12, ["Boyner"])])
    rows = occ.occupancy_rows(cur, dc_pattern="%DC13%")
    assert cur.executed[1] == {"dc_pattern": "%DC13%"}
    assert rows[0]["rack_name"] == "116" and rows[0]["free_u"] == 12


def test_occupancy_rows_dedupes_duplicate_physical_racks():
    """discovery_loki_rack has multiple rows for one physical rack (234 rows /
    188 unique name+site). The device->rack join is by (rack_name, site_name)
    only, so each duplicate re-counts the SAME devices (used_u=36 three times).
    occupancy_rows must collapse them to ONE physical rack so used/free U are
    not inflated; a same-name rack at a *different* site stays separate."""
    cur = _FakeCursor([
        # same physical rack "102"/ISTANBUL, 3 duplicate rows (differing dc + cap)
        ("id-a", "102", "DH3", "hallA", 52, 36, 16, ["Boyner"], "ISTANBUL"),
        ("id-b", "102", "DC13", "hallB", 47, 36, 11, ["Boyner"], "ISTANBUL"),
        ("id-c", "102", "DC13", "hallC", 47, 36, 11, ["Boyner"], "ISTANBUL"),
        # genuinely different rack: same name, different site -> kept separate
        ("id-d", "102", "AZ11", "hallD", 48, 16, 32, ["A101"], "ANKARA"),
    ])
    rows = occ.occupancy_rows(cur, dc_pattern=None)
    assert len(rows) == 2  # ISTANBUL/102 collapsed, ANKARA/102 kept
    ist = next(r for r in rows if (r.get("site_name") or "") == "ISTANBUL")
    assert ist["used_u"] == 36            # NOT 108 (3x)
    assert ist["capacity_u"] == 52        # max capacity among duplicates
    assert ist["free_u"] == 16            # 52 - 36
    assert ist["dc"] == "DC13"            # most-common dc among duplicates
    # the aggregate must reflect real physical capacity, not the fan-out
    agg = occ.aggregate_by_dc(rows)
    assert sum(a["used_u"] for a in agg.values()) == 36 + 16
    assert sum(a["total_u"] for a in agg.values()) == 52 + 48


def test_occupancy_rows_dedupe_unions_tenants_across_duplicates():
    cur = _FakeCursor([
        ("id-a", "9", "DC13", "h", 47, 20, 27, ["Boyner"], "IST"),
        ("id-b", "9", "DC13", "h", 47, 20, 27, ["AytemizBank"], "IST"),
    ])
    rows = occ.occupancy_rows(cur, dc_pattern=None)
    assert len(rows) == 1
    assert sorted(rows[0]["tenants"]) == ["AytemizBank", "Boyner"]


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


# --- Exact per-(rack, tenant) occupancy (used by the customer footprint) ---

def test_tenant_occupancy_sql_counts_distinct_u_per_tenant():
    sql = occ.TENANT_OCCUPANCY_SQL.lower()
    # current tables only
    assert "discovery_netbox_inventory_device" in sql
    assert "loki_device_types" in sql
    assert "discovery_loki_rack" in sql
    assert "in ('front', '')" in sql
    # exact per-tenant measurement: COUNT(DISTINCT u)
    assert "count(distinct u)" in sql
    # device-side aggregation FIRST (grouped by rack+site+tenant) — no rack join
    # at this step, so a non-unique (rack_name, site_name) cannot fan out the U.
    assert "group by rack_name, site_name, tenant_name" in sql
    # untagged devices excluded at source so they never inflate a customer
    assert "tenant_name is not null" in sql
    # FAN-OUT GUARD: the rack side is de-duplicated to one row per (name, site)
    # before it is joined on, so a device's U is never multiplied.
    assert "max(capacity_u)" in sql
    assert "group by rack_name, site_name\n" in sql or "group by rack_name, site_name " in sql
    # stale / nonexistent tables must never appear
    assert "loki_devices" not in sql
    assert "discovery_loki_racks" not in sql


def test_tenant_occupancy_rows_executes_with_dc_pattern():
    cur = _FakeCursor([("DC13", "116", "Boyner", 20)])
    rows = occ.tenant_occupancy_rows(cur, dc_pattern="%DC13%")
    assert cur.executed[1] == {"dc_pattern": "%DC13%"}
    assert rows[0] == {"dc": "DC13", "rack_name": "116", "tenant_name": "Boyner", "used_u": 20}


def test_tenant_occupancy_row_coerces_null_used_u():
    cur = _FakeCursor([("DC13", "116", "Boyner", None)])
    rows = occ.tenant_occupancy_rows(cur, dc_pattern=None)
    assert rows[0]["used_u"] == 0
