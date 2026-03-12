from unittest.mock import MagicMock, call

from app.adapters.energy_adapter import EnergyAdapter
from app.db.queries import energy as eq


def _make_adapter():
    run_value = MagicMock(return_value=500.0)
    get_conn = MagicMock()
    return EnergyAdapter(get_conn, run_value)


def test_fetch_single_dc_returns_dict_with_all_keys():
    adapter = _make_adapter()
    cursor = MagicMock()
    result = adapter.fetch_single_dc(cursor, "DC11", "%DC11%", "2026-03-01", "2026-03-07")
    assert "ibm_w" in result
    assert "vcenter_w" in result
    assert "ibm_kwh" in result
    assert "vcenter_kwh" in result


def test_fetch_single_dc_ibm_uses_dc_code_like():
    run_value = MagicMock(return_value=100.0)
    adapter = EnergyAdapter(MagicMock(), run_value)
    cursor = MagicMock()
    adapter.fetch_single_dc(cursor, "DC11", "%DC11%", "2026-03-01", "2026-03-07")
    ibm_calls = [c for c in run_value.call_args_list if c.args[1] == eq.IBM]
    assert len(ibm_calls) == 1
    assert ibm_calls[0].args[2][0] == "%DC11%"


def test_fetch_single_dc_vcenter_uses_dc_code_exact():
    run_value = MagicMock(return_value=100.0)
    adapter = EnergyAdapter(MagicMock(), run_value)
    cursor = MagicMock()
    adapter.fetch_single_dc(cursor, "DC11", "%DC11%", "2026-03-01", "2026-03-07")
    vcenter_calls = [c for c in run_value.call_args_list if c.args[1] == eq.VCENTER]
    assert len(vcenter_calls) == 1
    assert vcenter_calls[0].args[2][0] == "DC11"


def test_fetch_batch_queries_returns_four_tuples():
    adapter = _make_adapter()
    queries = adapter.fetch_batch_queries(["DC11"], ["%DC11%"], "2026-03-01", "2026-03-07")
    assert len(queries) == 4


def test_fetch_batch_queries_labels_are_correct():
    adapter = _make_adapter()
    queries = adapter.fetch_batch_queries(["DC11"], ["%DC11%"], "2026-03-01", "2026-03-07")
    labels = [q[0] for q in queries]
    assert "e_ibm" in labels
    assert "e_vcenter" in labels
    assert "e_ibm_kwh" in labels
    assert "e_vctr_kwh" in labels
