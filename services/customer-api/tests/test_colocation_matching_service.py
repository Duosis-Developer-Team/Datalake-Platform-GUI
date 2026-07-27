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


def test_used_u_breakdown_receives_same_prefixes_as_footprint_builders():
    """Fix round 1: the design spec says the summary-bar external/internal
    split must shift with Administration mappings too, not just the tenant
    footprint lists. used_u_breakdown, build_customer_footprint and
    build_internal_footprint must all be called with the identical prefixes
    tuple computed by _internal_prefixes()."""
    customer = MagicMock()
    webui = MagicMock()
    webui.is_available = True
    webui.run_rows.return_value = [{"match_value": "Acme-Internal", "enabled": True}]
    svc = ColocationMatchingService(customer_service=customer, webui=webui)

    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.cursor.return_value.__enter__.return_value = MagicMock()
    customer._get_connection.return_value = conn

    with patch("app.services.colocation_matching_service.occupancy_rows", return_value=_rows()), \
         patch("app.services.colocation_matching_service.tenant_occupancy_rows", return_value=_tenant_rows()), \
         patch("app.services.colocation_matching_service.used_u_breakdown",
               return_value={"external_u": 0, "internal_u": 0, "untagged_u": 0,
                             "external_customer_count": 0}) as breakdown_mock, \
         patch("app.services.colocation_matching_service.build_customer_footprint",
               return_value=[]) as customer_mock, \
         patch("app.services.colocation_matching_service.build_internal_footprint",
               return_value=[]) as internal_mock:
        svc.get_colocation("DC13")

    breakdown_prefixes = breakdown_mock.call_args.kwargs.get("internal_prefixes")
    customer_prefixes = customer_mock.call_args.kwargs.get("internal_prefixes")
    internal_prefixes = internal_mock.call_args.kwargs.get("internal_prefixes")

    assert breakdown_prefixes is not None
    assert breakdown_prefixes == customer_prefixes == internal_prefixes
    assert "acme-internal" in breakdown_prefixes
    assert "bulutistan" in breakdown_prefixes


def test_internal_prefixes_consulted_once_per_get_colocation_call():
    customer = MagicMock()
    webui = MagicMock()
    webui.is_available = True
    webui.run_rows.return_value = []
    svc = ColocationMatchingService(customer_service=customer, webui=webui)

    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.cursor.return_value.__enter__.return_value = MagicMock()
    customer._get_connection.return_value = conn

    with patch("app.services.colocation_matching_service.occupancy_rows", return_value=_rows()), \
         patch("app.services.colocation_matching_service.tenant_occupancy_rows", return_value=_tenant_rows()), \
         patch.object(svc, "_internal_prefixes", wraps=svc._internal_prefixes) as prefixes_mock:
        svc.get_colocation("DC13")

    assert prefixes_mock.call_count == 1


def _service_with_price(price):
    customer = MagicMock()
    conn = MagicMock()
    customer._get_connection.return_value.__enter__.return_value = conn
    webui = MagicMock()
    webui.is_available = False
    svc = ColocationMatchingService(customer_service=customer, webui=webui)
    return svc, price


def test_payload_carries_unit_price_and_potential():
    svc, price = _service_with_price(10430.84)

    with patch("app.services.colocation_matching_service.occupancy_rows", return_value=_rows()), \
         patch("app.services.colocation_matching_service.tenant_occupancy_rows", return_value=_tenant_rows()), \
         patch("app.services.colocation_matching_service.used_u_breakdown", return_value={}), \
         patch("app.services.colocation_matching_service.resolve_colocation_unit_price",
               return_value=(price, "crm")):
        payload = svc.get_colocation("DC13")

    agg = payload["aggregate"]
    assert agg["unit_price_tl"] == price
    assert agg["price_source"] == "crm"
    assert agg["free_u_potential_tl"] == agg["free_u"] * price
    assert agg["used_u_potential_tl"] == agg["used_u"] * price

    boyner = next(c for c in payload["customers"] if c["tenant"] == "Boyner")
    assert boyner["potential_tl"] == boyner["used_u"] * price


def test_payload_potential_is_none_when_price_unresolved():
    svc, _ = _service_with_price(None)

    with patch("app.services.colocation_matching_service.occupancy_rows", return_value=_rows()), \
         patch("app.services.colocation_matching_service.tenant_occupancy_rows", return_value=_tenant_rows()), \
         patch("app.services.colocation_matching_service.used_u_breakdown", return_value={}), \
         patch("app.services.colocation_matching_service.resolve_colocation_unit_price",
               return_value=(None, "unavailable")):
        payload = svc.get_colocation("DC13")

    agg = payload["aggregate"]
    assert agg["unit_price_tl"] is None
    assert agg["price_source"] == "unavailable"
    assert agg["free_u_potential_tl"] is None
    assert all(c["potential_tl"] is None for c in payload["customers"])
    assert all(r["potential_tl"] is None for r in payload["internal"])


def test_internal_rows_also_carry_potential():
    svc, price = _service_with_price(1000.0)

    with patch("app.services.colocation_matching_service.occupancy_rows", return_value=_rows()), \
         patch("app.services.colocation_matching_service.tenant_occupancy_rows", return_value=_tenant_rows()), \
         patch("app.services.colocation_matching_service.used_u_breakdown", return_value={}), \
         patch("app.services.colocation_matching_service.resolve_colocation_unit_price",
               return_value=(price, "override")):
        payload = svc.get_colocation("DC13")

    assert payload["internal"]
    for r in payload["internal"]:
        assert r["potential_tl"] == r["used_u"] * price
