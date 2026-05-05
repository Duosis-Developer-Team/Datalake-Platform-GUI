"""Tests for IBM SAN varchar capacity parsing (sellable pipeline)."""

from __future__ import annotations

import math

from app.utils.storage_capacity_parse import parse_storage_string_to_gb


def test_parse_tb_to_gb():
    assert math.isclose(parse_storage_string_to_gb("110.00 TB"), 110.00 * 1024, rel_tol=1e-9)


def test_parse_invalid_returns_zero():
    assert parse_storage_string_to_gb("N/A") == 0.0
