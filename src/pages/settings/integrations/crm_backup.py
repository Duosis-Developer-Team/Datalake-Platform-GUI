"""Integrations - Backup multipliers (soft-deprecated).

Moved to Administration → Platform → Backup Mapping
(``src.pages.settings.platform.backup_mapping``). This module re-exports
``build_layout`` so legacy imports and the CRM backup redirect route keep working.
"""
from __future__ import annotations

from src.pages.settings.platform.backup_mapping import build_layout

__all__ = ["build_layout"]
