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
    # dmc.Select uses prop `data` as list[{label, value}]
    opts = getattr(dmc_select, "data", None) or []
    return {o.get("value") for o in opts if isinstance(o, dict)}


def test_network_dashboard_builds_and_maps_values():
    net_filters = {
        "manufacturers": ["M1", "M2"],
        "roles_by_manufacturer": {"M1": ["R1"], "M2": ["R2"]},
        "devices_by_manufacturer_role": {"M1": {"R1": ["D1", "D2"]}, "M2": {"R2": ["D3"]}},
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
                "interface_name": "eth0",
                "interface_alias": "uplink",
                "p95_total_bps": 20_000_000_000,
                "speed_bps": 25_000_000_000,
                "utilization_pct": 80.0,
            }
        ]
    }

    node = dc_view._build_network_dashboard_subtab(net_filters, port_summary, percentile_data, interface_table)
    assert node is not None

    # Hierarchical filter defaults: union across manufacturers
    manu_select = _find_by_id(node, "net-manufacturer-selector")
    role_select = _find_by_id(node, "net-role-selector")
    device_select = _find_by_id(node, "net-device-selector")
    assert _extract_select_values(manu_select) == {"M1", "M2"}
    assert _extract_select_values(role_select) == {"R1", "R2"}
    assert _extract_select_values(device_select) == {"D1", "D2", "D3"}

    # KPI donut active ports: port availability = 30/100 => 30%
    donut_active = _find_by_id(node, "net-donut-active-ports")
    assert donut_active is not None
    ann = donut_active.figure.layout.annotations[0].text
    assert "30" in ann

    # Top bar chart: x values in Gbps (20 and 5)
    bar = _find_by_id(node, "net-top-interfaces-bar")
    assert bar is not None
    x_vals = list(bar.figure.data[0].x)
    assert x_vals == [20.0, 5.0]

    # Data table: initial page contains one row
    table = _find_by_id(node, "net-interface-table")
    assert table is not None
    assert len(table.data) == 1

