"""ColocationMatchingService stitches bulutlake occupancy + webui alias table
into {aggregate, customers, racks}. Alias index is built from GET_ALL_ALIASES
rows keyed by netbox_musteri_value and crm_account_name (lowercased)."""
from unittest.mock import MagicMock, patch

from app.services.colocation_matching_service import ColocationMatchingService


def _rows():
    return [
        {"rack_name": "116", "dc": "DC13", "capacity_u": 47, "used_u": 35, "free_u": 12,
         "tenants": ["Boyner", "Bulutistan - Linux TEAM"]},
        {"rack_name": "209", "dc": "DC13", "capacity_u": 47, "used_u": 27, "free_u": 20,
         "tenants": ["AytemizBank"]},
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

    with patch("app.services.colocation_matching_service.occupancy_rows", return_value=_rows()):
        out = svc.get_colocation("DC13")

    assert out["aggregate"]["total_u"] == 94
    assert out["aggregate"]["free_u"] == 32
    names = {c["tenant"]: c for c in out["customers"]}
    assert names["Boyner"]["crm_accountid"] == "A-1"
    assert names["Boyner"]["match_status"] == "matched"
    assert names["AytemizBank"]["match_status"] == "unmatched"
    assert len(out["racks"]) == 2
