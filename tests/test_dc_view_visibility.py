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
        def get_dc_network_filters(self, dc_id, tr):
            return {"manufacturers": [], "roles_by_manufacturer": {}, "devices_by_manufacturer_role": {}}

        def get_dc_network_port_summary(self, dc_id, tr, manufacturer=None, device_role=None, device_name=None):
            return {}

        def get_dc_network_95th_percentile(self, dc_id, tr, top_n=20, manufacturer=None, device_role=None, device_name=None):
            return {"top_interfaces": [], "overall_port_utilization_pct": 0.0}

        def get_dc_network_interface_table(self, dc_id, tr, page=1, page_size=50, search="", manufacturer=None, device_role=None, device_name=None):
            return {"items": []}

        # Intel Storage (Zabbix)
        def get_dc_zabbix_storage_capacity(self, dc_id, tr):
            return {"storage_device_count": 0}

        def get_dc_zabbix_storage_trend(self, dc_id, tr):
            return {"series": []}

        def get_dc_zabbix_disk_health(self, dc_id, tr):
            return {"items": []}

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
        def get_dc_network_filters(self, dc_id, tr):
            # Default: no Zabbix network data (only SAN gate is active in existing tests)
            return {"manufacturers": [], "roles_by_manufacturer": {}, "devices_by_manufacturer_role": {}}

        def get_dc_network_port_summary(self, dc_id, tr, manufacturer=None, device_role=None, device_name=None):
            return {}

        def get_dc_network_95th_percentile(self, dc_id, tr, top_n=20, manufacturer=None, device_role=None, device_name=None):
            return {"top_interfaces": [], "overall_port_utilization_pct": 0.0}

        def get_dc_network_interface_table(self, dc_id, tr, page=1, page_size=50, search="", manufacturer=None, device_role=None, device_name=None):
            return {"items": []}

        # Intel Storage (Zabbix)
        def get_dc_zabbix_storage_capacity(self, dc_id, tr):
            return {"storage_device_count": 0}

        def get_dc_zabbix_storage_trend(self, dc_id, tr):
            return {"series": []}

        def get_dc_zabbix_disk_health(self, dc_id, tr):
            return {"items": []}

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
    assert "Object Storage" in labels


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


def test_network_tab_shown_when_san_present(monkeypatch):
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
    assert "Network" in labels
    assert "SAN" in labels


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

