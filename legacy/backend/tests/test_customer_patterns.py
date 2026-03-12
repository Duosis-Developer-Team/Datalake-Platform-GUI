def _build_patterns(customer_name):
    name = (customer_name or "").strip()
    return {
        "vm_pattern": f"{name}-%" if name else "%",
        "lpar_pattern": f"{name}%" if name else "%",
        "veeam_pattern": f"{name}%" if name else "%",
        "storage_like": f"%{name}%" if name else "%",
        "netbackup_workload": f"%{name}%" if name else "%",
        "zerto_name_like": f"{name}%-%" if name else "%",
    }


def test_vm_pattern_appends_dash_wildcard_for_standard_customer():
    p = _build_patterns("Boyner")
    assert p["vm_pattern"] == "Boyner-%"


def test_lpar_pattern_appends_wildcard_without_dash():
    p = _build_patterns("Boyner")
    assert p["lpar_pattern"] == "Boyner%"


def test_storage_like_pattern_wraps_name_with_wildcards():
    p = _build_patterns("Boyner")
    assert p["storage_like"] == "%Boyner%"


def test_zerto_pattern_appends_dash_wildcard():
    p = _build_patterns("Boyner")
    assert p["zerto_name_like"] == "Boyner%-%"


def test_empty_customer_name_produces_wildcard_only_vm_pattern():
    p = _build_patterns("")
    assert p["vm_pattern"] == "%"


def test_empty_customer_name_produces_wildcard_only_lpar_pattern():
    p = _build_patterns("")
    assert p["lpar_pattern"] == "%"


def test_none_customer_name_treated_as_empty():
    p = _build_patterns(None)
    assert p["vm_pattern"] == "%"
    assert p["storage_like"] == "%"


def test_customer_name_with_whitespace_is_stripped():
    p = _build_patterns("  Boyner  ")
    assert p["vm_pattern"] == "Boyner-%"
    assert p["lpar_pattern"] == "Boyner%"


def test_patterns_work_for_multi_word_customer_name():
    p = _build_patterns("ACME Corp")
    assert p["vm_pattern"] == "ACME Corp-%"
    assert p["storage_like"] == "%ACME Corp%"
