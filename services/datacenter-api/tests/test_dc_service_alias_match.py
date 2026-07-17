"""The physical-inventory tenant filter must use the shared match semantics.

Imports the real function from dc_service — a mirror of the loop would pass
even if the service still had its own hand-rolled copy.
"""
from __future__ import annotations

from app.services.dc_service import tenant_matches_text_rules


def test_underscore_is_literal():
    assert tenant_matches_text_rules("Deneme_Dr_Prod", [("contains", "Deneme_Dr")]) is True
    assert tenant_matches_text_rules("DenemeXDr", [("contains", "Deneme_Dr")]) is False


def test_exact_does_not_match_substring():
    assert tenant_matches_text_rules("Deneme", [("exact", "Deneme")]) is True
    assert tenant_matches_text_rules("Deneme_Dr", [("exact", "Deneme")]) is False


def test_prefix_and_suffix():
    assert tenant_matches_text_rules("Deneme-vm01", [("prefix", "Deneme")]) is True
    assert tenant_matches_text_rules("x-Deneme", [("prefix", "Deneme")]) is False
    assert tenant_matches_text_rules("Deneme-vm01", [("suffix", "vm01")]) is True


def test_non_numeric_id_exact_matches_nothing():
    # Used to fall through to `key in tenant_key` and behave like contains.
    assert tenant_matches_text_rules("tenant-5", [("id_exact", "5")]) is False


def test_case_insensitive():
    assert tenant_matches_text_rules("DENEME", [("exact", "deneme")]) is True


def test_empty_inputs():
    assert tenant_matches_text_rules("", [("contains", "Deneme")]) is False
    assert tenant_matches_text_rules("Deneme", []) is False
    assert tenant_matches_text_rules("Deneme", [("contains", "  ")]) is False


def test_any_rule_matching_is_enough():
    rules = [("exact", "nope"), ("contains", "Deneme")]
    assert tenant_matches_text_rules("x-Deneme-y", rules) is True
