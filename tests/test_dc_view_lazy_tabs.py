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
