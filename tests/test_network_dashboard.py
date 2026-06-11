import pytest

from src.pages import dc_view


def _find_by_id(node, target_id):
    if node is None:
        return None
    if getattr(node, "id", None) == target_id:
        return node
    children = getattr(node, "children", None)
    if isinstance(children, (list, tuple)):
        for c in children:
            found = _find_by_id(c, target_id)
            if found is not None:
                return found
    elif children is not None:
        return _find_by_id(children, target_id)
    return None


def test_backbone_billing_page_table_first():
    node = dc_view._build_network_interface_page(
        net_filters={"manufacturers": ["M1"], "devices_by_manufacturer": {"M1": ["sw-01"]}},
        port_summary={"device_count": 1, "total_ports": 10, "active_ports": 5, "avg_icmp_loss_pct": 0.0},
        percentile_data={"overall_port_utilization_pct": 40.0, "top_interfaces": []},
        interface_table={"items": [{"host": "sw-01", "interface_name": "eth0", "p95_total_bps": 1e9, "speed_bps": 10e9, "utilization_pct": 10}], "total": 1},
        top_scope="switch",
        switch_role="backbone",
    )
    table = _find_by_id(node, "net-interface-table")
    assert table is not None
    assert getattr(table, "page_count", None) == 1
    assert getattr(table, "page_action", None) == "custom"
    assert getattr(table, "sort_action", None) == "none"
    assert _find_by_id(node, "net-interface-export-btn") is not None
    assert _find_by_id(node, "net-donut-grid-wrap") is not None
    assert _find_by_id(node, "net-export-btn-wrap") is not None


def test_firewall_page_has_no_interface_widgets():
    node = dc_view._build_network_firewall_page({"devices": [{"host": "fw-1", "active_sessions": 10}]})
    assert _find_by_id(node, "net-fw-kpi-container") is not None
    assert _find_by_id(node, "net-firewall-table") is not None
    assert _find_by_id(node, "net-manufacturer-selector") is None
    assert _find_by_id(node, "net-interface-table") is None
    assert _find_by_id(node, "net-top-interfaces-bar") is None


def test_network_zabbix_section_has_role_pages():
    node = dc_view._build_network_zabbix_section(
        net_filters={"manufacturers": ["M1"], "devices_by_manufacturer": {"M1": ["sw-01"]}},
        port_summary={"device_count": 1, "total_ports": 10, "active_ports": 5, "avg_icmp_loss_pct": 0.0},
        percentile_data={"overall_port_utilization_pct": 0.0, "top_interfaces": []},
        interface_table={"items": [], "total": 0},
        firewall_data={"devices": []},
        lb_data={"devices": []},
        sec_check=lambda _code: True,
    )
    assert _find_by_id(node, "net-page-interface") is not None
    assert _find_by_id(node, "net-page-firewall") is not None
    assert _find_by_id(node, "net-page-load-balancer") is not None
    tabs = _find_by_id(node, "net-scope-tabs")
    assert tabs is not None
    assert tabs.value == "overview"


def test_resolve_network_interface_scope():
    assert dc_view.resolve_network_interface_scope("overview", None) is None
    assert dc_view.resolve_network_interface_scope("switch", "leaf") == "leaf"
    assert dc_view.resolve_network_interface_scope("router_uplink", None) == "router_uplink"


def test_interface_table_page_count_for_large_total():
    node = dc_view._build_network_interface_page(
        net_filters={"manufacturers": ["M1"], "devices_by_manufacturer": {"M1": ["sw-01"]}},
        port_summary={"device_count": 1, "total_ports": 723, "active_ports": 723, "avg_icmp_loss_pct": 0.0},
        percentile_data={"overall_port_utilization_pct": 16.0, "top_interfaces": []},
        interface_table={"items": [], "total": 723},
        top_scope="switch",
        switch_role="backbone",
    )
    table = _find_by_id(node, "net-interface-table")
    assert table is not None
    assert getattr(table, "page_count", None) == 15


def test_network_page_flags():
    flags = dc_view._network_page_flags("switch", "backbone")
    assert flags["billing"] is True
    assert flags["show_export"] is True
    assert flags["show_donut_grid"] is False
    fw_flags = dc_view._network_page_flags("firewall", None)
    assert fw_flags["is_interface_page"] is False


def test_backbone_interface_table_columns_include_billing():
    cols = dc_view._network_interface_table_columns("backbone")
    col_ids = [c["id"] for c in cols]
    assert "p95_billable_mbit" in col_ids
    assert "unit_price_tl_per_mbit" in col_ids
    assert "estimated_cost_tl" in col_ids


def test_backbone_interface_table_rows_map_billing_fields():
    rows = dc_view._interface_table_rows(
        [
            {
                "host": "sw-01",
                "interface_name": "eth0",
                "p95_rx_bps": 1e9,
                "p95_tx_bps": 2e9,
                "p95_total_bps": 3e9,
                "speed_bps": 10e9,
                "utilization_pct": 30.0,
                "p95_billable_mbit": 3000.0,
                "unit_price_tl_per_mbit": 331.12,
                "estimated_cost_tl": 993360.0,
            }
        ],
        interface_scope="backbone",
    )
    assert rows[0]["p95_billable_mbit"] == "3.00K"
    assert "993" in rows[0]["estimated_cost_tl"]


def test_backbone_table_subtitle_includes_crm_price():
    title, subtitle = dc_view._network_table_section_titles(
        "backbone",
        True,
        {
            "has_price": True,
            "product_name": "Veri Merkezi Erişim ve L3 DDoS Hizmeti",
            "unit_price_tl": 331.12,
        },
    )
    assert title == "Billable Interface Table"
    assert "331.12" in subtitle
    assert "Veri Merkezi" in subtitle
