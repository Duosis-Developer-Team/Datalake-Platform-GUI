"""GUI api_client virt sellable cache key consistency."""
from __future__ import annotations

from unittest.mock import patch

from src.services import api_client as api
from src.services import cache_service


def test_virt_sellable_panels_delegates_to_by_panel_cache():
    cache_service.clear()
    with patch.object(api, "_get_json", return_value=[]):
        with patch.object(
            api,
            "_api_cache_get_sellable_panels",
            side_effect=lambda _k, fetch, *_a: fetch(),
        ) as mock_get:
            api.get_virt_sellable_panels("DC13", None, None, tr={"preset": "7d"})
            keys = [call.args[0] for call in mock_get.call_args_list]
    assert len(keys) == 4
    assert all(k.startswith("api:sellable_by_panel:DC13:") for k in keys)
    assert all("7d" in k for k in keys)
