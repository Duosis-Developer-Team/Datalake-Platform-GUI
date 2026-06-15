"""Unit tests for virt cluster filter bar component."""
from __future__ import annotations

import unittest

from src.components.virt_cluster_filter import (
    VIRT_CLUSTER_DEBOUNCE_MS,
    build_virt_cluster_filter_bar,
    virt_cluster_filter_ids,
)


class TestVirtClusterFilterBar(unittest.TestCase):
    def test_build_returns_stores_and_controls(self):
        children = build_virt_cluster_filter_bar(
            "classic",
            ["DC13-KM-01", "DC13-KM-02"],
            "Select Classic clusters",
        )
        self.assertEqual(len(children), 4)
        ids = virt_cluster_filter_ids("classic")
        self.assertEqual(ids["applied"], "virt-classic-cluster-applied")
        self.assertEqual(ids["selector"], "virt-classic-cluster-selector")
        self.assertEqual(VIRT_CLUSTER_DEBOUNCE_MS, 800)

    def test_hyperconv_prefix(self):
        ids = virt_cluster_filter_ids("hyperconv")
        self.assertEqual(ids["apply"], "virt-hyperconv-cluster-apply")


if __name__ == "__main__":
    unittest.main()
