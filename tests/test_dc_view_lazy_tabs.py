"""Verify summary-only DC build skips heavy tab fetches."""
from unittest.mock import patch


def test_summary_eager_skips_backup_and_network_fetch():
    from src.pages.dc_view import _SUMMARY_EAGER_TABS, build_dc_view

    calls: list[str] = []

    def _track(name):
        def _fn(*_a, **_k):
            calls.append(name)
            if name == "get_dc_details":
                return {
                    "meta": {"name": "IST1", "location": "Istanbul"},
                    "classic": {"hosts": 1, "cpu_cap": 10, "cpu_used": 5, "mem_cap": 100, "mem_used": 50, "stor_cap": 1, "stor_used": 0.5},
                    "hyperconv": {},
                    "power": {},
                    "energy": {},
                    "intel": {"vms": 0},
                }
            if name == "get_sla_by_dc":
                return {}
            if name == "get_classic_cluster_list":
                return ["c1"]
            if name == "get_hyperconv_cluster_list":
                return []
            if name == "get_sellable_summary_light":
                return {"families": [], "total_potential_tl": 0}
            return {}

        return _fn

    api_patch = {
        "get_dc_details": _track("get_dc_details"),
        "get_sla_by_dc": _track("get_sla_by_dc"),
        "get_classic_cluster_list": _track("get_classic_cluster_list"),
        "get_hyperconv_cluster_list": _track("get_hyperconv_cluster_list"),
        "get_sellable_summary_light": _track("get_sellable_summary_light"),
        "get_dc_netbackup_pools": _track("get_dc_netbackup_pools"),
        "get_dc_network_filters": _track("get_dc_network_filters"),
    }

    with patch.multiple("src.pages.dc_view.api", **api_patch):
        build_dc_view("IST1", time_range={"preset": "7d"}, eager_tabs=_SUMMARY_EAGER_TABS)

    assert "get_dc_details" in calls
    assert "get_sellable_summary_light" in calls
    assert "get_dc_netbackup_pools" not in calls
    assert "get_dc_network_filters" not in calls
    assert "get_classic_host_rows" not in calls
    assert "get_hyperconv_host_rows" not in calls


def test_virt_eager_skips_host_prefetch():
    from unittest.mock import patch

    from src.pages.dc_view import build_dc_view

    calls: list[str] = []

    def _track(name):
        def _fn(*_a, **_k):
            calls.append(name)
            if name == "get_dc_details":
                return {
                    "meta": {"name": "DC13", "location": "Istanbul"},
                    "classic": {
                        "hosts": 1, "cpu_cap": 10, "cpu_used": 5,
                        "mem_cap": 100, "mem_used": 50, "stor_cap": 1, "stor_used": 0.5,
                    },
                    "hyperconv": {},
                    "power": {},
                    "energy": {},
                    "intel": {"vms": 0},
                }
            if name == "get_sla_by_dc":
                return {}
            if name == "get_classic_cluster_list":
                return ["c1"]
            if name == "get_hyperconv_cluster_list":
                return []
            return {}

        return _fn

    api_patch = {
        "get_dc_details": _track("get_dc_details"),
        "get_sla_by_dc": _track("get_sla_by_dc"),
        "get_classic_cluster_list": _track("get_classic_cluster_list"),
        "get_hyperconv_cluster_list": _track("get_hyperconv_cluster_list"),
        "get_classic_host_rows": _track("get_classic_host_rows"),
        "get_hyperconv_host_rows": _track("get_hyperconv_host_rows"),
        "get_dc_storage_capacity": _track("get_dc_storage_capacity"),
        "get_dc_storage_performance": _track("get_dc_storage_performance"),
        "get_dc_san_bottleneck": _track("get_dc_san_bottleneck"),
    }

    with patch.multiple("src.pages.dc_view.api", **api_patch):
        build_dc_view("DC13", time_range={"preset": "7d"}, eager_tabs=frozenset({"virt"}))

    assert "get_classic_host_rows" not in calls
    assert "get_hyperconv_host_rows" not in calls


def test_storage_eager_fetches_ibm_storage():
    from src.pages.dc_view import build_dc_view

    calls: list[str] = []

    def _track(name):
        def _fn(*_a, **_k):
            calls.append(name)
            if name == "get_dc_details":
                return {
                    "meta": {"name": "DC13", "location": "Istanbul"},
                    "classic": {"hosts": 1, "cpu_cap": 10, "mem_cap": 100},
                    "hyperconv": {},
                    "power": {"storage_cap_tb": 100},
                    "energy": {},
                    "intel": {"vms": 0},
                }
            if name == "get_sla_by_dc":
                return {}
            if name == "get_dc_storage_capacity":
                return {"systems": [{"name": "IBM9500DC13"}]}
            if name == "get_dc_storage_performance":
                return {"series": []}
            if name == "get_dc_s3_pools":
                return {"pools": []}
            if name == "get_dc_zabbix_storage_capacity":
                return {"storage_device_count": 0}
            if name == "get_dc_datastore_mapping":
                return {"datastore_count": 2, "datastores": []}
            return {}

        return _fn

    api_patch = {
        "get_dc_details": _track("get_dc_details"),
        "get_sla_by_dc": _track("get_sla_by_dc"),
        "get_dc_storage_capacity": _track("get_dc_storage_capacity"),
        "get_dc_storage_performance": _track("get_dc_storage_performance"),
        "get_dc_s3_pools": _track("get_dc_s3_pools"),
        "get_dc_zabbix_storage_capacity": _track("get_dc_zabbix_storage_capacity"),
        "get_dc_zabbix_storage_devices": _track("get_dc_zabbix_storage_devices"),
        "get_dc_zabbix_storage_trend": _track("get_dc_zabbix_storage_trend"),
        "get_dc_datastore_mapping": _track("get_dc_datastore_mapping"),
        "get_dc_san_bottleneck": _track("get_dc_san_bottleneck"),
    }

    with patch.multiple("src.pages.dc_view.api", **api_patch):
        build_dc_view("DC13", time_range={"preset": "7d"}, eager_tabs=frozenset({"storage"}))

    assert "get_dc_storage_capacity" in calls
    assert "get_dc_san_bottleneck" not in calls
