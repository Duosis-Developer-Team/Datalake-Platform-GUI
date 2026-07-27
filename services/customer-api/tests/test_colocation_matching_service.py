"""ColocationMatchingService stitches bulutlake occupancy + webui alias table
into {aggregate, customers, racks}. Alias index is built from GET_ALL_ALIASES
rows keyed by netbox_musteri_value and crm_account_name (lowercased)."""
from unittest.mock import MagicMock, patch

from app.services.colocation_matching_service import ColocationMatchingService
from shared.colocation.occupancy import INTERNAL_TENANT_PREFIXES


def _rows():
    # rack-level rollup (occupancy_rows) — drives aggregate + racks
    return [
        {"rack_name": "116", "dc": "DC13", "capacity_u": 47, "used_u": 35, "free_u": 12,
         "tenants": ["Boyner", "Bulutistan - Linux TEAM"]},
        {"rack_name": "209", "dc": "DC13", "capacity_u": 47, "used_u": 27, "free_u": 20,
         "tenants": ["AytemizBank"]},
    ]


def _tenant_rows():
    # exact per-(rack, tenant) U (tenant_occupancy_rows) — drives customers.
    # rack 116's 35 used-U splits: Boyner 20, internal Linux TEAM 15 (excluded).
    return [
        {"dc": "DC13", "rack_name": "116", "tenant_name": "Boyner", "used_u": 20},
        {"dc": "DC13", "rack_name": "116", "tenant_name": "Bulutistan - Linux TEAM", "used_u": 15},
        {"dc": "DC13", "rack_name": "209", "tenant_name": "AytemizBank", "used_u": 27},
    ]


def test_get_colocation_assembles_payload():
    customer = MagicMock()
    webui = MagicMock()
    webui.is_available = True
    webui.run_rows.return_value = [
        {"crm_accountid": "A-1", "crm_account_name": "Boyner A.Ş.",
         "canonical_customer_key": "boyner", "netbox_musteri_value": "Boyner"},
    ]
    svc = ColocationMatchingService(customer_service=customer, webui=webui)

    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.cursor.return_value.__enter__.return_value = MagicMock()
    customer._get_connection.return_value = conn

    with patch("app.services.colocation_matching_service.occupancy_rows", return_value=_rows()), \
         patch("app.services.colocation_matching_service.tenant_occupancy_rows", return_value=_tenant_rows()):
        out = svc.get_colocation("DC13")

    assert out["aggregate"]["total_u"] == 94
    assert out["aggregate"]["free_u"] == 32
    names = {c["tenant"]: c for c in out["customers"]}
    # internal tenant excluded from the customer view
    assert set(names) == {"Boyner", "AytemizBank"}
    assert names["Boyner"]["crm_accountid"] == "A-1"
    assert names["Boyner"]["match_status"] == "matched"
    assert names["Boyner"]["used_u"] == 20   # EXACT: Boyner's own U, not the whole rack (35)
    assert names["AytemizBank"]["match_status"] == "unmatched"
    assert names["AytemizBank"]["used_u"] == 27
    assert len(out["racks"]) == 2


def test_get_colocation_aggregate_includes_used_u_breakdown():
    customer = MagicMock()
    webui = MagicMock()
    webui.is_available = False
    svc = ColocationMatchingService(customer_service=customer, webui=webui)

    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.cursor.return_value.__enter__.return_value = MagicMock()
    customer._get_connection.return_value = conn

    with patch("app.services.colocation_matching_service.occupancy_rows", return_value=_rows()), \
         patch("app.services.colocation_matching_service.tenant_occupancy_rows", return_value=_tenant_rows()), \
         patch("app.services.colocation_matching_service.used_u_breakdown",
               return_value={"external_u": 149, "internal_u": 481, "untagged_u": 648,
                             "external_customer_count": 5}):
        out = svc.get_colocation("DC13")

    agg = out["aggregate"]
    assert agg["external_u"] == 149
    assert agg["internal_u"] == 481
    assert agg["untagged_u"] == 648
    assert agg["external_customer_count"] == 5


def test_get_colocation_returns_internal_footprint():
    customer = MagicMock()
    webui = MagicMock()
    webui.is_available = False
    svc = ColocationMatchingService(customer_service=customer, webui=webui)

    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.cursor.return_value.__enter__.return_value = MagicMock()
    customer._get_connection.return_value = conn

    with patch("app.services.colocation_matching_service.occupancy_rows", return_value=_rows()), \
         patch("app.services.colocation_matching_service.tenant_occupancy_rows", return_value=_tenant_rows()), \
         patch("app.services.colocation_matching_service.used_u_breakdown",
               return_value={"external_u": 149, "internal_u": 481, "untagged_u": 648,
                             "external_customer_count": 5}):
        out = svc.get_colocation("DC13")

    internal = {r["tenant"]: r for r in out["internal"]}
    # _tenant_rows() has "Bulutistan - Linux TEAM" (internal) with 15U in rack 116
    assert "Bulutistan - Linux TEAM" in internal
    assert internal["Bulutistan - Linux TEAM"]["used_u"] == 15
    # external tenants must NOT appear in the internal list
    assert "Boyner" not in internal and "AytemizBank" not in internal


def test_internal_prefixes_union_administration_mappings_with_builtins():
    webui = MagicMock()
    webui.is_available = True
    webui.run_rows.return_value = [
        {"match_value": "Acme-Internal", "enabled": True},
        {"match_value": "Disabled-One", "enabled": False},
        {"match_value": "  Padded  ", "enabled": True},
    ]
    svc = ColocationMatchingService(customer_service=MagicMock(), webui=webui)

    prefixes = svc._internal_prefixes()

    assert "acme-internal" in prefixes
    assert "padded" in prefixes
    assert "disabled-one" not in prefixes
    # Built-ins are always retained as a seed.
    assert "bulutistan" in prefixes


def test_internal_prefixes_fall_back_to_builtins_when_webui_unavailable():
    webui = MagicMock()
    webui.is_available = False
    svc = ColocationMatchingService(customer_service=MagicMock(), webui=webui)

    assert svc._internal_prefixes() == INTERNAL_TENANT_PREFIXES


def test_internal_prefixes_fall_back_to_builtins_when_lookup_raises():
    webui = MagicMock()
    webui.is_available = True
    webui.run_rows.side_effect = RuntimeError("webui down")
    svc = ColocationMatchingService(customer_service=MagicMock(), webui=webui)

    assert svc._internal_prefixes() == INTERNAL_TENANT_PREFIXES
