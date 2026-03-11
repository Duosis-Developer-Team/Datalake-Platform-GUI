from app.services.db_service import _DC_CODE_RE


def _extract_dc(server_name, dc_set_upper):
    if not server_name:
        return None
    m = _DC_CODE_RE.search(server_name.upper())
    if m and m.group(1) in dc_set_upper:
        return m.group(1)
    return None


def _deduplicate_hosts(raw_rows, dc_set_upper):
    acc = {}
    for row in raw_rows:
        dc = _extract_dc(row[0], dc_set_upper) if row else None
        if dc:
            acc.setdefault(dc, set()).add(row[0])
    return {dc: len(names) for dc, names in acc.items()}


def test_ibm_host_dedup_counts_unique_hostnames_only():
    rows = [("DC11-srv1",), ("DC11-srv1",), ("DC11-srv2",)]
    result = _deduplicate_hosts(rows, {"DC11"})
    assert result["DC11"] == 2


def test_ibm_host_dedup_separates_hosts_by_dc_code():
    rows = [("DC11-srv1",), ("DC12-srv1",), ("DC11-srv2",)]
    result = _deduplicate_hosts(rows, {"DC11", "DC12"})
    assert result["DC11"] == 2
    assert result["DC12"] == 1


def test_ibm_host_dedup_ignores_rows_not_in_dc_set():
    rows = [("DC99-srv1",), ("DC11-srv1",)]
    result = _deduplicate_hosts(rows, {"DC11"})
    assert "DC99" not in result
    assert result.get("DC11") == 1


def test_ibm_host_dedup_returns_empty_for_no_matching_rows():
    rows = [("random-server",), ("another-host",)]
    result = _deduplicate_hosts(rows, {"DC11"})
    assert result == {}


def test_ibm_host_dedup_handles_empty_input():
    result = _deduplicate_hosts([], {"DC11"})
    assert result == {}


def test_ibm_host_dedup_handles_none_server_name_rows():
    rows = [(None,), ("DC11-srv1",)]
    result = _deduplicate_hosts(rows, {"DC11"})
    assert result["DC11"] == 1


def test_ibm_host_dedup_case_insensitive_dc_matching():
    rows = [("dc11-srv1",)]
    result = _deduplicate_hosts(rows, {"DC11"})
    assert result.get("DC11") == 1


def test_ibm_dedup_uses_set_so_identical_names_count_once():
    rows = [("DC11-srv1",), ("DC11-srv1",), ("DC11-srv1",)]
    result = _deduplicate_hosts(rows, {"DC11"})
    assert result["DC11"] == 1


def test_ibm_vios_dedup_counts_unique_vios_per_dc():
    rows = [("DC11-host1", "vios1"), ("DC11-host1", "vios1"), ("DC11-host2", "vios2")]
    acc = {}
    dc_set = {"DC11"}
    for row in rows:
        if row and len(row) > 1:
            dc = _extract_dc(row[0], dc_set)
            if dc:
                acc.setdefault(dc, set()).add(row[1])
    result = {dc: len(names) for dc, names in acc.items()}
    assert result["DC11"] == 2
