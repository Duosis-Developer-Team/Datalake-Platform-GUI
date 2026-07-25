"""Group EXACT per-(rack, tenant) U rows into per-customer footprints,
resolving to CRM accounts via the alias map; Bulutistan-internal excluded.

Input rows come from occupancy.tenant_occupancy_rows: one row per
(dc, rack_name, tenant_name) carrying an exact per-tenant ``used_u``
(COUNT DISTINCT U-slot), so a rack shared by two tenants splits correctly
instead of crediting each tenant with the whole rack.
"""
from shared.colocation import matching as m


def test_footprint_uses_exact_per_tenant_u_and_excludes_internal():
    rows = [
        # rack 116 shared by an external + an internal tenant: each keeps ITS OWN U
        {"dc": "DC13", "rack_name": "116", "tenant_name": "Boyner", "used_u": 20},
        {"dc": "DC13", "rack_name": "116", "tenant_name": "Bulutistan - Linux TEAM", "used_u": 15},
        {"dc": "DC13", "rack_name": "209", "tenant_name": "AytemizBank", "used_u": 27},
        {"dc": "DC14", "rack_name": "300", "tenant_name": "Bulutistan - Virtualization", "used_u": 10},
    ]
    alias = {"boyner": {"crm_accountid": "A-1", "crm_account_name": "Boyner A.Ş."}}
    out = {f["tenant"]: f for f in m.build_customer_footprint(rows, alias)}
    assert set(out) == {"Boyner", "AytemizBank"}       # internal excluded
    assert out["Boyner"]["used_u"] == 20               # ONLY Boyner's U, not the whole rack (35)
    assert out["Boyner"]["racks"] == ["116"]
    assert out["Boyner"]["crm_accountid"] == "A-1"
    assert out["Boyner"]["match_status"] == "matched"
    assert out["AytemizBank"]["used_u"] == 27
    assert out["AytemizBank"]["match_status"] == "unmatched"
    assert out["AytemizBank"]["crm_accountid"] is None


def test_footprint_sums_exact_u_across_racks():
    rows = [
        {"dc": "DC13", "rack_name": "1", "tenant_name": "Paycore", "used_u": 10},
        {"dc": "DC13", "rack_name": "2", "tenant_name": "Paycore", "used_u": 20},
    ]
    out = m.build_customer_footprint(rows, {})
    assert out[0]["tenant"] == "Paycore"
    assert sorted(out[0]["racks"]) == ["1", "2"]
    assert out[0]["used_u"] == 30


def test_shared_rack_totals_are_additive_across_tenants():
    """The whole point of the fix: two external tenants in one rack each get
    their own U, and the sum never exceeds the rack's real used-U (no
    whole-rack double counting)."""
    rows = [
        {"dc": "DC13", "rack_name": "500", "tenant_name": "Boyner", "used_u": 12},
        {"dc": "DC13", "rack_name": "500", "tenant_name": "AytemizBank", "used_u": 8},
    ]
    out = {f["tenant"]: f for f in m.build_customer_footprint(rows, {})}
    assert out["Boyner"]["used_u"] == 12
    assert out["AytemizBank"]["used_u"] == 8
    assert out["Boyner"]["used_u"] + out["AytemizBank"]["used_u"] == 20


def test_footprint_empty_when_no_external_tenants():
    rows = [{"dc": "DC13", "rack_name": "9", "tenant_name": "Bulutistan - Network & Security", "used_u": 5}]
    assert m.build_customer_footprint(rows, {}) == []


def test_footprint_sorted_by_used_u_desc():
    rows = [
        {"dc": "DC13", "rack_name": "1", "tenant_name": "SmallCo", "used_u": 5},
        {"dc": "DC13", "rack_name": "2", "tenant_name": "BigCo", "used_u": 50},
    ]
    out = m.build_customer_footprint(rows, {})
    assert [e["tenant"] for e in out] == ["BigCo", "SmallCo"]


def test_internal_footprint_keeps_only_internal_tenants():
    rows = [
        {"dc": "DC13", "rack_name": "1", "tenant_name": "Bulutistan - Virtualization", "used_u": 20},
        {"dc": "DC13", "rack_name": "2", "tenant_name": "Bulutistan - Virtualization", "used_u": 5},
        {"dc": "DC13", "rack_name": "1", "tenant_name": "Boyner", "used_u": 10},   # external -> excluded
        {"dc": "DC13", "rack_name": "3", "tenant_name": "", "used_u": 9},          # untagged -> excluded
    ]
    out = m.build_internal_footprint(rows)
    assert [e["tenant"] for e in out] == ["Bulutistan - Virtualization"]
    assert out[0]["used_u"] == 25            # 20 + 5, exact
    assert sorted(out[0]["racks"]) == ["1", "2"]
    assert "crm_accountid" not in out[0]     # internal rows carry no CRM columns


def test_internal_footprint_sorted_by_used_u_desc():
    rows = [
        {"dc": "DC13", "rack_name": "1", "tenant_name": "Bulut Broker", "used_u": 5},
        {"dc": "DC13", "rack_name": "2", "tenant_name": "Bulutistan - Linux TEAM", "used_u": 50},
    ]
    out = m.build_internal_footprint(rows)
    assert [e["tenant"] for e in out] == ["Bulutistan - Linux TEAM", "Bulut Broker"]


def test_footprint_skips_blank_tenant_and_zero_or_null_u():
    rows = [
        {"dc": "DC13", "rack_name": "1", "tenant_name": "", "used_u": 9},
        {"dc": "DC13", "rack_name": "1", "tenant_name": None, "used_u": 9},
        {"dc": "DC13", "rack_name": "1", "tenant_name": "Paycore", "used_u": None},
    ]
    out = m.build_customer_footprint(rows, {})
    # blank/None tenants dropped; Paycore present but with 0 U (null coerced)
    assert [e["tenant"] for e in out] == ["Paycore"]
    assert out[0]["used_u"] == 0
