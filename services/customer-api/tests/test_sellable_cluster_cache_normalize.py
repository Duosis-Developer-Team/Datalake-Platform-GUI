"""CRM cache key normalization for full virt cluster selection."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.sellable_service import SellableService


def _make_service() -> SellableService:
    return SellableService(
        customer_service=MagicMock(),
        webui=MagicMock(is_available=False),
        config_service=MagicMock(),
        currency_service=MagicMock(),
        tagging_service=MagicMock(),
        datacenter_api_url="http://dc-api",
    )


def test_crm_result_cache_key_full_list_matches_empty():
    svc = _make_service()
    with patch.object(
        svc,
        "_cached_virt_cluster_lists",
        return_value=(["KM-1", "KM-2"], None),
    ):
        none_key = svc._result_cache_key("DC13", None, "virt_classic")
        full_key = svc._result_cache_key(
            "DC13",
            svc._normalize_clusters_for_cache("DC13", ["KM-1", "KM-2"], "virt_classic"),
            "virt_classic",
        )
    assert none_key == full_key == "sellable:panels:DC13:virt_classic:"


def test_crm_normalize_keeps_partial_selection():
    svc = _make_service()
    with patch.object(
        svc,
        "_cached_virt_cluster_lists",
        return_value=(["KM-1", "KM-2"], None),
    ):
        out = svc._normalize_clusters_for_cache("DC13", ["KM-1"], "virt_classic")
    assert out == ["KM-1"]
