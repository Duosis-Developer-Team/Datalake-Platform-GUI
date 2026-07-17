"""Backup capacity callbacks must not fire on global time-range before panels mount."""

from __future__ import annotations

import inspect
from unittest.mock import patch

import dash


_CAPACITY_OUTPUT_FRAGMENTS = (
    "backup-nb-capacity-image.children",
    "backup-nb-capacity-application.children",
    "backup-zerto-capacity.children",
    "backup-veeam-capacity.children",
)

_CAPACITY_FNS = (
    "update_backup_netbackup_capacity_image",
    "update_backup_netbackup_capacity_application",
    "update_backup_zerto_capacity",
    "update_backup_veeam_capacity",
)


def test_backup_capacity_callbacks_gated_on_panels_ready():
    import app as app_module

    found = 0
    for key, meta in app_module.app.callback_map.items():
        if not any(frag in key for frag in _CAPACITY_OUTPUT_FRAGMENTS):
            continue
        # Capacity children + selector data are co-outputs of the same callback.
        assert "backup-nb-pool-selector" in key or "backup-zerto-site-selector" in key or "backup-veeam-repo-selector" in key or ".." in key
        input_ids = {i["id"] for i in meta["inputs"]}
        assert "backup-panels-ready" in input_ids, (key, input_ids)
        assert "backup-time-range" in input_ids, (key, input_ids)
        assert "app-time-range" not in input_ids, (key, input_ids)
        found += 1
    assert found == 4, f"expected 4 capacity callbacks, found {found}"


def test_backup_capacity_callbacks_prevent_initial_call():
    import app as app_module

    for name in _CAPACITY_FNS:
        src = inspect.getsource(getattr(app_module, name))
        assert "prevent_initial_call=True" in src, name


def test_backup_capacity_callbacks_skip_when_panels_not_ready():
    import app as app_module

    with patch.object(app_module, "api") as mock_api:
        out = app_module.update_backup_zerto_capacity(
            ["site-a"],
            {"preset": "7d"},
            0,
            "/datacenter/DC13",
        )
        assert out == (dash.no_update, dash.no_update)
        mock_api.get_dc_zerto_sites.assert_not_called()

        out = app_module.update_backup_veeam_capacity(
            ["repo-a"],
            {"preset": "7d"},
            None,
            "/datacenter/DC13",
        )
        assert out == (dash.no_update, dash.no_update)
        mock_api.get_dc_veeam_repos.assert_not_called()


def test_backup_capacity_callback_returns_selector_options():
    import app as app_module

    with patch.object(app_module, "api") as mock_api:
        mock_api.get_dc_netbackup_pools.return_value = {
            "pools": ["pool-a", "pool-b"],
            "rows": [
                {
                    "name": "pool-a",
                    "stype": "disk",
                    "storagecategory": "cat",
                    "diskvolumes_name": "vol1",
                    "diskvolumes_state": "UP",
                    "usablesizebytes": 100,
                    "availablespacebytes": 40,
                    "usedcapacitybytes": 60,
                }
            ],
        }
        children, options = app_module.update_backup_netbackup_capacity_image(
            None,
            {"preset": "7d"},
            1,
            "/datacenter/DC13",
        )
        assert options == [
            {"label": "pool-a", "value": "pool-a"},
            {"label": "pool-b", "value": "pool-b"},
        ]
        assert children is not dash.no_update
        mock_api.get_dc_netbackup_pools.assert_called_once()
