# services/datacenter-api/tests/test_rack_load_aggregate.py
from app.services.rack_load import aggregate_rack_load, build_metric_index


def test_build_metric_index_lowercases_and_computes_percentages():
    index = build_metric_index(
        vmware_rows=[("ESX-13-01", 40.0, 100.0, 32.0, 64.0)],
        nutanix_rows=[],
        ibm_rows=[],
    )
    assert index["esx-13-01"]["cpu_pct"] == 40.0
    assert index["esx-13-01"]["ram_pct"] == 50.0
    assert index["esx-13-01"]["source"] == "vmware"


def test_rack_load_takes_the_worst_device_not_the_average():
    # One saturated host among three idle ones: a rack you cannot place work in.
    index = build_metric_index(
        vmware_rows=[
            ("h1", 5.0, 100.0, 5.0, 100.0),
            ("h2", 5.0, 100.0, 5.0, 100.0),
            ("h3", 5.0, 100.0, 5.0, 100.0),
            ("h4", 95.0, 100.0, 10.0, 100.0),
        ],
        nutanix_rows=[], ibm_rows=[],
    )
    rows = aggregate_rack_load(
        [("104", "h1"), ("104", "h2"), ("104", "h3"), ("104", "h4")], index
    )
    assert len(rows) == 1
    assert rows[0]["load_pct"] == 95.0          # MAX, not 27.5
    assert rows[0]["hottest_device"] == "h4"
    assert rows[0]["monitored_devices"] == 4
    assert rows[0]["total_devices"] == 4


def test_device_load_is_max_of_cpu_and_ram():
    index = build_metric_index([("h1", 10.0, 100.0, 90.0, 100.0)], [], [])
    rows = aggregate_rack_load([("104", "h1")], index)
    assert rows[0]["load_pct"] == 90.0
    assert rows[0]["cpu_pct"] == 10.0
    assert rows[0]["ram_pct"] == 90.0


def test_rack_with_devices_but_no_metrics_is_null_not_zero():
    # The tempting bug: unmonitored rendering as a healthy 0%.
    rows = aggregate_rack_load([("104", "switch-1"), ("104", "pdu-1")], {})
    assert rows[0]["load_pct"] is None
    assert rows[0]["monitored_devices"] == 0
    assert rows[0]["total_devices"] == 2


def test_name_matching_is_case_insensitive():
    index = build_metric_index([("ESX-13-01", 70.0, 100.0, 10.0, 100.0)], [], [])
    rows = aggregate_rack_load([("104", "esx-13-01")], index)
    assert rows[0]["load_pct"] == 70.0


def test_zero_capacity_never_divides_by_zero():
    index = build_metric_index([("h1", 5.0, 0.0, 5.0, 0.0)], [], [])
    assert index["h1"]["cpu_pct"] is None
    assert index["h1"]["ram_pct"] is None
    rows = aggregate_rack_load([("104", "h1")], index)
    assert rows[0]["load_pct"] is None


def test_ibm_memory_is_derived_from_available_not_used():
    # IBM reports available memory; used = total - available.
    index = build_metric_index([], [], [("pwr-1", 4.0, 10.0, 200.0, 50.0)])
    assert index["pwr-1"]["cpu_pct"] == 40.0
    assert index["pwr-1"]["ram_pct"] == 75.0
    assert index["pwr-1"]["source"] == "ibm"


def test_racks_are_returned_sorted_by_name():
    rows = aggregate_rack_load([("110", "a"), ("104", "b")], {})
    assert [r["rack_name"] for r in rows] == ["104", "110"]
