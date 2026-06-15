"""GUI api_client virt sellable cache key consistency."""
from __future__ import annotations

from unittest.mock import patch

from src.services import api_client as api


def test_virt_sellable_total_cache_key_uses_star_for_all():
    with patch.object(api, "_get_json", return_value=[]):
        with patch.object(
            api,
            "_api_cache_get_sellable_panels",
            side_effect=lambda _k, fetch, *_a: fetch(),
        ) as mock_get:
            api.get_virt_sellable_panels("DC13", None, None)
            api.get_virt_sellable_panels("DC13", ["A", "B"], ["X", "Y"])
            keys = [call.args[0] for call in mock_get.call_args_list]
    assert keys[0] == "api:virt_sellable_total:DC13:*:*"
    assert keys[1] == "api:virt_sellable_total:DC13:A,B:X,Y"
