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


def test_negative_rowcount_does_not_subtract_from_total():
    # psycopg2 returns -1 for statements it cannot report a count for (e.g.
    # some DDL or certain driver situations). `-1 or 0` is truthy and would
    # previously subtract from the running total; it must contribute 0.
    conn, cur = _fake_conn()
    pool = _pool_with_fake_conn(conn)

    rowcounts = iter([-1, 5])

    def fake_execute(sql, params=None):
        cur.rowcount = next(rowcounts)

    cur.execute.side_effect = fake_execute

    total = pool.execute_all(
        [("SOME STATEMENT WITH NO COUNT", None), ("DELETE FROM t WHERE a=%s", ("x",))]
    )

    assert total == 5


def _pool_with_real_get_connection(conn):
    """Build a WebuiPool whose `_get_connection` is the real contextmanager.

    Unlike `_pool_with_fake_conn`, this does not stub out `_get_connection`
    itself. Instead it sets `_pool` to a mock ThreadedConnectionPool whose
    `getconn()` returns `conn`, so the genuine finally/putconn logic in
    `_get_connection` actually runs.
    """
    pool = WebuiPool.__new__(WebuiPool)  # bypass __init__ / real pool creation
    fake_pg_pool = MagicMock()
    fake_pg_pool.getconn.return_value = conn
    pool._pool = fake_pg_pool
    return pool, fake_pg_pool


def test_real_get_connection_returns_conn_to_pool_on_exception():
    conn, cur = _fake_conn()
    cur.execute.side_effect = [None, RuntimeError("boom")]
    pool, fake_pg_pool = _pool_with_real_get_connection(conn)

    try:
        pool.execute_all([("DELETE FROM t", None), ("INSERT INTO t VALUES (1)", None)])
    except RuntimeError:
        pass

    # Never committed...
    assert conn.commit.call_count == 0
    # ...but the connection WAS handed back to the pool, which is what
    # actually triggers psycopg2's rollback-on-putconn behavior.
    fake_pg_pool.putconn.assert_called_once_with(conn, close=False)


def test_real_get_connection_returns_conn_to_pool_on_success():
    conn, _ = _fake_conn()
    pool, fake_pg_pool = _pool_with_real_get_connection(conn)

    pool.execute_all([("DELETE FROM t", None), ("INSERT INTO t VALUES (1)", None)])

    assert conn.commit.call_count == 1
    fake_pg_pool.putconn.assert_called_once_with(conn, close=False)
