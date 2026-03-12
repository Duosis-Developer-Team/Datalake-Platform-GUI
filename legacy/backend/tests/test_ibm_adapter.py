from unittest.mock import MagicMock

from app.adapters.ibm_power_adapter import IBMPowerAdapter, _DC_CODE_RE, _extract_dc


def _make_adapter():
    run_value = MagicMock(return_value=3)
    run_row = MagicMock(return_value=(512.0, 256.0))
    run_rows = MagicMock(return_value=[])
    get_conn = MagicMock()
    return IBMPowerAdapter(get_conn, run_value, run_row, run_rows)


def test_dc_code_re_matches_dc11():
    assert _DC_CODE_RE.search("DC11") is not None


def test_dc_code_re_matches_az11():
    assert _DC_CODE_RE.search("AZ11") is not None


def test_dc_code_re_matches_ict11():
    assert _DC_CODE_RE.search("ICT11") is not None


def test_dc_code_re_matches_uz11():
    assert _DC_CODE_RE.search("UZ11") is not None


def test_dc_code_re_matches_dh11():
    assert _DC_CODE_RE.search("DH11") is not None


def test_dc_code_re_matches_embedded_in_hostname():
    m = _DC_CODE_RE.search("server-DC11-host1")
    assert m is not None
    assert m.group(1).upper() == "DC11"


def test_dc_code_re_is_case_insensitive():
    assert _DC_CODE_RE.search("dc11-server") is not None


def test_dc_code_re_does_not_match_random_text():
    assert _DC_CODE_RE.search("random-server-name") is None


def test_dc_code_re_does_not_match_partial_prefix():
    assert _DC_CODE_RE.search("DCserver") is None


def test_dc_code_re_captures_dc16():
    m = _DC_CODE_RE.search("DC16-backup")
    assert m is not None
    assert m.group(1).upper() == "DC16"


def test_extract_dc_returns_dc_code_when_in_set():
    result = _extract_dc("DC11-server-name", {"DC11"})
    assert result == "DC11"


def test_extract_dc_returns_none_when_not_in_set():
    result = _extract_dc("DC12-server-name", {"DC11"})
    assert result is None


def test_extract_dc_returns_none_for_empty_string():
    result = _extract_dc("", {"DC11"})
    assert result is None


def test_extract_dc_returns_none_for_none_input():
    result = _extract_dc(None, {"DC11"})
    assert result is None


def test_extract_dc_srv_dc14_hmc01_returns_dc14():
    result = _extract_dc("srv-DC14-hmc01", {"DC14"})
    assert result == "DC14"


def test_extract_dc_lowercase_dc14_returns_dc14():
    result = _extract_dc("dc14-lowercase-test", {"DC14"})
    assert result == "DC14"


def test_extract_dc_multi_dc_name_returns_first_match():
    result = _extract_dc("multi-DC11-DC12-name", {"DC11", "DC12"})
    assert result == "DC11"


def test_fetch_single_dc_returns_dict_with_all_keys():
    adapter = _make_adapter()
    cursor = MagicMock()
    result = adapter.fetch_single_dc(cursor, "%DC11%", "2026-03-01", "2026-03-07")
    assert "host_count" in result
    assert "vios_count" in result
    assert "lpar_count" in result
    assert "memory" in result
    assert "cpu" in result


def test_fetch_batch_queries_returns_five_tuples():
    adapter = _make_adapter()
    queries = adapter.fetch_batch_queries(["DC11"], ["%DC11%"], "2026-03-01", "2026-03-07")
    assert len(queries) == 5


def test_fetch_batch_queries_labels_are_raw():
    adapter = _make_adapter()
    queries = adapter.fetch_batch_queries(["DC11"], ["%DC11%"], "2026-03-01", "2026-03-07")
    labels = [q[0] for q in queries]
    assert "ibm_host_raw" in labels
    assert "ibm_vios_raw" in labels
    assert "ibm_lpar_raw" in labels
    assert "ibm_mem_raw" in labels
    assert "ibm_cpu_raw" in labels


def test_process_raw_batch_deduplicates_hosts():
    adapter = _make_adapter()
    raw_data = {
        "ibm_host_raw": [("DC11-srv1",), ("DC11-srv1",), ("DC11-srv2",)],
        "ibm_vios_raw": [],
        "ibm_lpar_raw": [],
        "ibm_mem_raw": [],
        "ibm_cpu_raw": [],
    }
    result = adapter.process_raw_batch(raw_data, {"DC11"})
    assert result["hosts"]["DC11"] == 2


def test_process_raw_batch_returns_all_keys():
    adapter = _make_adapter()
    raw_data = {
        "ibm_host_raw": [],
        "ibm_vios_raw": [],
        "ibm_lpar_raw": [],
        "ibm_mem_raw": [],
        "ibm_cpu_raw": [],
    }
    result = adapter.process_raw_batch(raw_data, {"DC11"})
    assert "hosts" in result
    assert "vios" in result
    assert "lpar" in result
    assert "mem" in result
    assert "cpu" in result


def test_process_raw_batch_memory_averages_two_records():
    adapter = _make_adapter()
    raw_data = {
        "ibm_host_raw": [],
        "ibm_vios_raw": [],
        "ibm_lpar_raw": [],
        "ibm_mem_raw": [
            ("DC11-srv1", 100.0, 50.0),
            ("DC11-srv2", 200.0, 100.0),
        ],
        "ibm_cpu_raw": [],
    }
    result = adapter.process_raw_batch(raw_data, {"DC11"})
    assert result["mem"]["DC11"] == (150.0, 75.0)


def test_process_raw_batch_cpu_averages_three_tuples():
    adapter = _make_adapter()
    raw_data = {
        "ibm_host_raw": [],
        "ibm_vios_raw": [],
        "ibm_lpar_raw": [],
        "ibm_mem_raw": [],
        "ibm_cpu_raw": [
            ("DC11-srv1", 1.0, 2.0, 3.0),
            ("DC11-srv2", 3.0, 4.0, 5.0),
            ("DC11-srv3", 5.0, 6.0, 7.0),
        ],
    }
    result = adapter.process_raw_batch(raw_data, {"DC11"})
    cpu = result["cpu"]["DC11"]
    assert round(cpu[0], 4) == 3.0
    assert round(cpu[1], 4) == 4.0
    assert round(cpu[2], 4) == 5.0


def test_process_raw_batch_ignores_hosts_not_in_dc_set():
    adapter = _make_adapter()
    raw_data = {
        "ibm_host_raw": [("DC99-srv1",), ("DC11-srv1",)],
        "ibm_vios_raw": [],
        "ibm_lpar_raw": [],
        "ibm_mem_raw": [],
        "ibm_cpu_raw": [],
    }
    result = adapter.process_raw_batch(raw_data, {"DC11"})
    assert "DC99" not in result["hosts"]
    assert result["hosts"].get("DC11") == 1


def test_process_raw_batch_deduplicates_vios():
    adapter = _make_adapter()
    raw_data = {
        "ibm_host_raw": [],
        "ibm_vios_raw": [
            ("DC11-host1", "vios1"),
            ("DC11-host1", "vios1"),
            ("DC11-host2", "vios2"),
        ],
        "ibm_lpar_raw": [],
        "ibm_mem_raw": [],
        "ibm_cpu_raw": [],
    }
    result = adapter.process_raw_batch(raw_data, {"DC11"})
    assert result["vios"]["DC11"] == 2


def test_process_raw_batch_deduplicates_lpar():
    adapter = _make_adapter()
    raw_data = {
        "ibm_host_raw": [],
        "ibm_vios_raw": [],
        "ibm_lpar_raw": [
            ("DC11-host1", "lpar1"),
            ("DC11-host1", "lpar1"),
            ("DC11-host2", "lpar2"),
        ],
        "ibm_mem_raw": [],
        "ibm_cpu_raw": [],
    }
    result = adapter.process_raw_batch(raw_data, {"DC11"})
    assert result["lpar"]["DC11"] == 2


def test_process_raw_batch_skips_short_mem_rows():
    adapter = _make_adapter()
    raw_data = {
        "ibm_host_raw": [],
        "ibm_vios_raw": [],
        "ibm_lpar_raw": [],
        "ibm_mem_raw": [
            ("DC11-srv1",),
            ("DC11-srv2", 100.0, 50.0),
        ],
        "ibm_cpu_raw": [],
    }
    result = adapter.process_raw_batch(raw_data, {"DC11"})
    assert result["mem"]["DC11"] == (100.0, 50.0)


def test_process_raw_batch_three_distinct_hosts_count_three():
    adapter = _make_adapter()
    raw_data = {
        "ibm_host_raw": [("DC11-srv1",), ("DC11-srv2",), ("DC11-srv3",)],
        "ibm_vios_raw": [],
        "ibm_lpar_raw": [],
        "ibm_mem_raw": [],
        "ibm_cpu_raw": [],
    }
    result = adapter.process_raw_batch(raw_data, {"DC11"})
    assert result["hosts"]["DC11"] == 3


def test_process_raw_batch_memory_section_2_3_exact_values():
    adapter = _make_adapter()
    raw_data = {
        "ibm_host_raw": [],
        "ibm_vios_raw": [],
        "ibm_lpar_raw": [],
        "ibm_mem_raw": [
            ("DC11-srv1", 100.0, 80.0),
            ("DC11-srv2", 200.0, 160.0),
        ],
        "ibm_cpu_raw": [],
    }
    result = adapter.process_raw_batch(raw_data, {"DC11"})
    assert result["mem"]["DC11"] == (150.0, 120.0)


def test_process_raw_batch_cpu_section_2_3_exact_values():
    adapter = _make_adapter()
    raw_data = {
        "ibm_host_raw": [],
        "ibm_vios_raw": [],
        "ibm_lpar_raw": [],
        "ibm_mem_raw": [],
        "ibm_cpu_raw": [
            ("DC11-srv1", 10.0, 8.0, 6.0),
            ("DC11-srv2", 20.0, 16.0, 12.0),
        ],
    }
    result = adapter.process_raw_batch(raw_data, {"DC11"})
    assert result["cpu"]["DC11"] == (15.0, 12.0, 9.0)


def test_process_raw_batch_skips_short_cpu_rows():
    adapter = _make_adapter()
    raw_data = {
        "ibm_host_raw": [],
        "ibm_vios_raw": [],
        "ibm_lpar_raw": [],
        "ibm_mem_raw": [],
        "ibm_cpu_raw": [
            ("DC11-srv1", 1.0),
            ("DC11-srv2", 2.0, 3.0, 4.0),
        ],
    }
    result = adapter.process_raw_batch(raw_data, {"DC11"})
    assert result["cpu"]["DC11"] == (2.0, 3.0, 4.0)
