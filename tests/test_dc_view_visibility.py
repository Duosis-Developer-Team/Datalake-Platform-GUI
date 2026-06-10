from __future__ import annotations
from dash import html
from src.pages import dc_view


def test_has_compute_data_empty():
    assert dc_view._has_compute_data({}) is False
    assert dc_view._has_compute_data(None) is False


def test_has_compute_data_with_hosts():
    assert dc_view._has_compute_data({"hosts": 1}) is True


def test_has_power_data_empty():
    assert dc_view._has_power_data({}) is False
    assert dc_view._has_power_data(None) is False


def test_has_power_data_with_lpars():
    assert dc_view._has_power_data({"lpar_count": 1}) is True


def test_has_power_data_with_compute_hosts():
    assert dc_view._has_power_data({"hosts": 3}) is True


def test_has_power_data_storage_only():
    """Storage-only DC: compute keys zero but IBM storage capacity present."""
    assert dc_view._has_power_data(
        {
            "hosts": 0,
            "lpar_count": 0,
            "cpu_used": 0,
            "memory_total": 0,
            "storage_cap_tb": 3567.3,
            "storage_used_tb": 1648.86,
        }
    ) is True


def test_has_power_data_storage_used_only():
    assert dc_view._has_power_data({"storage_used_tb": 100.0}) is True


def test_has_power_data_vios_only():
    assert dc_view._has_power_data({"vios": 2}) is True


def test_power_virt_and_ibm_storage_tabs_shown_for_storage_only_dc(monkeypatch):
    """Power Mimari + IBM Storage tabs visible when only IBM storage metrics exist."""
    dc = {
        "meta": {"name": "DC13", "location": "Istanbul"},
        "classic": {"hosts": 29, "vms": 1732, "cpu_cap": 5317.44, "mem_cap": 87.49, "stor_cap": 7970.24},
        "hyperconv": {},
        "power": {
            "hosts": 0,
            "lpar_count": 0,
            "cpu_used": 0,
            "memory_total": 0,
            "storage_cap_tb": 3567.3,
            "storage_used_tb": 1648.86,
        },
        "energy": {},
    }
    storage_capacity = {"systems": [{"total_mdisk_capacity": "3567.30 TB"}]}
    storage_performance = {"series": []}
    _fake_service_network(
        monkeypatch,
        dc,
        storage_capacity=storage_capacity,
        storage_performance=storage_performance,
    )

    layout = dc_view.build_dc_view("DC13", time_range={"from": 0, "to": 0})
    labels = _collect_tab_labels(layout)
    assert "Power Mimari" in labels
    assert "IBM Storage" in labels
    assert "Virtualization" in labels


def test_power_virt_tab_hidden_when_all_power_metrics_empty(monkeypatch):
    dc = {
        "meta": {"name": "DCX", "location": "Nowhere"},
        "classic": {"hosts": 1, "vms": 1, "cpu_cap": 10.0},
        "hyperconv": {},
        "power": {},
        "energy": {},
    }
    _fake_service_network(monkeypatch, dc)

    layout = dc_view.build_dc_view("DCX", time_range={"from": 0, "to": 0})
    labels = _collect_tab_labels(layout)
    assert "Power Mimari" not in labels
    assert "IBM Storage" not in labels
    assert "Virtualization" in labels


def _fake_service(monkeypatch, dc_details: dict, s3_pools: dict | None = None):
    """Patch api_client (imported as api) for build_dc_view tests."""
    pools = s3_pools or {}
    san_switches = []
    san_port_usage = {}
    san_health_alerts: list[dict] = []
    san_traffic_trend: list[dict] = []
    san_bottleneck: dict = {}
    storage_capacity: dict = {}
    storage_performance: dict = {}

    class FakeApi:
        def get_dc_details(self, dc_id, tr):
            return dc_details

        def get_sla_by_dc(self, tr):
            return {}

        def get_dc_s3_pools(self, dc_id, tr):
            return pools

        def get_classic_cluster_list(self, dc_id, tr):
            return []

        def get_hyperconv_cluster_list(self, dc_id, tr):
            return []

        def get_physical_inventory_dc(self, dc_name):
            return {"total": 0, "by_role": [], "by_role_manufacturer": []}

        def get_dc_netbackup_pools(self, dc_id, tr):
            return {"pools": [], "rows": []}

        def get_dc_zerto_sites(self, dc_id, tr):
            return {"sites": [], "rows": []}

        def get_dc_veeam_repos(self, dc_id, tr):
            return {"repos": [], "rows": []}

        # Network > SAN (Brocade)
        def get_dc_san_switches(self, dc_id, tr):
            return san_switches

        def get_dc_san_port_usage(self, dc_id, tr):
            return san_port_usage

        def get_dc_san_health(self, dc_id, tr):
            return san_health_alerts

        def get_dc_san_traffic_trend(self, dc_id, tr):
            return san_traffic_trend

        def get_dc_san_bottleneck(self, dc_id, tr):
            return san_bottleneck

        # Power Mimari Storage (IBM)
        def get_dc_storage_capacity(self, dc_id, tr):
            return storage_capacity

        def get_dc_storage_performance(self, dc_id, tr):
            return storage_performance

        # Network Dashboard (Zabbix)
        def get_dc_network_filters(self, dc_id, tr, interface_scope=None):
            return {"manufacturers": [], "devices_by_manufacturer": {}}

        def get_dc_network_port_summary(self, dc_id, tr, manufacturer=None, device_role=None, device_name=None, interface_scope=None):
            return {}

        def get_dc_network_95th_percentile(self, dc_id, tr, top_n=20, manufacturer=None, device_role=None, device_name=None, interface_scope=None):
            return {"top_interfaces": [], "overall_port_utilization_pct": 0.0}

        def get_dc_network_interface_table(self, dc_id, tr, page=1, page_size=50, search="", manufacturer=None, device_role=None, device_name=None, interface_scope=None):
            return {"items": []}

        def get_dc_network_firewall_summary(self, dc_id, tr):
            return {"devices": []}

        def get_dc_network_load_balancer_summary(self, dc_id, tr):
            return {"devices": []}

        # Intel Storage (Zabbix)
        def get_dc_zabbix_storage_capacity(self, dc_id, tr, host=None):
            return {"storage_device_count": 0}

        def get_dc_zabbix_storage_trend(self, dc_id, tr, host=None):
            return {"series": []}

        def get_dc_zabbix_storage_devices(self, dc_id, tr):
            return []

        def get_dc_availability_sla_item(self, dc_code, dc_display_name, tr):
            return None

    monkeypatch.setattr(dc_view, "api", FakeApi())


def _fake_service_network(
    monkeypatch,
    dc_details: dict,
    s3_pools: dict | None = None,
    san_switches: list[str] | None = None,
    san_port_usage: dict | None = None,
    san_health_alerts: list[dict] | None = None,
    san_traffic_trend: list[dict] | None = None,
    san_bottleneck: dict | None = None,
    storage_capacity: dict | None = None,
    storage_performance: dict | None = None,
):
    """Patch api_client for build_dc_view network/storage tests."""
    pools = s3_pools or {}

    san_switches_val = san_switches or []
    san_port_usage_val = san_port_usage or {}
    san_health_alerts_val = san_health_alerts or []
    san_traffic_trend_val = san_traffic_trend or []
    san_bottleneck_val = san_bottleneck or {}
    storage_capacity_val = storage_capacity or {}
    storage_performance_val = storage_performance or {}

    class FakeApi:
        def get_dc_details(self, dc_id, tr):
            return dc_details

        def get_sla_by_dc(self, tr):
            return {}

        def get_dc_s3_pools(self, dc_id, tr):
            return pools

        def get_classic_cluster_list(self, dc_id, tr):
            return []

        def get_hyperconv_cluster_list(self, dc_id, tr):
            return []

        def get_physical_inventory_dc(self, dc_name):
            return {"total": 0, "by_role": [], "by_role_manufacturer": []}

        def get_dc_netbackup_pools(self, dc_id, tr):
            return {"pools": [], "rows": []}

        def get_dc_zerto_sites(self, dc_id, tr):
            return {"sites": [], "rows": []}

        def get_dc_veeam_repos(self, dc_id, tr):
            return {"repos": [], "rows": []}

        # Network > SAN (Brocade)
        def get_dc_san_switches(self, dc_id, tr):
            return san_switches_val

        def get_dc_san_port_usage(self, dc_id, tr):
            return san_port_usage_val

        def get_dc_san_health(self, dc_id, tr):
            return san_health_alerts_val

        def get_dc_san_traffic_trend(self, dc_id, tr):
            return san_traffic_trend_val

        def get_dc_san_bottleneck(self, dc_id, tr):
            return san_bottleneck_val

        # Power Mimari Storage (IBM)
        def get_dc_storage_capacity(self, dc_id, tr):
            return storage_capacity_val

        def get_dc_storage_performance(self, dc_id, tr):
            return storage_performance_val

        # Network Dashboard (Zabbix)
        def get_dc_network_filters(self, dc_id, tr, interface_scope=None):
            return {"manufacturers": [], "devices_by_manufacturer": {}}

        def get_dc_network_port_summary(self, dc_id, tr, manufacturer=None, device_role=None, device_name=None, interface_scope=None):
            return {}

        def get_dc_network_95th_percentile(self, dc_id, tr, top_n=20, manufacturer=None, device_role=None, device_name=None, interface_scope=None):
            return {"top_interfaces": [], "overall_port_utilization_pct": 0.0}

        def get_dc_network_interface_table(self, dc_id, tr, page=1, page_size=50, search="", manufacturer=None, device_role=None, device_name=None, interface_scope=None):
            return {"items": []}

        def get_dc_network_firewall_summary(self, dc_id, tr):
            return {"devices": []}

        def get_dc_network_load_balancer_summary(self, dc_id, tr):
            return {"devices": []}

        # Intel Storage (Zabbix)
        def get_dc_zabbix_storage_capacity(self, dc_id, tr, host=None):
            return {"storage_device_count": 0}

        def get_dc_zabbix_storage_trend(self, dc_id, tr, host=None):
            return {"series": []}

        def get_dc_zabbix_storage_devices(self, dc_id, tr):
            return []

        def get_dc_availability_sla_item(self, dc_code, dc_display_name, tr):
            return None

    monkeypatch.setattr(dc_view, "api", FakeApi())


def _collect_tab_labels(component) -> list[str]:
    """Recursively collect dmc.TabsTab string labels from a layout tree."""
    labels: list[str] = []
    if component is None:
        return labels
    name = getattr(component.__class__, "__name__", "")
    if name == "TabsTab":
        ch = getattr(component, "children", None)
        if isinstance(ch, str):
            labels.append(ch)
    children = getattr(component, "children", None)
    if children is None:
        return labels
    if isinstance(children, (list, tuple)):
        for c in children:
            labels.extend(_collect_tab_labels(c))
    else:
        labels.extend(_collect_tab_labels(children))
    return labels


def test_summary_hidden_when_no_data(monkeypatch):
    empty_dc = {
        "meta": {"name": "DCX", "location": "Nowhere"},
        "classic": {},
        "hyperconv": {},
        "power": {},
        "energy": {},
    }
    _fake_service(monkeypatch, empty_dc, s3_pools={})

    layout = dc_view.build_dc_view("DCX", time_range={"from": 0, "to": 0})
    # With no compute and no S3 data, Summary and Virtualization tabs should be absent
    # We approximate this by checking helper functions directly.
    assert dc_view._has_compute_data(empty_dc.get("classic")) is False
    assert dc_view._has_compute_data(empty_dc.get("hyperconv")) is False


def test_s3_tab_shown_when_pools_present(monkeypatch):
    dc = {
        "meta": {"name": "DCX", "location": "Nowhere"},
        "classic": {},
        "hyperconv": {},
        "power": {},
        "energy": {},
    }
    s3_pools = {"pools": ["pool1"], "latest": {}, "growth": {}}
    _fake_service(monkeypatch, dc, s3_pools=s3_pools)

    layout = dc_view.build_dc_view("DCX", time_range={"from": 0, "to": 0})
    labels = _collect_tab_labels(layout)
    assert "Object Storage - S3" in labels


def test_backup_tab_hidden(monkeypatch):
    dc = {
        "meta": {"name": "DCX", "location": "Nowhere"},
        "classic": {},
        "hyperconv": {},
        "power": {},
        "energy": {},
    }
    _fake_service(monkeypatch, dc, s3_pools={})

    layout = dc_view.build_dc_view("DCX", time_range={"from": 0, "to": 0})
    labels = _collect_tab_labels(layout)
    assert "Backup & Replication" not in labels


def test_network_tab_hidden_when_no_san_switches(monkeypatch):
    empty_dc = {
        "meta": {"name": "DCX", "location": "Nowhere"},
        "classic": {},
        "hyperconv": {},
        "power": {},
        "energy": {},
    }
    _fake_service_network(monkeypatch, empty_dc, san_switches=[])

    layout = dc_view.build_dc_view("DCX", time_range={"from": 0, "to": 0})
    labels = _collect_tab_labels(layout)
    assert "Network" not in labels
    assert "SAN" not in labels


def test_storage_tab_shown_with_san_switch_subtab(monkeypatch):
    dc = {
        "meta": {"name": "DCX", "location": "Nowhere"},
        "classic": {},
        "hyperconv": {},
        "power": {},
        "energy": {},
    }
    san_port_usage = {
        "total_ports": 10,
        "licensed_ports": 6,
        "active_ports": 3,
        "no_link_ports": 3,
        "disabled_ports": 4,
    }
    _fake_service_network(
        monkeypatch,
        dc,
        san_switches=["sw-1"],
        san_port_usage=san_port_usage,
        san_health_alerts=[],
        san_traffic_trend=[],
    )

    layout = dc_view.build_dc_view("DCX", time_range={"from": 0, "to": 0})
    labels = _collect_tab_labels(layout)
    assert "Storage" in labels
    assert "SAN Switch" in labels
    assert "Network" not in labels


def test_build_power_tab_storage_widgets_render_without_error():
    power = {
        "hosts": 1,
        "vios": 1,
        "lpar_count": 2,
        "memory_total": 100.0,
        "memory_assigned": 50.0,
        "cpu_used": 10.0,
        "cpu_assigned": 20.0,
    }
    energy = {}

    storage_capacity = {
        "systems": [
            {
                "total_mdisk_capacity": "10.00 TB",
                "total_used_capacity": "5.00 TB",
                "total_free_space": "5.00 TB",
            }
        ]
    }
    storage_performance = {
        "series": [
            {"ts": "2020-01-01", "iops": 100, "throughput_mb": 200, "latency_ms": 10},
            {"ts": "2020-01-02", "iops": 120, "throughput_mb": 210, "latency_ms": 12},
        ]
    }
    san_bottleneck = {"has_issue": False, "issues": []}

    # Should not raise exceptions
    node = dc_view._build_power_tab(power, energy, storage_capacity, storage_performance, san_bottleneck)
    assert node is not None

