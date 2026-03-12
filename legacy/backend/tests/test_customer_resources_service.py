from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from app.services.db_service import DatabaseService
from app.services import cache_service as cache

FIXED_TR = {"start": "2026-03-01", "end": "2026-03-07"}


def _make_cur():
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    cur.description = [("col",)]
    return cur


def _make_conn(cur):
    conn = MagicMock()
    conn.cursor.return_value = cur
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    return conn


def _make_svc(mock_conn):
    with patch("app.services.db_service.pg_pool.ThreadedConnectionPool") as cls:
        pool = MagicMock()
        pool.getconn.return_value = mock_conn
        cls.return_value = pool
        svc = DatabaseService()

    @contextmanager
    def fake_conn():
        yield mock_conn

    svc._get_connection = fake_conn
    return svc


def _cache_key(name):
    return f"customer_assets:{name}:{FIXED_TR['start']}:{FIXED_TR['end']}"


def test_get_customer_resources_happy_path_builds_correct_totals():
    cur = _make_cur()
    cur.fetchone.side_effect = [
        (7, 3, 10),
        (14.0, 6.0, 20.0),
        (70.0, 30.0, 100.0),
        (700.0, 300.0, 1000.0),
        (4.0,),
        (2,),
        (16.0,),
        (5,),
        (50.0, 10.0, "5x"),
        (3,),
        (100.0,),
    ]
    cur.fetchall.side_effect = [
        [("vm1", "vmware", 2.0, 10.0, 100.0)],
        [("lpar1", "ibm", 2.0, 8.0, "Running")],
        [("Backup", 3)],
        [("VMware", 3)],
        [("vpg1", 20.0)],
    ]
    svc = _make_svc(_make_conn(cur))
    cache.delete(_cache_key("HappyCustomer"))
    result = svc.get_customer_resources("HappyCustomer", FIXED_TR)
    assert result["totals"]["intel_vms_total"] == 10
    assert result["totals"]["power_lpar_total"] == 2
    assert result["totals"]["vms_total"] == 12
    assert result["totals"]["cpu_total"] == 20.0 + 4.0
    assert len(result["assets"]["intel"]["vm_list"]) == 1


def test_get_customer_resources_caches_result_on_success():
    cur = _make_cur()
    cur.fetchone.side_effect = [
        (5, 5, 10),
        (10.0, 10.0, 20.0),
        (50.0, 50.0, 100.0),
        (500.0, 500.0, 1000.0),
        (0,),
        (0,),
        (0.0,),
        (0,),
        (0.0, 0.0, "1x"),
        (0,),
        (0.0,),
    ]
    cur.fetchall.return_value = []
    svc = _make_svc(_make_conn(cur))
    cache.delete(_cache_key("CachingCustomer"))
    svc.get_customer_resources("CachingCustomer", FIXED_TR)
    execute_count = cur.execute.call_count
    svc.get_customer_resources("CachingCustomer", FIXED_TR)
    assert cur.execute.call_count == execute_count


def test_get_customer_resources_empty_customer_name_uses_wildcard_patterns():
    cur = _make_cur()
    cur.fetchone.return_value = None
    cur.fetchall.return_value = []
    svc = _make_svc(_make_conn(cur))
    cache.delete(_cache_key(""))
    result = svc.get_customer_resources("", FIXED_TR)
    assert result["totals"]["vms_total"] == 0
    assert isinstance(result["assets"], dict)


def test_get_customer_resources_storage_volume_exception_uses_zero():
    cur = _make_cur()
    cur.fetchone.return_value = None
    cur.fetchall.return_value = []
    svc = _make_svc(_make_conn(cur))
    cache.delete(_cache_key("StorageExcCustomer"))
    run_value_calls = [0]

    def patched_run_value(cursor, sql, params=None):
        run_value_calls[0] += 1
        if run_value_calls[0] == 6:
            return "not_a_number"
        return 0

    svc._run_value = patched_run_value
    result = svc.get_customer_resources("StorageExcCustomer", FIXED_TR)
    assert result["totals"]["backup"]["storage_volume_gb"] == 0.0


def test_get_customer_resources_backup_detail_structures():
    cur = _make_cur()
    cur.fetchone.side_effect = [
        (3, 2, 5),
        (6.0, 4.0, 10.0),
        (30.0, 20.0, 50.0),
        (300.0, 200.0, 500.0),
        (0,),
        (0,),
        (0.0,),
        (3,),
        (100.0, 20.0, "5x"),
        (2,),
        (50.0,),
    ]
    cur.fetchall.side_effect = [
        [],
        [],
        [("Backup Job", 2), ("Copy Job", 1)],
        [("VMware", 2), ("HyperV", 1)],
        [("vpg_prod", 30.0), ("vpg_dev", 20.0)],
    ]
    svc = _make_svc(_make_conn(cur))
    cache.delete(_cache_key("BackupCustomer"))
    result = svc.get_customer_resources("BackupCustomer", FIXED_TR)
    backup = result["assets"]["backup"]
    assert backup["veeam"]["defined_sessions"] == 3
    assert len(backup["veeam"]["session_types"]) == 2
    assert len(backup["veeam"]["platforms"]) == 2
    assert backup["netbackup"]["pre_dedup_size_gib"] == 100.0
    assert backup["netbackup"]["deduplication_factor"] == "5x"
    assert backup["zerto"]["protected_total_vms"] == 2
    assert len(backup["zerto"]["vpgs"]) == 2
    assert backup["zerto"]["provisioned_storage_gib_total"] == 50.0
    assert backup["storage"]["total_volume_capacity_gb"] == 50.0
