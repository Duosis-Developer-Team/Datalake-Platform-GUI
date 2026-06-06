"""Unit tests for CRM-backed customer list helpers."""
from __future__ import annotations

from app.services.crm_customer_list import (
    build_crm_project_customer_list,
    resolve_infra_search_name,
)


def test_build_crm_project_customer_list_includes_project_names():
    names = build_crm_project_customer_list(["Acme Corp", "Beta Ltd"], boyner_crm_name=None)
    assert names == ["Acme Corp", "Beta Ltd", "Boyner"]


def test_build_crm_project_customer_list_replaces_boyner_with_crm_name():
    names = build_crm_project_customer_list(
        ["Boyner", "Acme Corp"],
        boyner_crm_name="BOYNER BUYUK MAGAZACILIK A.S.",
    )
    assert "Boyner" not in names
    assert "BOYNER BUYUK MAGAZACILIK A.S." in names
    assert "Acme Corp" in names


def test_build_crm_project_customer_list_pins_boyner_when_no_projects():
    names = build_crm_project_customer_list(
        ["Acme Corp"],
        boyner_crm_name="BOYNER BUYUK MAGAZACILIK A.S.",
    )
    assert names[0] == "Acme Corp"
    assert "BOYNER BUYUK MAGAZACILIK A.S." in names


def test_build_crm_project_customer_list_pins_legacy_boyner_without_crm():
    names = build_crm_project_customer_list(["Acme Corp"], boyner_crm_name=None)
    assert "Boyner" in names
    assert "Acme Corp" in names


def test_resolve_infra_search_name_uses_alias_netbox_value():
    assert (
        resolve_infra_search_name(
            "BOYNER BUYUK MAGAZACILIK A.S.",
            alias_netbox_value="Boyner",
        )
        == "Boyner"
    )


def test_resolve_infra_search_name_boyner_fallback():
    assert resolve_infra_search_name("BOYNER BUYUK MAGAZACILIK A.S.") == "Boyner"


def test_resolve_infra_search_name_matches_netbox_tenant():
    assert (
        resolve_infra_search_name(
            "MEZON LOJISTIK ANONIM SIRKETI",
            netbox_tenant_names=["Boyner", "Mezon"],
        )
        == "Mezon"
    )
