"""Item 7.2: the Settings dashboard surfaces the live cache metrics (hit rate,
entry count, avg fetch time, backend) next to the cache-refresh control, so the
cache's effectiveness is visible instead of guessed.
"""
from unittest.mock import patch

from src.pages.settings import dashboard


def test_cache_metrics_panel_shows_hit_rate_entries_backend():
    metrics = {
        "hits": 3, "misses": 1, "fetches": 1, "errors": 0,
        "fetch_seconds_total": 2.0, "hit_rate": 0.75, "avg_fetch_seconds": 2.0,
    }
    stats = {"backend": "redis", "current_size": 42, "max_size": 2048}
    with patch.object(dashboard.api, "get_cache_metrics", return_value=metrics), \
         patch.object(dashboard.cache_service, "stats", return_value=stats):
        panel = dashboard.build_cache_metrics_panel()
    text = str(panel)
    assert "75" in text          # hit rate %
    assert "42" in text          # entry count
    assert "redis" in text       # backend


def test_cache_metrics_panel_handles_no_traffic():
    metrics = {
        "hits": 0, "misses": 0, "fetches": 0, "errors": 0,
        "fetch_seconds_total": 0.0, "hit_rate": None, "avg_fetch_seconds": None,
    }
    stats = {"backend": "in_process", "current_size": 0, "max_size": 2048}
    with patch.object(dashboard.api, "get_cache_metrics", return_value=metrics), \
         patch.object(dashboard.cache_service, "stats", return_value=stats):
        panel = dashboard.build_cache_metrics_panel()
    assert panel is not None  # must not crash on None hit_rate


def test_dashboard_layout_includes_cache_metrics():
    layout = dashboard.build_layout()
    assert "hit" in str(layout).lower()
