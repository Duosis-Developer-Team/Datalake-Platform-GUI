"""Local dev: re-export shared migrations. Docker build overwrites this file with a copy of
`src/auth/auth_db_migrations.py` (see services/admin-api/Dockerfile).
"""

from __future__ import annotations

import sys
from pathlib import Path

_gui_root = Path(__file__).resolve().parents[3]
if (_gui_root / "src" / "auth" / "auth_db_migrations.py").is_file():
    root = str(_gui_root)
    if root not in sys.path:
        sys.path.insert(0, root)
    from src.auth.auth_db_migrations import run_auth_db_migrations
else:
    raise ImportError(
        "auth_db_migrations: run from Datalake-Platform-GUI repo or use the Docker image "
        "(expected src/auth/auth_db_migrations.py under repo root)."
    )

__all__ = ["run_auth_db_migrations"]
