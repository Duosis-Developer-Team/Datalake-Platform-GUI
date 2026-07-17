from unittest.mock import MagicMock, patch

from src.services import api_client


def test_put_returns_mappings_and_warning():
    payload = {"mappings": [{"data_source": "virtualization"}], "cache_warning": None}
    with patch.object(api_client, "_put_json", return_value=payload), patch.object(
        api_client, "_api_response_cache"
    ):
        mappings, warning = api_client.put_crm_source_mappings("acct-1", mappings=[])

    assert mappings == [{"data_source": "virtualization"}]
    assert warning is None


def test_put_surfaces_backend_cache_warning():
    payload = {"mappings": [], "cache_warning": "cache temizlenemedi"}
    with patch.object(api_client, "_put_json", return_value=payload), patch.object(
        api_client, "_api_response_cache"
    ):
        _mappings, warning = api_client.put_crm_source_mappings("acct-1", mappings=[])

    assert warning == "cache temizlenemedi"


def test_put_clears_the_gui_resource_cache():
    payload = {"mappings": [], "cache_warning": None}
    cache = MagicMock()
    with patch.object(api_client, "_put_json", return_value=payload), patch.object(
        api_client, "_api_response_cache", cache
    ):
        api_client.put_crm_source_mappings("acct-1", mappings=[])

    # Version-agnostic prefix: the version token is being bumped elsewhere.
    cache.delete_prefix.assert_any_call("api:customer_resources:")
    cache.delete.assert_any_call("api:crm_aliases")
    cache.delete.assert_any_call("api:customer_catalog")
    cache.delete.assert_any_call("api:customer_overview")


def test_put_tolerates_a_malformed_response():
    with patch.object(api_client, "_put_json", return_value="nonsense"), patch.object(
        api_client, "_api_response_cache"
    ):
        mappings, warning = api_client.put_crm_source_mappings("acct-1", mappings=[])

    assert mappings == []
    assert warning is None
