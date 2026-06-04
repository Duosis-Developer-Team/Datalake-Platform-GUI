"""Deprecated shim — the domain catalog moved to ``app.catalog.domain_catalog``.

Kept so existing imports (``from app.services import metric_catalog``) keep
working. New code should import from ``app.catalog`` directly.
"""

from __future__ import annotations

from app.catalog.domain_catalog import (
    METRICS,
    MetricDefinition,
    find_metric_candidates,
    get,
    match,
)

CATALOG = tuple(METRICS.values())

__all__ = ["MetricDefinition", "METRICS", "CATALOG", "get", "match", "find_metric_candidates"]
