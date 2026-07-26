"""Deduped DC->Cluster->Host->VM topology tree builder + dedup SQL."""
from shared.topology import vm_topology as vt


def test_is_system_vm():
    assert vt.is_system_vm("vCLS-abc")
    assert not vt.is_system_vm("web-01")


def test_build_tree_nests_and_counts():
    rows = [
        ("DC13", "CL1", "esx1", "web-01", "Microsoft Windows Server 2019 (64-bit)", "poweredOn"),
        ("DC13", "CL1", "esx1", "web-02", "Ubuntu Linux (64-bit)", "poweredOff"),
        ("DC13", "CL1", "esx2", "db-01", "Red Hat Enterprise Linux 8 (64-bit)", "poweredOn"),
        ("DC14", "CL9", "esx9", "vCLS-x", "", "poweredOn"),   # system -> excluded
        ("DC14", "CL9", "esx9", "app-1", "SUSE Linux Enterprise 15", "poweredOn"),
    ]
    t = vt.build_tree(rows, with_os=True)
    assert t["totals"] == {"dcs": 2, "clusters": 2, "hosts": 3, "vms": 4, "running": 3}
    dc13 = next(d for d in t["dcs"] if d["name"] == "DC13")
    assert dc13["counts"] == {"clusters": 1, "hosts": 2, "vms": 3, "running": 2}
    assert dc13["os"]["windows"] == 1 and dc13["os"]["rhel"] == 1 and dc13["os"]["free"] == 1
    esx1 = dc13["clusters"][0]["hosts"][0]
    assert esx1["counts"] == {"vms": 2, "running": 1}
    assert "vms" not in esx1                     # leaf VM lists omitted by default (DOM safety)


def test_build_tree_with_vms_includes_leaves():
    rows = [
        ("DC13", "CL1", "esx1", "web-01", "Ubuntu Linux", "poweredOn"),
        ("DC13", "CL1", "esx1", "web-02", "Ubuntu Linux", "poweredOff"),
    ]
    t = vt.build_tree(rows, with_vms=True)
    esx1 = t["dcs"][0]["clusters"][0]["hosts"][0]
    assert {v["name"] for v in esx1["vms"]} == {"web-01", "web-02"}


def test_build_tree_unmapped_coalescing():
    rows = [("", "", "", "orphan-1", "", "poweredOn")]
    t = vt.build_tree(rows)
    dc = t["dcs"][0]
    assert dc["name"] == "(DC atanmamış)"
    assert dc["clusters"][0]["name"] == "(cluster yok)"
    assert dc["clusters"][0]["hosts"][0]["name"] == "(host yok)"


def test_topology_sql_uses_netbox_and_dedup():
    sql = vt.VM_TOPOLOGY_SQL.lower()
    assert "discovery_netbox_virtualization_vm" in sql
    assert "distinct on" in sql
    assert "custom_fields_config_instance_uuid" in sql
    assert "custom_fields_guest_os" in sql
    assert "raw_vmware_vm_config" not in sql
