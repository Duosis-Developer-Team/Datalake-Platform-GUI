"""Periodic backend warm keeps overview/summary caches hot (no nav-only 15-min throttle)."""
import ast
from pathlib import Path

from src.services import app_background_warm as warm


def test_warm_throttle_lowered_for_periodic_warm():
    # Was 900s (nav-only). Now short enough that a ~5-min interval re-warms.
    assert warm._WARM_INTERVAL_SECONDS <= 300


def test_app_has_periodic_warm_interval_and_callback():
    src = Path("app.py").read_text(encoding="utf-8")
    assert "app-warm-interval" in src           # Interval in layout
    tree = ast.parse(src)
    names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert "_periodic_backend_warm" in names     # the periodic callback
