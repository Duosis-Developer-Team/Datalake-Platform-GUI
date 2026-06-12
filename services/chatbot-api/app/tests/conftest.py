"""Pytest configuration — ensure datalake-tools-core is importable in dev/CI."""

from __future__ import annotations

import sys
from pathlib import Path

_CORE = Path(__file__).resolve().parents[3] / "datalake-tools-core"
if _CORE.exists() and str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))
