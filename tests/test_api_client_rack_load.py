from unittest.mock import patch

import httpx
import pytest

from src.services import api_client as api
from src.services import cache_service


def test_get_dc_racks_load_calls_the_load_path():
    cache_service.clear()
    with patch.object(api, "_get_json", return_value={"racks": [], "summary": {}}) as gj:
        api.get_dc_racks_load("DC13")
    assert gj.call_args[0][1] == "/api/v1/datacenters/DC13/racks/load"


def test_get_dc_racks_load_url_encodes_the_dc_code():
    cache_service.clear()
    with patch.object(api, "_get_json", return_value={"racks": []}) as gj:
        api.get_dc_racks_load("Vadi Ofis")
    assert "Vadi%20Ofis" in gj.call_args[0][1]


def test_get_dc_racks_load_returns_empty_shape_on_bad_shape():
    # A list or None from the backend is a shape bug, not data: fall back to
    # the empty contract rather than handing the caller something it cannot read.
    cache_service.clear()
    with patch.object(api, "_get_json", return_value=["not", "a", "dict"]):
        assert api.get_dc_racks_load("DC13") == {"racks": [], "summary": {}}


def test_get_dc_racks_load_returns_empty_shape_when_the_backend_is_unreachable():
    # httpx.ConnectError is in _HTTP_ERRORS, so the stale-while-revalidate
    # wrapper handles it: it logs the failure and falls back. A bare
    # RuntimeError is NOT handled, and must not be — an unexpected exception
    # type is a bug to surface, not a "no data" answer to swallow.
    cache_service.clear()
    with patch.object(api, "_get_json", side_effect=httpx.ConnectError("down")):
        result = api.get_dc_racks_load("DC13")
    assert result == {"racks": [], "summary": {}}


def test_an_unexpected_exception_type_is_not_swallowed():
    # Mirrors get_dc_racks_occupancy: only _HTTP_ERRORS are absorbed. A
    # payload-shape bug must surface, not render as "every rack unmonitored".
    cache_service.clear()
    with patch.object(api, "_get_json", side_effect=TypeError("shape changed")):
        with pytest.raises(TypeError):
            api.get_dc_racks_load("DC14")
