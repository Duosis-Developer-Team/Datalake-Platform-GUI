from unittest.mock import MagicMock

from app.adapters.nutanix_adapter import NutanixAdapter


def _make_adapter():
    run_value = MagicMock(return_value=5)
    run_row = MagicMock(return_value=(100.0, 80.0))
    run_rows = MagicMock(return_value=[])
    get_conn = MagicMock()
    return NutanixAdapter(get_conn, run_value, run_row, run_rows)


def test_fetch_single_dc_returns_dict_with_all_keys():
    adapter = _make_adapter()
    cursor = MagicMock()
    result = adapter.fetch_single_dc(cursor, "DC11", "2026-03-01", "2026-03-07")
    assert "host_count" in result
    assert "vm_count" in result
    assert "memory" in result
    assert "storage" in result
    assert "cpu" in result


def test_fetch_single_dc_host_count_uses_run_value():
    adapter = _make_adapter()
    cursor = MagicMock()
    result = adapter.fetch_single_dc(cursor, "DC11", "2026-03-01", "2026-03-07")
    assert result["host_count"] == 5


def test_fetch_single_dc_memory_uses_run_row():
    adapter = _make_adapter()
    cursor = MagicMock()
    result = adapter.fetch_single_dc(cursor, "DC11", "2026-03-01", "2026-03-07")
    assert result["memory"] == (100.0, 80.0)


def test_fetch_batch_queries_returns_six_tuples():
    adapter = _make_adapter()
    queries = adapter.fetch_batch_queries(["DC11"], ["%DC11%"], "2026-03-01", "2026-03-07")
    assert len(queries) == 6


def test_fetch_batch_queries_labels_are_correct():
    adapter = _make_adapter()
    queries = adapter.fetch_batch_queries(["DC11"], ["%DC11%"], "2026-03-01", "2026-03-07")
    labels = [q[0] for q in queries]
    assert "n_host" in labels
    assert "n_vm" in labels
    assert "n_mem" in labels
    assert "n_stor" in labels
    assert "n_cpu" in labels
    assert "n_platform" in labels


def test_fetch_batch_queries_each_tuple_has_three_elements():
    adapter = _make_adapter()
    queries = adapter.fetch_batch_queries(["DC11"], ["%DC11%"], "2026-03-01", "2026-03-07")
    for q in queries:
        assert len(q) == 3
