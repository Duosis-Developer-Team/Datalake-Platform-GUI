"""
Unit tests for backup panels and DC detection helpers.
DB calls are mocked; no live database required.
"""

import unittest
from unittest.mock import MagicMock, patch

import psycopg2

with patch("psycopg2.pool.ThreadedConnectionPool"):
    from src.services.db_service import DatabaseService

from src.services import cache_service as cache
from src.components import backup_panel


def _make_service():
    with patch("psycopg2.pool.ThreadedConnectionPool"):
        svc = DatabaseService()
    svc._pool = MagicMock()
    svc._dc_list = ["DC13", "DC11"]
    return svc


class TestDcDetectionHelpers(unittest.TestCase):
    def setUp(self):
        cache.clear()

    def test_filter_rows_for_dc_by_name_and_host_uses_name_pattern(self):
        svc = _make_service()
        rows = [
            # ts, host, name, ...
            ("2024-01-01", "10.34.17.200", "dp_rpnbmedia05dc13", "stype", "cat", "vol", "state", 1, 2, 3),
            ("2024-01-01", "10.34.17.200", "other", "stype", "cat", "vol", "state", 4, 5, 6),
        ]
        filtered = svc._filter_rows_for_dc_by_name_and_host(rows, "DC13", name_index=2, host_index=1)
        self.assertEqual(len(filtered), 1)
        self.assertIn("dp_rpnbmedia05dc13", filtered[0][2])

    def test_filter_rows_for_dc_by_name_and_host_uses_ip_prefix_grouping(self):
        svc = _make_service()
        rows = [
            ("2024-01-01", "10.34.17.200", "dp_rpnbmedia05dc13", "stype", "cat", "vol", "state", 1, 2, 3),
            ("2024-01-01", "10.34.17.201", "pool_without_dc", "stype", "cat", "vol", "state", 4, 5, 6),
        ]
        filtered = svc._filter_rows_for_dc_by_name_and_host(rows, "DC13", name_index=2, host_index=1)
        names = [r[2] for r in filtered]
        self.assertIn("dp_rpnbmedia05dc13", names)
        self.assertIn("pool_without_dc", names)

    def test_filter_rows_for_dc_by_host_pattern_veeam(self):
        svc = _make_service()
        rows = [
            ("2024-01-01", "id1", "repo1", "veeam-dc13-host", "type", 1.0, 2.0, 3.0, True),
            ("2024-01-01", "id2", "repo2", "veeam-dc11-host", "type", 1.0, 2.0, 3.0, True),
        ]
        filtered = svc._filter_rows_for_dc_by_host_pattern(rows, "DC13", host_index=3)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0][2], "repo1")


class TestBackupPanels(unittest.TestCase):
    def test_netbackup_panel_aggregation(self):
        data = {
            "rows": [
                {
                    "name": "pool1",
                    "usablesizebytes": 100,
                    "availablespacebytes": 40,
                    "usedcapacitybytes": 60,
                },
                {
                    "name": "pool2",
                    "usablesizebytes": 200,
                    "availablespacebytes": 50,
                    "usedcapacitybytes": 150,
                },
            ]
        }
        agg = backup_panel._aggregate_netbackup(data, selected_pools=None)
        self.assertEqual(agg["total_usable"], 300)
        self.assertEqual(agg["total_used"], 210)
        self.assertIn("pools", agg)

    def test_zerto_panel_aggregation(self):
        data = {
            "rows": [
                {
                    "name": "site1",
                    "provisioned_storage_mb": 1000,
                    "used_storage_mb": 400,
                    "incoming_throughput_mb": 10.5,
                    "outgoing_bandwidth_mb": 5.0,
                },
                {
                    "name": "site2",
                    "provisioned_storage_mb": 2000,
                    "used_storage_mb": 1000,
                    "incoming_throughput_mb": 20.0,
                    "outgoing_bandwidth_mb": 8.0,
                },
            ]
        }
        agg = backup_panel._aggregate_zerto(data, selected_sites=None)
        self.assertEqual(agg["total_provisioned_mb"], 3000)
        self.assertEqual(agg["total_used_mb"], 1400)
        self.assertAlmostEqual(agg["incoming_mb"], 30.5, places=1)

    def test_veeam_panel_aggregation(self):
        data = {
            "rows": [
                {
                    "name": "repo1",
                    "capacity_gb": 100.0,
                    "free_gb": 40.0,
                    "used_space_gb": 60.0,
                },
                {
                    "name": "repo2",
                    "capacity_gb": 200.0,
                    "free_gb": 50.0,
                    "used_space_gb": 150.0,
                },
            ]
        }
        agg = backup_panel._aggregate_veeam(data, selected_repos=None)
        self.assertAlmostEqual(agg["total_capacity_gb"], 300.0, places=1)
        self.assertAlmostEqual(agg["total_used_gb"], 210.0, places=1)
        self.assertAlmostEqual(agg["total_free_gb"], 90.0, places=1)


def _collect_layout_ids(node) -> list[str]:
    ids: list[str] = []

    def walk(n) -> None:
        if n is None:
            return
        if hasattr(n, "id") and getattr(n, "id", None):
            ids.append(n.id)
        children = getattr(n, "children", None)
        if isinstance(children, (list, tuple)):
            for child in children:
                walk(child)
        elif children is not None:
            walk(children)

    walk(node)
    return ids


class TestBackupPanelLayoutOrder(unittest.TestCase):
    _NB_ROW = {
        "name": "pool1",
        "stype": "disk",
        "storagecategory": "cat",
        "diskvolumes_name": "vol1",
        "diskvolumes_state": "UP",
        "usablesizebytes": 100,
        "availablespacebytes": 40,
        "usedcapacitybytes": 60,
    }

    def test_netbackup_panel_jobs_before_pool_capacity(self):
        data = {"rows": [self._NB_ROW]}
        panel = backup_panel.build_netbackup_panel(
            data,
            None,
            category="image",
            policy_type_options=["VMWARE"],
        )
        ids = _collect_layout_ids(panel)
        jobs_idx = ids.index("backup-jobs-netbackup-image-chart")
        unique_idx = ids.index("backup-uj-dc-netbackup-image-kpis")
        capacity_idx = ids.index("backup-nb-capacity-image")
        selector_idx = ids.index("backup-nb-pool-selector-image")
        self.assertLess(jobs_idx, unique_idx)
        self.assertLess(unique_idx, selector_idx)
        self.assertLess(selector_idx, capacity_idx)

    def test_zerto_panel_jobs_before_site_capacity(self):
        data = {
            "rows": [
                {
                    "name": "site1",
                    "provisioned_storage_mb": 1000,
                    "used_storage_mb": 400,
                    "incoming_throughput_mb": 10.5,
                    "outgoing_bandwidth_mb": 5.0,
                    "is_connected": True,
                    "site_type": "local",
                }
            ]
        }
        panel = backup_panel.build_zerto_panel(data, None)
        ids = _collect_layout_ids(panel)
        self.assertLess(ids.index("backup-jobs-zerto-chart"), ids.index("backup-zerto-capacity"))
        self.assertLess(ids.index("backup-uj-dc-zerto-kpis"), ids.index("backup-zerto-capacity"))

    def test_veeam_panel_jobs_before_repository_capacity(self):
        data = {
            "rows": [
                {
                    "name": "repo1",
                    "capacity_gb": 100.0,
                    "free_gb": 40.0,
                    "used_space_gb": 60.0,
                    "host_name": "host1",
                    "type": "repo",
                    "is_online": True,
                }
            ]
        }
        panel = backup_panel.build_veeam_panel(data, None)
        ids = _collect_layout_ids(panel)
        self.assertLess(ids.index("backup-jobs-veeam-chart"), ids.index("backup-veeam-capacity"))
        self.assertLess(ids.index("backup-uj-dc-veeam-kpis"), ids.index("backup-veeam-capacity"))


if __name__ == "__main__":
    unittest.main()

