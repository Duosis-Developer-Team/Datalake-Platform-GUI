"""Pytest path setup for hmdl-api (avoid shadowing by repo-root app.py)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Allow unit tests without a local psycopg2 install.
if "psycopg2" not in sys.modules:
    _pg = MagicMock()
    sys.modules["psycopg2"] = _pg
    sys.modules["psycopg2.extras"] = MagicMock(RealDictCursor=MagicMock())
    sys.modules["psycopg2.pool"] = MagicMock(ThreadedConnectionPool=MagicMock())
