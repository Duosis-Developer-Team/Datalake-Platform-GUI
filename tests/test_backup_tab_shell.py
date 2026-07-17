"""Backup tab shell/defer — mount without sync API fan-out; capacity empty until callback."""

from __future__ import annotations

from unittest.mock import patch


def _walk(node):
    if node is None:
        return
    if isinstance(node, (list, tuple)):
        for item in node:
            yield from _walk(item)
        return
    yield node
    children = getattr(node, "children", None)
    if children is not None:
        yield from _walk(children)


def _collect_ids(component):
    return {getattr(n, "id", None) for n in _walk(component) if getattr(n, "id", None)}


def _capacity_children(component, target_id: str):
    for node in _walk(component):
        if getattr(node, "id", None) == target_id:
            return getattr(node, "children", "MISSING")
    return "MISSING"


def test_netbackup_shell_has_empty_capacity_and_job_ids():
    from src.components import backup_panel

    panel = backup_panel.build_netbackup_panel(
        {"rows": []},
        None,
        category="image",
        policy_type_options=["VMWARE"],
        content_mode="shell",
    )
    ids = _collect_ids(panel)
    assert "backup-nb-capacity-image" in ids
    assert "backup-nb-capacity-image-loading" in ids
    assert "backup-jobs-netbackup-image-chart" in ids
    assert "backup-uj-dc-netbackup-image-kpis" in ids
    assert "backup-nb-pool-selector-image" in ids
    assert _capacity_children(panel, "backup-nb-capacity-image") is None


def test_netbackup_full_also_defers_capacity_children():
    """Inline capacity build removed — even full mode leaves capacity for the callback."""
    from src.components import backup_panel

    data = {
        "rows": [
            {
                "name": "pool1",
                "stype": "disk",
                "storagecategory": "cat",
                "diskvolumes_name": "vol1",
                "diskvolumes_state": "UP",
                "usablesizebytes": 100,
                "availablespacebytes": 40,
                "usedcapacitybytes": 60,
            }
        ]
    }
    panel = backup_panel.build_netbackup_panel(
        data, None, category="image", content_mode="full"
    )
    assert _capacity_children(panel, "backup-nb-capacity-image") is None


def test_image_shell_mounts_nutanix_target():
    from src.components.backup_panel import build_image_backup_section

    section = build_image_backup_section(content_mode="shell")
    ids = _collect_ids(section)
    assert "backup-nutanix-panel" in ids
    assert "backup-netbackup-panel-image" in ids
    assert "backup-image-tabs" in ids


def test_lazy_backup_tab_panel_skips_sync_backup_apis():
    from src.pages.dc_view import build_dc_lazy_tab_panel

    calls: list[str] = []

    def _track(name):
        def _fn(*_a, **_k):
            calls.append(name)
            if "pools" in name or name.endswith("_pools"):
                return {"pools": [], "rows": []}
            if "sites" in name:
                return {"sites": [], "rows": []}
            if "repos" in name:
                return {"repos": [], "rows": []}
            if "license" in name:
                return {"has_license": False, "licenses": [], "sites": [], "summary": {}}
            if "nutanix" in name:
                return {"rows": [], "totals": {}, "items": [], "total": 0}
            return {}

        return _fn

    def _details(*_a, **_k):
        return {
            "meta": {"name": "DC13", "location": "Istanbul"},
            "classic": {},
            "hyperconv": {},
            "power": {},
            "energy": {},
            "intel": {"vms": 0},
        }

    api_patch = {
        "get_dc_details": _details,
        "get_sla_by_dc": lambda *_a, **_k: {},
        "get_dc_netbackup_pools": _track("get_dc_netbackup_pools"),
        "get_dc_zerto_sites": _track("get_dc_zerto_sites"),
        "get_dc_veeam_repos": _track("get_dc_veeam_repos"),
        "get_dc_zerto_license": _track("get_dc_zerto_license"),
        "get_dc_nutanix_snapshots": _track("get_dc_nutanix_snapshots"),
        "get_dc_nutanix_snapshot_table": _track("get_dc_nutanix_snapshot_table"),
        "get_dc_nutanix_missing": _track("get_dc_nutanix_missing"),
    }

    with (
        patch.multiple("src.pages.dc_view.api", **api_patch),
        patch(
            "src.pages.dc_view.resolve_dc_display_from_summary",
            return_value=("DC13", "Istanbul"),
        ),
    ):
        panel = build_dc_lazy_tab_panel("DC13", "backup", {"preset": "7d"}, None)

    assert "get_dc_netbackup_pools" not in calls
    assert "get_dc_zerto_sites" not in calls
    assert "get_dc_veeam_repos" not in calls
    assert "get_dc_nutanix_snapshots" not in calls
    assert "get_dc_nutanix_snapshot_table" not in calls
    assert "get_dc_nutanix_missing" not in calls

    ids = _collect_ids(panel)
    assert "backup-category-tabs" in ids
    assert "backup-nb-capacity-image" in ids
    assert "backup-nutanix-panel" in ids
    assert "backup-zerto-capacity" in ids
    assert "backup-veeam-capacity" in ids


def test_populate_backup_nutanix_panel_gated():
    import dash
    import app as app_module

    with patch.object(app_module, "api") as mock_api:
        assert (
            app_module.populate_backup_nutanix_panel(0, {"preset": "7d"}, "/datacenter/DC13")
            is dash.no_update
        )
        mock_api.get_dc_nutanix_snapshots.assert_not_called()


def test_populate_backup_nutanix_panel_builds_on_ready():
    import dash
    import app as app_module

    with patch.object(app_module, "api") as mock_api:
        mock_api.get_dc_nutanix_snapshots.return_value = {
            "rows": [{"vm_name": "vm1", "cluster": "c1"}],
            "totals": {},
        }
        mock_api.get_dc_nutanix_snapshot_table.return_value = {"items": [], "total": 0}
        mock_api.get_dc_nutanix_missing.return_value = {"items": [], "total": 0}
        out = app_module.populate_backup_nutanix_panel(1, {"preset": "7d"}, "/datacenter/DC13")
        assert out is not dash.no_update
        mock_api.get_dc_nutanix_snapshots.assert_called_once()
        mock_api.get_dc_nutanix_snapshot_table.assert_called_once()
