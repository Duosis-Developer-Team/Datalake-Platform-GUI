"""Matching NetBox tenant strings to CRM accounts when no manual alias exists.

The DC licence attribution needs tenant -> CRM account. The authoritative link is
`gui_crm_customer_alias.netbox_musteri_value`, but that field is filled by hand —
the automatic resync explicitly writes NULL into it — so most customers have no
alias. Without a fallback the DC "Satılan" column is empty for nearly everyone.

The fallback is name matching, the same heuristic Customer View already runs in
production. It is a guess, so every match records how it was made and the UI says
which one it used.
"""
from __future__ import annotations

from shared.licensing.tenant_match import MATCH_ALIAS, MATCH_NAME, match_tenants_to_accounts

# (accountid, account name) as CRM stores them.
_ACCOUNTS = [
    ("id-gama", "GAMA ENERJİ A.Ş."),
    ("id-ankutsan", "ANKUTSAN GERİ DÖNÜŞÜM SANAYİ VE TİCARET A.Ş."),
    ("id-4a", "4A KOZMETİK SANAYİ VE TİCARET ANONİM ŞİRKETİ"),
]


def test_manual_alias_wins_over_any_name_similarity():
    """A hand-made mapping is a decision someone took; a guess must never override
    it — even when the names look like they point elsewhere."""
    out = match_tenants_to_accounts(
        tenants=["gama_enerji"],
        accounts=_ACCOUNTS,
        alias_by_tenant={"gama_enerji": "id-ankutsan"},
    )
    assert out["gama_enerji"] == ("id-ankutsan", MATCH_ALIAS)


def test_tenant_without_an_alias_falls_back_to_name_matching():
    out = match_tenants_to_accounts(
        tenants=["gama_enerji"], accounts=_ACCOUNTS, alias_by_tenant={},
    )
    assert out["gama_enerji"] == ("id-gama", MATCH_NAME)


def test_turkish_characters_and_separators_do_not_block_a_match():
    out = match_tenants_to_accounts(
        tenants=["ANKUTSAN", "4a_Kozmetik"], accounts=_ACCOUNTS, alias_by_tenant={},
    )
    assert out["ANKUTSAN"][0] == "id-ankutsan"
    assert out["4a_Kozmetik"][0] == "id-4a"


def test_unmatched_tenant_is_absent_rather_than_guessed_at():
    out = match_tenants_to_accounts(
        tenants=["silinecek_makineler_vc3_dc13"], accounts=_ACCOUNTS, alias_by_tenant={},
    )
    assert "silinecek_makineler_vc3_dc13" not in out


def test_an_ambiguous_token_matches_nothing():
    """Two customers sharing a leading token cannot be told apart by it, so
    neither is picked — a wrong attribution is worse than a missing one."""
    accounts = [("id-a", "AKSA ENERJİ A.Ş."), ("id-b", "AKSA AKRİLİK A.Ş.")]
    out = match_tenants_to_accounts(tenants=["aksa"], accounts=accounts, alias_by_tenant={})
    assert "aksa" not in out


def test_very_short_tokens_are_not_used_as_evidence():
    accounts = [("id-x", "AS BİLİŞİM A.Ş.")]
    out = match_tenants_to_accounts(tenants=["as"], accounts=accounts, alias_by_tenant={})
    assert "as" not in out


def test_empty_inputs_are_safe():
    assert match_tenants_to_accounts(tenants=[], accounts=[], alias_by_tenant={}) == {}
    assert match_tenants_to_accounts(tenants=None, accounts=None, alias_by_tenant=None) == {}
