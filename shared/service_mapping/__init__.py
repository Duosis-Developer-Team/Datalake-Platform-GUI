"""Shared CRM service mapping helpers (rule pack + YAML load for GUI tooling)."""

from .rules import load_rule_pack, match_product_name

__all__ = ["match_product_name", "load_rule_pack"]
