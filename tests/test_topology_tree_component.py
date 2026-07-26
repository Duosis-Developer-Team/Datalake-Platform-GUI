"""build_topology_tree renders the DC->Cluster->Host->VM drill-down."""
from src.components.topology_tree import build_topology_tree

_TREE = {
    "dcs": [{
        "name": "DC13",
        "counts": {"clusters": 1, "hosts": 1, "vms": 2, "running": 1},
        "os": {"rhel": 0, "suse": 0, "windows": 1, "free": 1, "unknown": 0},
        "clusters": [{
            "name": "CL1", "counts": {"hosts": 1, "vms": 2, "running": 1},
            "os": {"rhel": 0, "suse": 0, "windows": 1, "free": 1, "unknown": 0},
            "hosts": [{
                "name": "esx1", "counts": {"vms": 2, "running": 1},
                "os": {"rhel": 0, "suse": 0, "windows": 1, "free": 1, "unknown": 0},
                "vms": [
                    {"name": "web-01", "os_family": "windows", "power_state": "poweredOn"},
                    {"name": "web-02", "os_family": "free", "power_state": "poweredOff"},
                ],
            }],
        }],
    }],
    "totals": {"dcs": 1, "clusters": 1, "hosts": 1, "vms": 2, "running": 1},
}


def test_tree_renders_all_levels():
    text = str(build_topology_tree(_TREE, with_os=True))
    for token in ("DC13", "CL1", "esx1", "web-01", "web-02"):
        assert token in text


def test_tree_empty_is_graceful():
    comp = build_topology_tree({"dcs": [], "totals": {}})
    assert comp is not None
    assert "yok" in str(comp).lower()
