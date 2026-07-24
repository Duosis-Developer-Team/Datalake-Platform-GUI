"""Group rack occupancy by external device-tenant into per-customer footprints,
resolving to CRM accounts via the alias map; Bulutistan-internal excluded."""
from shared.colocation import matching as m


def _rows():
    return [
        {"rack_name": "116", "dc": "DC13", "capacity_u": 47, "used_u": 35, "free_u": 12,
         "tenants": ["Boyner", "Bulutistan - Linux TEAM"]},
        {"rack_name": "209", "dc": "DC13", "capacity_u": 47, "used_u": 27, "free_u": 20,
         "tenants": ["AytemizBank"]},
        {"rack_name": "300", "dc": "DC14", "capacity_u": 45, "used_u": 10, "free_u": 35,
         "tenants": ["Bulutistan - Virtualization"]},  # internal only -> no customer entry
    ]


def test_footprint_groups_external_tenants_and_excludes_internal():
    alias = {"boyner": {"crm_accountid": "A-1", "crm_account_name": "Boyner A.Ş."}}
    out = {f["tenant"]: f for f in m.build_customer_footprint(_rows(), alias)}
    assert set(out) == {"Boyner", "AytemizBank"}          # internal excluded
    assert out["Boyner"]["crm_accountid"] == "A-1"
    assert out["Boyner"]["match_status"] == "matched"
    assert out["Boyner"]["racks"] == ["116"]
    assert out["Boyner"]["used_u"] == 35                  # 47 - 12
    assert out["AytemizBank"]["match_status"] == "unmatched"
    assert out["AytemizBank"]["crm_accountid"] is None


def test_footprint_sums_used_u_across_racks():
    rows = [
        {"rack_name": "1", "dc": "DC13", "capacity_u": 47, "used_u": 10, "free_u": 37, "tenants": ["Paycore"]},
        {"rack_name": "2", "dc": "DC13", "capacity_u": 47, "used_u": 20, "free_u": 27, "tenants": ["Paycore"]},
    ]
    out = m.build_customer_footprint(rows, {})
    assert out[0]["tenant"] == "Paycore"
    assert sorted(out[0]["racks"]) == ["1", "2"]
    assert out[0]["used_u"] == 10 + 20


def test_footprint_empty_when_no_external_tenants():
    rows = [{"rack_name": "9", "dc": "DC13", "capacity_u": 47, "used_u": 5, "free_u": 42,
             "tenants": ["Bulutistan - Network & Security"]}]
    assert m.build_customer_footprint(rows, {}) == []
