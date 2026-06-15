"""Verify summary-only DC build skips heavy tab fetches."""
import sys
import types
from unittest.mock import MagicMock, patch

if "pandas" not in sys.modules:
    _pd = types.ModuleType("pandas")

    class _FakeSeries(list):
        pass

    class _FakeIndex(list):
        pass

    _pd.DataFrame = MagicMock()
    _pd.Series = _FakeSeries
    _pd.Index = _FakeIndex
    sys.modules["pandas"] = _pd


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

    virt_sections = {
        "sec:dc_view:virtualization",
        "sub:dc_view:virt:classic",
    }
    with patch.multiple("src.pages.dc_view.api", **api_patch):
        build_dc_view(
            "DC13",
            time_range={"preset": "7d"},
            eager_tabs=frozenset({"virt"}),
            visible_sections=virt_sections,
        )

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


def test_build_virt_subtab_stack_classic_no_name_error():
    from dash import html

    from src.pages.dc_view import _build_virt_subtab_stack

    with patch("src.pages.dc_view._build_sellable_inline_kpi", return_value=html.Div(id="sellable-stub")), patch(
        "src.pages.dc_view._build_compute_tab",
        return_value=html.Div(id="compute-stub"),
    ):
        stack = _build_virt_subtab_stack(
            "classic",
            dc_id="DC13",
            classic={"hosts": 1, "cpu_cap": 10, "cpu_used": 5, "mem_cap": 100, "mem_used": 50},
            hyperconv={},
            power={},
            energy={},
            classic_clusters=["c1"],
            hyperconv_clusters=[],
            storage_capacity=None,
            storage_performance=None,
            san_bottleneck=None,
            show_virt_hosts=False,
        )

    assert stack
    assert stack[0].id == "virt-classic-cluster-draft"
    from src.pages.dc_view import _find_component_by_id

    assert _find_component_by_id(stack[0], "virt-classic-cluster-draft") is not None
    assert _find_component_by_id(stack[4], "virt-classic-cluster-popover") is not None


def test_build_dc_lazy_tab_panel_virt_no_name_error():
    from dash import html

    from src.pages.dc_view import build_dc_lazy_tab_panel

    def _track(name):
        def _fn(*_a, **_k):
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
    }

    virt_sections = {
        "sec:dc_view:virtualization",
        "sub:dc_view:virt:classic",
    }
    with patch.multiple("src.pages.dc_view.api", **api_patch), patch(
        "src.pages.dc_view.resolve_dc_display_from_summary",
        return_value=("DC13", "Istanbul"),
    ), patch(
        "src.pages.dc_view._build_virt_total_sellable_children",
        return_value=[],
    ), patch(
        "src.pages.dc_view._build_compute_tab",
        return_value=html.Div(id="compute-stub"),
    ):
        panel = build_dc_lazy_tab_panel(
            "DC13",
            "virt",
            time_range={"preset": "7d"},
            visible_sections=virt_sections,
        )

    assert panel is not None
    from src.pages.dc_view import _find_component_by_id

    roots = panel if isinstance(panel, (list, tuple)) else [panel]
    classic_selector = None
    for root in roots:
        classic_selector = _find_component_by_id(root, "virt-classic-cluster-draft")
        if classic_selector is not None:
            break
    assert classic_selector is not None
    for root in roots:
        assert _find_component_by_id(root, "virt-nested-content") is None


def test_virt_nested_tabs_eager_all_panels_present():
    from dash import html

    from src.pages.dc_view import _find_component_by_id, build_dc_view

    def _track(name):
        def _fn(*_a, **_k):
            if name == "get_dc_details":
                return {
                    "meta": {"name": "DC13", "location": "Istanbul"},
                    "classic": {
                        "hosts": 1, "cpu_cap": 10, "cpu_used": 5,
                        "mem_cap": 100, "mem_used": 50, "stor_cap": 1, "stor_used": 0.5,
                    },
                    "hyperconv": {"hosts": 2, "cpu_cap": 20, "cpu_used": 10, "mem_cap": 200, "mem_used": 100},
                    "power": {"hosts": 1, "vios": 2, "lpar_count": 4},
                    "energy": {},
                    "intel": {"vms": 0},
                }
            if name == "get_sla_by_dc":
                return {}
            if name == "get_classic_cluster_list":
                return ["c1"]
            if name == "get_hyperconv_cluster_list":
                return ["KM-1"]
            if name == "get_dc_storage_capacity":
                return {"systems": []}
            if name == "get_dc_storage_performance":
                return {"series": []}
            if name == "get_dc_san_bottleneck":
                return {"issues": []}
            return {}

        return _fn

    api_patch = {
        "get_dc_details": _track("get_dc_details"),
        "get_sla_by_dc": _track("get_sla_by_dc"),
        "get_classic_cluster_list": _track("get_classic_cluster_list"),
        "get_hyperconv_cluster_list": _track("get_hyperconv_cluster_list"),
        "get_dc_storage_capacity": _track("get_dc_storage_capacity"),
        "get_dc_storage_performance": _track("get_dc_storage_performance"),
        "get_dc_san_bottleneck": _track("get_dc_san_bottleneck"),
    }

    virt_sections = {
        "sec:dc_view:virtualization",
        "sub:dc_view:virt:classic",
        "sub:dc_view:virt:hyperconv",
        "sub:dc_view:virt:power",
    }
    with patch.multiple("src.pages.dc_view.api", **api_patch), patch(
        "src.pages.dc_view.resolve_dc_display_from_summary",
        return_value=("DC13", "Istanbul"),
    ), patch(
        "src.pages.dc_view._build_virt_total_sellable_children",
        return_value=[],
    ), patch(
        "src.pages.dc_view._build_compute_tab",
        return_value=html.Div(id="compute-stub"),
    ), patch(
        "src.pages.dc_view._build_power_tab",
        return_value=html.Div(id="power-stub"),
    ):
        page = build_dc_view(
            "DC13",
            time_range={"preset": "7d"},
            visible_sections=virt_sections,
            eager_tabs=frozenset({"virt"}),
        )

    assert _find_component_by_id(page, "virt-nested-content") is None
    assert _find_component_by_id(page, "virt-classic-cluster-draft") is not None
    assert _find_component_by_id(page, "virt-hyperconv-cluster-draft") is not None
    assert _find_component_by_id(page, "classic-virt-panel") is not None
    assert _find_component_by_id(page, "hyperconv-virt-panel") is not None
    assert _find_component_by_id(page, "power-stub") is not None


def test_build_virt_subtab_stack_hyperconv_no_name_error():
    from dash import html

    from src.pages.dc_view import _build_virt_subtab_stack

    with patch("src.pages.dc_view._build_sellable_inline_kpi", return_value=html.Div(id="sellable-stub")), patch(
        "src.pages.dc_view._build_compute_tab",
        return_value=html.Div(id="compute-stub"),
    ):
        stack = _build_virt_subtab_stack(
            "hyperconv",
            dc_id="DC13",
            classic={},
            hyperconv={"hosts": 2, "cpu_cap": 20, "cpu_used": 10, "mem_cap": 200, "mem_used": 100},
            power={},
            energy={},
            classic_clusters=[],
            hyperconv_clusters=["KM-1", "KM-2"],
            storage_capacity=None,
            storage_performance=None,
            san_bottleneck=None,
            show_virt_hosts=False,
        )

    assert stack
    assert stack[0].id == "virt-hyperconv-cluster-draft"
    from src.pages.dc_view import _find_component_by_id

    assert _find_component_by_id(stack[4], "virt-hyperconv-cluster-checklist") is not None


def test_build_virt_subtab_stack_power_renders():
    from dash import html

    from src.pages.dc_view import _build_virt_subtab_stack

    with patch("src.pages.dc_view._build_sellable_inline_kpi", return_value=html.Div(id="sellable-stub")), patch(
        "src.pages.dc_view._build_power_tab",
        return_value=html.Div(id="power-stub"),
    ):
        stack = _build_virt_subtab_stack(
            "power",
            dc_id="DC13",
            classic={},
            hyperconv={},
            power={"hosts": 4, "vios": 8, "lpar_count": 12},
            energy={},
            classic_clusters=[],
            hyperconv_clusters=[],
            storage_capacity={"systems": []},
            storage_performance={"series": []},
            san_bottleneck={"issues": []},
            show_virt_hosts=False,
        )

    assert len(stack) == 2
    assert getattr(stack[0], "id", None) == "power-stub"


def test_build_virt_nested_subtab_panel_hyperconv_skips_storage_apis():
    from dash import html

    from src.pages.dc_view import build_virt_nested_subtab_panel

    ctx = {
        "dc_id": "DC13",
        "classic_clusters": ["c1"],
        "hyperconv_clusters": ["KM-1"],
        "show_virt_hosts": False,
    }

    def _details(*_a, **_k):
        return {
            "classic": {"hosts": 1},
            "hyperconv": {"hosts": 2, "cpu_cap": 10},
            "power": {"hosts": 1},
            "energy": {},
        }

    with patch("src.pages.dc_view.api.get_dc_details", side_effect=_details), patch(
        "src.pages.dc_view.api.get_dc_storage_capacity"
    ) as mock_cap, patch("src.pages.dc_view.api.get_dc_storage_performance") as mock_perf, patch(
        "src.pages.dc_view.api.get_dc_san_bottleneck"
    ) as mock_san, patch(
        "src.pages.dc_view._build_virt_subtab_stack",
        return_value=[html.Div(id="hyperconv-panel")],
    ) as mock_stack:
        panel, mount_ok = build_virt_nested_subtab_panel("hyperconv", ctx, {"preset": "7d"})

    assert mount_ok is True
    assert panel is not None
    mock_cap.assert_not_called()
    mock_perf.assert_not_called()
    mock_san.assert_not_called()
    assert mock_stack.call_args.kwargs["storage_capacity"] == {}
    assert mock_stack.call_args.kwargs["storage_performance"] == {}
    assert mock_stack.call_args.kwargs["san_bottleneck"] == {}


def test_build_virt_nested_subtab_panel_power_fetches_storage_apis():
    from dash import html

    from src.pages.dc_view import build_virt_nested_subtab_panel

    ctx = {"dc_id": "DC13", "classic_clusters": [], "hyperconv_clusters": [], "show_virt_hosts": False}
    cap_data = {"systems": [{"name": "IBM"}]}
    perf_data = {"series": []}
    san_data = {"issues": []}

    with patch(
        "src.pages.dc_view.api.get_dc_details",
        return_value={"classic": {}, "hyperconv": {}, "power": {"hosts": 1}, "energy": {}},
    ), patch("src.pages.dc_view.api.get_dc_storage_capacity", return_value=cap_data) as mock_cap, patch(
        "src.pages.dc_view.api.get_dc_storage_performance", return_value=perf_data
    ) as mock_perf, patch("src.pages.dc_view.api.get_dc_san_bottleneck", return_value=san_data) as mock_san, patch(
        "src.pages.dc_view._build_virt_subtab_stack",
        return_value=[html.Div(id="power-panel")],
    ) as mock_stack:
        panel, mount_ok = build_virt_nested_subtab_panel("power", ctx, {"preset": "7d"})

    assert mount_ok is True
    mock_cap.assert_called_once()
    mock_perf.assert_called_once()
    mock_san.assert_called_once()
    assert mock_stack.call_args.kwargs["storage_capacity"] == cap_data
    assert mock_stack.call_args.kwargs["storage_performance"] == perf_data
    assert mock_stack.call_args.kwargs["san_bottleneck"] == san_data


def test_build_virt_nested_subtab_panel_failure_returns_alert():
    import dash_mantine_components as dmc

    from src.pages.dc_view import build_virt_nested_subtab_panel

    ctx = {"dc_id": "DC13", "classic_clusters": [], "hyperconv_clusters": [], "show_virt_hosts": False}

    with patch("src.pages.dc_view.api.get_dc_details", side_effect=RuntimeError("boom")):
        panel, mount_ok = build_virt_nested_subtab_panel("power", ctx, {"preset": "7d"})

    assert mount_ok is False
    assert isinstance(panel, dmc.Stack)


def test_storage_tab_empty_state_returns_alert():
    import dash_mantine_components as dmc

    from src.pages.dc_view import _storage_tab_content_or_empty

    panel = _storage_tab_content_or_empty(
        has_intel_storage=False,
        has_ibm_storage=False,
        has_power=False,
        has_s3=False,
        has_san=False,
        zabbix_storage_devices=[],
        zabbix_storage_capacity={},
        zabbix_storage_trend={},
        storage_capacity={},
        storage_performance={},
        dc_name="AZ11",
        s3_data={"pools": []},
        tr={"preset": "7d"},
        san_port_usage={},
        san_health_alerts=[],
        san_traffic_trend=[],
    )
    assert panel is not None
    assert "No storage metrics available" in str(panel)
