"""Migration v4 (platform versioning tables) runs the 003 SQL and records the version.

The v1/v2/v3 migration side effects are neutralized via monkeypatch so the test
exercises only the new v4 block against a lightweight fake cursor.
"""

from __future__ import annotations

import re

from src.auth import auth_db_migrations as m


class _Cur:
    def __init__(self, applied, executed):
        self.applied = applied
        self.executed = executed
        self._n = None

    def execute(self, sql, params=None):
        self.executed.append(sql)
        s = sql.upper()
        if "SELECT 1 FROM SCHEMA_MIGRATIONS WHERE VERSION =" in s:
            self._n = int(sql.rsplit("=", 1)[1].strip())
        elif s.strip().startswith("INSERT INTO SCHEMA_MIGRATIONS"):
            mo = re.search(r"VALUES\s*\((\d+)", sql)
            if mo:
                self.applied.add(int(mo.group(1)))
            self._n = None
        else:
            self._n = None

    def fetchone(self):
        return {"1": 1} if (self._n in self.applied) else None

    def close(self):
        pass


class _Conn:
    def __init__(self, applied, executed):
        self.applied = applied
        self.executed = executed

    def cursor(self):
        return _Cur(self.applied, self.executed)


def test_migration_v4_creates_versioning_tables(monkeypatch):
    applied: set[int] = set()
    executed: list[str] = []
    # Neutralize v1/v2/v3 so only the v4 path is meaningful; keep the real 003 SQL.
    monkeypatch.setattr(m, "_read_schema_sql", lambda: "CREATE TABLE IF NOT EXISTS schema_migrations ();")
    monkeypatch.setattr(m, "_migration_v2_rename_settings", lambda cur: None)
    monkeypatch.setattr(m, "_read_migration_002_sql", lambda: "")

    m.run_auth_db_migrations(_Conn(applied, executed))

    joined = " ".join(executed)
    assert "platform_releases" in joined
    assert "release_changes" in joined
    assert "service_deployments" in joined
    assert 4 in applied


def test_migration_003_read_sql_nonempty():
    sql = m._read_migration_003_sql()
    assert "platform_releases" in sql
    assert "service_deployments" in sql
