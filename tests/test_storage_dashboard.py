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


def _find_all_graphs(node, out):
    if node is None:
        return
    if node.__class__.__name__ == "Graph" and getattr(node, "figure", None) is not None:
        out.append(node)
    children = getattr(node, "children", None)
    if isinstance(children, (list, tuple)):
        for c in children:
            _find_all_graphs(c, out)
    elif children is not None:
        _find_all_graphs(children, out)


def test_intel_storage_dashboard_maps_utilization_and_disk_placeholders():
    gb = 1024.0 ** 3
    device_list = [
        {"host": "zbx-host-1", "device_name": "Intel Array 1", "total_capacity_bytes": 100 * gb},
    ]
    zabbix_storage_capacity = {
        "storage_device_count": 1,
        "total_capacity_bytes": 100 * gb,
        "used_capacity_bytes": 50 * gb,
        "free_capacity_bytes": 50 * gb,
    }
    zabbix_storage_trend = {
        "series": [
            {"ts": "2020-01-01", "used_capacity_bytes": 50 * gb, "total_capacity_bytes": 100 * gb, "used_pct": 50.0},
            {"ts": "2020-01-02", "used_capacity_bytes": 60 * gb, "total_capacity_bytes": 100 * gb, "used_pct": 60.0},
        ]
    }

    node = dc_view._build_intel_storage_subtab(device_list, zabbix_storage_capacity, zabbix_storage_trend)
    assert node is not None

    # Donut "Used Capacity": used_pct = 50% => annotation contains 50
    donut_used = _find_by_id(node, "intel-donut-used")
    assert donut_used is not None
    ann = donut_used.figure.layout.annotations[0].text
    assert "50" in ann

    # Capacity utilization trend graph title match
    graphs = []
    _find_all_graphs(node, graphs)
    trend_graph = None
    for g in graphs:
        try:
            if g.figure.layout.title.text == "Capacity Utilization Trend":
                trend_graph = g
                break
        except Exception:
            pass
    assert trend_graph is not None
    y_vals = list(trend_graph.figure.data[0].y)
    assert y_vals == [50.0, 60.0]

    # Disk placeholders (disk health table removed; only containers exist initially)
    assert _find_by_id(node, "intel-disk-container") is not None
    assert _find_by_id(node, "intel-disk-trend-container") is not None
    assert _find_by_id(node, "intel-storage-disk-selector") is None

