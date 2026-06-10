import pytest
from dash import html

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


def _extract_select_values(dmc_select):
    opts = getattr(dmc_select, "data", None) or []
    return {o.get("value") for o in opts if isinstance(o, dict)}


def test_network_dashboard_builds_and_maps_values():
    net_filters = {
        "manufacturers": ["M1", "M2"],
        "devices_by_manufacturer": {
            "M1": ["D1", "D2"],
            "M2": ["D3"],
        },
    }
    port_summary = {"device_count": 3, "total_ports": 100, "active_ports": 30, "avg_icmp_loss_pct": 2.5}
    percentile_data = {
        "overall_port_utilization_pct": 45.0,
        "top_interfaces": [
            {
                "interface_name": "eth0",
                "interface_alias": "uplink",
                "p95_total_bps": 20_000_000_000,
                "p95_rx_bps": 12_000_000_000,
                "p95_tx_bps": 8_000_000_000,
                "speed_bps": 25_000_000_000,
                "utilization_pct": 80.0,
            },
            {
                "interface_name": "eth1",
                "interface_alias": "",
                "p95_total_bps": 5_000_000_000,
                "p95_rx_bps": 2_000_000_000,
                "p95_tx_bps": 3_000_000_000,
                "speed_bps": 10_000_000_000,
                "utilization_pct": 50.0,
            },
        ],
    }
    interface_table = {
        "items": [
            {
                "host": "sw-01",
                "interface_name": "eth0",
                "interface_alias": "uplink",
                "p95_rx_bps": 12_000_000_000,
                "p95_tx_bps": 8_000_000_000,
                "p95_total_bps": 20_000_000_000,
                "speed_bps": 25_000_000_000,
                "utilization_pct": 80.0,
            }
        ]
    }

    node = dc_view._build_network_dashboard_subtab(
        net_filters, port_summary, percentile_data, interface_table,
        top_scope="switch", switch_role="backbone",
    )
    assert node is not None

    manu_select = _find_by_id(node, "net-manufacturer-selector")
    device_select = _find_by_id(node, "net-device-selector")
    assert _find_by_id(node, "net-role-selector") is None
    assert _extract_select_values(manu_select) == {"M1", "M2"}
    assert _extract_select_values(device_select) == {"D1", "D2", "D3"}

    donut_active = _find_by_id(node, "net-donut-active-ports")
    assert donut_active is not None
    assert donut_active.figure.data[0].value == pytest.approx(30.0)

    bar = _find_by_id(node, "net-top-interfaces-bar")
    assert bar is not None
    x_vals = list(bar.figure.data[0].x)
    assert x_vals == [20.0, 5.0]

    table = _find_by_id(node, "net-interface-table")
    assert table is not None
    assert len(table.data) == 1
    col_ids = {c["id"] for c in table.columns}
    assert "p95_rx_gbps" in col_ids
    assert "host" in col_ids


def test_network_zabbix_section_exposes_scope_tabs():
    node = dc_view._build_network_zabbix_section(
        net_filters={"manufacturers": ["M1"], "devices_by_manufacturer": {"M1": ["sw-01"]}},
        port_summary={"device_count": 1, "total_ports": 10, "active_ports": 5, "avg_icmp_loss_pct": 0.0},
        percentile_data={"overall_port_utilization_pct": 0.0, "top_interfaces": []},
        interface_table={"items": []},
        firewall_data={"devices": []},
        lb_data={"devices": []},
        sec_check=lambda _code: True,
    )
    tabs = _find_by_id(node, "net-scope-tabs")
    segment = _find_by_id(node, "net-switch-role-segment")
    assert tabs is not None
    assert tabs.value == "overview"
    assert segment is not None
    tab_values = {t.value for t in tabs.children[0].children if hasattr(t, "value")}
    assert tab_values == set(dc_view.NETWORK_TOP_SCOPES)


def test_resolve_network_interface_scope():
    assert dc_view.resolve_network_interface_scope("overview", None) is None
    assert dc_view.resolve_network_interface_scope("switch", "leaf") == "leaf"
    assert dc_view.resolve_network_interface_scope("switch", None) == "backbone"
    assert dc_view.resolve_network_interface_scope("router_uplink", None) == "router_uplink"


def test_network_dashboard_empty_top_interfaces_no_crash():
    net_filters = {
        "manufacturers": ["M1"],
        "devices_by_manufacturer": {"M1": ["D1"]},
    }
    port_summary = {"device_count": 1, "total_ports": 10, "active_ports": 5, "avg_icmp_loss_pct": 0.0}
    percentile_data = {
        "overall_port_utilization_pct": 0.0,
        "top_interfaces": [],
    }
    interface_table = {"items": []}

    node = dc_view._build_network_dashboard_subtab(net_filters, port_summary, percentile_data, interface_table)
    assert node is not None
    bar = _find_by_id(node, "net-top-interfaces-bar")
    assert bar is not None
    assert bar.figure.data == () or len(bar.figure.data[0].x or []) == 0
