"""Compact, static domain knowledge catalog for the chatbot planner.

This package is the machine-readable counterpart of docs/chatbot-knowledge/. The
human-readable MD files are NEVER injected into the LLM context at runtime — the
planner uses these compact definitions, and only the resulting plan / evidence /
analysis (plus the matched metric's answer_guidance) reaches the model.

The catalog only maps domain concepts to *allowlisted* tools in tool_registry;
it never grants access to anything outside the registry, and it contains no
secrets.
"""

from app.catalog import data_source_catalog, domain_catalog, metric_semantics

__all__ = ["domain_catalog", "data_source_catalog", "metric_semantics"]
