from unittest.mock import MagicMock

from app.adapters.vmware_adapter import VMwareAdapter


def _make_adapter():
    run_value = MagicMock(return_value=10)
    run_row = MagicMock(return_value=(200.0, 150.0))
    run_rows = MagicMock(return_value=[])
    get_conn = MagicMock()
    return VMwareAdapter(get_conn, run_value, run_row, run_rows)


def test_fetch_single_dc_returns_dict_with_all_keys():
    adapter = _make_adapter()
    cursor = MagicMock()
    result = adapter.fetch_single_dc(cursor, "DC11", "2026-03-01", "2026-03-07")
    assert "counts" in result
    assert "memory" in result
    assert "storage" in result
    assert "cpu" in result


def test_fetch_single_dc_counts_uses_run_row():
    adapter = _make_adapter()
    cursor = MagicMock()
    result = adapter.fetch_single_dc(cursor, "DC11", "2026-03-01", "2026-03-07")
    assert result["counts"] == (200.0, 150.0)


def test_fetch_batch_queries_returns_five_tuples():
    adapter = _make_adapter()
    queries = adapter.fetch_batch_queries(["DC11"], ["%DC11%"], "2026-03-01", "2026-03-07")
    assert len(queries) == 5


def test_fetch_batch_queries_labels_are_correct():
    adapter = _make_adapter()
    queries = adapter.fetch_batch_queries(["DC11"], ["%DC11%"], "2026-03-01", "2026-03-07")
    labels = [q[0] for q in queries]
    assert "v_cnt" in labels
    assert "v_mem" in labels
    assert "v_stor" in labels
    assert "v_cpu" in labels
    assert "v_platform" in labels


def test_fetch_batch_queries_each_tuple_has_three_elements():
    adapter = _make_adapter()
    queries = adapter.fetch_batch_queries(["DC11"], ["%DC11%"], "2026-03-01", "2026-03-07")
    for q in queries:
        assert len(q) == 3
