"""Rack detail surfaces external dedicated-customer badges from occupancy tenants."""
from src.pages.floor_map import _external_rack_tenants  # helper added below


def test_external_tenants_filters_internal():
    tenants = ["Boyner", "Bulutistan - Linux TEAM", "AytemizBank", "Bulut Broker"]
    assert _external_rack_tenants(tenants) == ["Boyner", "AytemizBank"]


def test_external_tenants_empty():
    assert _external_rack_tenants(["Bulutistan - Virtualization"]) == []
    assert _external_rack_tenants([]) == []


def test_external_tenants_dedupes_and_preserves_order():
    tenants = ["Boyner", "AytemizBank", "Boyner", "Bulutistan - Virtualization", "Paycore"]
    assert _external_rack_tenants(tenants) == ["Boyner", "AytemizBank", "Paycore"]


def test_external_tenants_handles_none_and_falsy_entries():
    assert _external_rack_tenants(None) == []
    assert _external_rack_tenants(["", None, "Boyner"]) == ["Boyner"]
