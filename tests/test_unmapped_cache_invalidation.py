"""The unmapped view is the complement of every mapping, so a mapping write
must drop it. customer-api already does this server-side
(customer_service.apply_mapping_invalidation); the GUI response cache did not,
which left the just-fixed row on screen after a successful save.
"""


def test_mapping_write_drops_the_gui_unmapped_response_cache():
    from src.services import api_client

    ck = "api:unmapped_resources:preset=7d"
    api_client._api_response_cache.set(ck, {"rows": [], "total": 0})
    assert api_client._api_response_cache.get(ck) is not None

    api_client._invalidate_customer_views_cache()

    assert api_client._api_response_cache.get(ck) is None
