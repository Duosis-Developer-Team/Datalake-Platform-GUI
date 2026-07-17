from contextlib import contextmanager
from unittest.mock import MagicMock

from app.services.webui_db import WebuiPool


def _pool_with_fake_conn(conn):
    pool = WebuiPool.__new__(WebuiPool)  # bypass __init__ / real pool creation

    @contextmanager
    def fake_get_connection():
        yield conn

    pool._get_connection = fake_get_connection
    return pool


def _fake_conn():
    conn = MagicMock()
    cur = MagicMock()
    cur.rowcount = 1
    conn.cursor.return_value.__enter__.return_value = cur
    return conn, cur


def test_runs_every_statement_on_one_connection():
    conn, cur = _fake_conn()
    pool = _pool_with_fake_conn(conn)

    total = pool.execute_all([("DELETE FROM t WHERE a=%s", ("x",)), ("INSERT INTO t VALUES (%s)", ("y",))])

    assert cur.execute.call_count == 2
    assert total == 2


def test_commits_once_at_the_end_not_per_statement():
    conn, _ = _fake_conn()
    pool = _pool_with_fake_conn(conn)

    pool.execute_all([("DELETE FROM t", None), ("INSERT INTO t VALUES (1)", None)])

    # One commit for the whole batch — this is what makes it atomic.
    assert conn.commit.call_count == 1


def test_does_not_commit_when_a_statement_raises():
    conn, cur = _fake_conn()
    cur.execute.side_effect = [None, RuntimeError("boom")]
    pool = _pool_with_fake_conn(conn)

    try:
        pool.execute_all([("DELETE FROM t", None), ("INSERT INTO t VALUES (1)", None)])
    except RuntimeError:
        pass

    # No commit -> the pool rolls the whole thing back on putconn.
    assert conn.commit.call_count == 0


def test_empty_statement_list_is_a_noop():
    conn, _ = _fake_conn()
    pool = _pool_with_fake_conn(conn)

    assert pool.execute_all([]) == 0
    assert conn.commit.call_count == 0
