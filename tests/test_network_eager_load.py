"""Tests that build_dc_view eagerly fetches network payloads when Zabbix data exists."""

from __future__ import annotations

from src.pages import dc_view


def _fake_service_with_network(monkeypatch, *, call_log: list[str]):
    dc = {
        "meta": {"name": "DCNET", "location": "Test"},
        "classic": {"hosts": 1, "vms": 1, "cpu_cap": 10.0},
        "hyperconv": {},
        "power": {},
        "energy": {},
    }
    net_filters = {
        "manufacturers": ["Fortinet"],
        "roles_by_manufacturer": {"Fortinet": ["Core"]},
        "devices_by_manufacturer_role": {"Fortinet": {"Core": ["fw-01"]}},
    }

    class FakeApi:
        def get_dc_details(self, dc_id, tr):
            return dc

        def get_sla_by_dc(self, tr):
            return {}

        def get_dc_s3_pools(self, dc_id, tr):
            return {"pools": []}

        def get_classic_cluster_list(self, dc_id, tr):
            return []

        def get_hyperconv_cluster_list(self, dc_id, tr):
            return []

        def get_physical_inventory_dc(self, dc_name):
            return {"total": 0, "by_role": [], "by_role_manufacturer": []}

        def get_dc_san_switches(self, dc_id, tr):
            return []

        def get_dc_netbackup_pools(self, dc_id, tr):
            return {"pools": [], "rows": []}

        def get_dc_zerto_sites(self, dc_id, tr):
            return {"sites": [], "rows": []}

        def get_dc_veeam_repos(self, dc_id, tr):
            return {"repos": [], "rows": []}

        def get_dc_nutanix_snapshots(self, dc_id, tr):
            return {"rows": [], "totals": {}, "as_of": ""}

        def get_dc_nutanix_snapshot_table(self, dc_id, tr, page=1, page_size=50, search="", schedule_type=None):
            return {"items": [], "total": 0, "page": page, "page_size": page_size}

        def get_dc_nutanix_missing(self, dc_id, tr, page=1, page_size=50):
            return {"items": [], "total": 0, "page": page, "page_size": page_size}
        def get_dc_network_filters(self, dc_id, tr):
            call_log.append("filters")
            return net_filters

        def get_dc_network_port_summary(self, dc_id, tr, manufacturer=None, device_role=None, device_name=None):
            call_log.append("port_summary")
            return {"device_count": 1, "total_ports": 48, "active_ports": 40, "avg_icmp_loss_pct": 0.5}

        def get_dc_network_95th_percentile(self, dc_id, tr, top_n=20, manufacturer=None, device_role=None, device_name=None):
            call_log.append("p95")
            return {"overall_port_utilization_pct": 35.0, "top_interfaces": []}

        def get_dc_network_interface_table(self, dc_id, tr, page=1, page_size=50, search="", manufacturer=None, device_role=None, device_name=None):
            call_log.append("iface_table")
            return {"items": [{"interface_name": "eth0", "p95_total_bps": 1e9, "speed_bps": 10e9, "utilization_pct": 10.0}]}

        def get_dc_zabbix_storage_capacity(self, dc_id, tr, host=None):
            return {"storage_device_count": 0}

        def get_dc_zabbix_storage_trend(self, dc_id, tr, host=None):
            return {"series": []}

        def get_dc_zabbix_storage_devices(self, dc_id, tr):
            return []

        def get_dc_availability_sla_item(self, dc_code, dc_display_name, tr):
            return None

    monkeypatch.setattr(dc_view, "api", FakeApi())


def test_build_dc_view_eager_fetches_network_payloads(monkeypatch):
    call_log: list[str] = []
    _fake_service_with_network(monkeypatch, call_log=call_log)

    layout = dc_view.build_dc_view("DCNET", time_range={"preset": "7d"})
    assert layout is not None

    assert "filters" in call_log
    assert "port_summary" in call_log
    assert "p95" in call_log
    assert "iface_table" in call_log


def test_build_dc_view_skips_network_payload_when_no_devices(monkeypatch):
    call_log: list[str] = []

    class FakeApiMinimal:
        def get_dc_details(self, dc_id, tr):
            return {
                "meta": {"name": "DCX", "location": "X"},
                "classic": {"hosts": 1, "vms": 1},
                "hyperconv": {},
                "power": {},
                "energy": {},
            }

        def get_sla_by_dc(self, tr):
            return {}

        def get_dc_s3_pools(self, dc_id, tr):
            return {"pools": []}

        def get_classic_cluster_list(self, dc_id, tr):
            return []

        def get_hyperconv_cluster_list(self, dc_id, tr):
            return []

        def get_physical_inventory_dc(self, dc_name):
            return {"total": 0, "by_role": [], "by_role_manufacturer": []}

        def get_dc_san_switches(self, dc_id, tr):
            return []

        def get_dc_netbackup_pools(self, dc_id, tr):
            return {"pools": [], "rows": []}

        def get_dc_zerto_sites(self, dc_id, tr):
            return {"sites": [], "rows": []}

        def get_dc_veeam_repos(self, dc_id, tr):
            return {"repos": [], "rows": []}

        def get_dc_nutanix_snapshots(self, dc_id, tr):
            return {"rows": [], "totals": {}, "as_of": ""}

        def get_dc_nutanix_snapshot_table(self, dc_id, tr, page=1, page_size=50, search="", schedule_type=None):
            return {"items": [], "total": 0, "page": page, "page_size": page_size}

        def get_dc_nutanix_missing(self, dc_id, tr, page=1, page_size=50):
            return {"items": [], "total": 0, "page": page, "page_size": page_size}
        def get_dc_network_filters(self, dc_id, tr):
            call_log.append("filters")
            return {"manufacturers": [], "roles_by_manufacturer": {}, "devices_by_manufacturer_role": {}}

        def get_dc_network_port_summary(self, *args, **kwargs):
            call_log.append("port_summary")
            return {}

        def get_dc_network_95th_percentile(self, *args, **kwargs):
            call_log.append("p95")
            return {}

        def get_dc_network_interface_table(self, *args, **kwargs):
            call_log.append("iface_table")
            return {"items": []}

        def get_dc_zabbix_storage_capacity(self, dc_id, tr, host=None):
            return {"storage_device_count": 0}

        def get_dc_zabbix_storage_trend(self, dc_id, tr, host=None):
            return {"series": []}

        def get_dc_zabbix_storage_devices(self, dc_id, tr):
            return []

        def get_dc_availability_sla_item(self, dc_code, dc_display_name, tr):
            return None

    monkeypatch.setattr(dc_view, "api", FakeApiMinimal())

    dc_view.build_dc_view("DCX", time_range={"preset": "7d"})

    assert call_log == ["filters"]
