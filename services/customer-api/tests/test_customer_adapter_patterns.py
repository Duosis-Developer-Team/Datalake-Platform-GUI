"""The adapter must pass resolved patterns through untouched.

_normalize_ilike_pattern used to re-derive the match method from the pattern
string ("no % in here, so it must need wrapping"), which turned every exact
rule back into a contains and would misread an escaped literal %.
"""
from __future__ import annotations

from app.adapters.customer_adapter import CustomerAdapter
from app.services.customer_mapping_resolver import MappingRule, build_resolved_patterns


def _adapter() -> CustomerAdapter:
    noop = lambda *a, **k: None  # noqa: E731
    return CustomerAdapter(noop, noop, noop, noop)


def test_exact_pattern_is_not_rebroadened_into_contains():
    rules = [MappingRule(data_source="virtualization", match_method="exact", match_value="Boyner_Dr")]
    resolved = build_resolved_patterns(rules)
    out = _adapter()._resolve_patterns(resolved, "virtualization", "%Boyner%")
    # Must stay wildcard-free. The old code wrapped it into %Boyner\_Dr%.
    assert out == [r"Boyner\_Dr"]


def test_contains_pattern_passes_through():
    rules = [MappingRule(data_source="virtualization", match_method="contains", match_value="Boyner")]
    resolved = build_resolved_patterns(rules)
    out = _adapter()._resolve_patterns(resolved, "virtualization", "%fallback%")
    assert out == ["%Boyner%"]


def test_escaped_literal_percent_is_not_mistaken_for_a_wildcard():
    rules = [MappingRule(data_source="virtualization", match_method="exact", match_value="50%")]
    resolved = build_resolved_patterns(rules)
    out = _adapter()._resolve_patterns(resolved, "virtualization", "%fallback%")
    assert out == [r"50\%"]


def test_no_patterns_falls_back():
    out = _adapter()._resolve_patterns(None, "virtualization", "%Boyner%")
    assert out == ["%Boyner%"]


def test_empty_source_patterns_falls_back():
    resolved = build_resolved_patterns([])
    out = _adapter()._resolve_patterns(resolved, "storage_ibm", "%Boyner%")
    assert out == ["%Boyner%"]
