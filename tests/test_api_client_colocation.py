"""api_client colocation clients call the right endpoints and cache via SWR."""
from unittest.mock import patch

from src.services import api_client as api
from src.services import cache_service


def test_get_dc_racks_occupancy_calls_endpoint():
    cache_service.clear()
    payload = {"racks": [{"rack_name": "116"}], "summary": {"free_u": 12}}
    with patch("src.services.api_client._get_json", return_value=payload) as gj:
        out = api.get_dc_racks_occupancy("DC13")
    assert out == payload
    called_path = gj.call_args[0][1]
    assert called_path == "/api/v1/datacenters/DC13/racks/occupancy"


def test_get_dc_racks_occupancy_empty_on_bad_shape():
    cache_service.clear()
    with patch("src.services.api_client._get_json", return_value="oops"):
        out = api.get_dc_racks_occupancy("DC13")
    assert out == {"racks": [], "summary": {}}


def test_get_colocation_calls_endpoint():
    cache_service.clear()
    payload = {"aggregate": {"foo": "bar"}, "customers": ["c1"], "racks": [{"id": "R1"}]}
    with patch("src.services.api_client._get_json", return_value=payload) as gj:
        out = api.get_colocation("DC13")
    assert out == payload
    called_path = gj.call_args[0][1]
    assert called_path == "/api/v1/crm/colocation/DC13"


def test_get_colocation_uses_customer_api_client():
    cache_service.clear()
    payload = {"aggregate": {}, "customers": [], "racks": []}
    cust_sentinel = object()
    crm_sentinel = object()
    with patch("src.services.api_client._get_json") as gj, \
         patch("src.services.api_client._get_client_cust", return_value=cust_sentinel), \
         patch("src.services.api_client._get_client_crm", return_value=crm_sentinel):
        gj.return_value = payload
        api.get_colocation("DC13")
    # Assert _get_json was called with the CUST client, not the CRM client
    assert gj.call_args[0][0] is cust_sentinel
    assert gj.call_args[0][0] is not crm_sentinel


def test_get_colocation_empty_on_bad_shape():
    cache_service.clear()
    with patch("src.services.api_client._get_json", return_value="oops"):
        out = api.get_colocation("DC13")
    assert out == {"aggregate": {}, "customers": [], "racks": []}
