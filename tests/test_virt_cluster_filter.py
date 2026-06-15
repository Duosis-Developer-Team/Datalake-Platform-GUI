"""Unit tests for virt cluster filter bar component."""
from __future__ import annotations

import unittest

from dash import dcc

from src.components.virt_cluster_filter import (
    VIRT_CLUSTER_DEBOUNCE_MS,
    build_virt_cluster_filter_bar,
    checklist_value_from_draft,
    cluster_selection_summary,
    draft_from_checklist,
    short_cluster_label,
    virt_cluster_filter_ids,
)


class TestVirtClusterFilterHelpers(unittest.TestCase):
    def test_short_cluster_label_strips_dc_prefix(self):
        self.assertEqual(
            short_cluster_label("DC13-FC1-HYBRID", "DC13-"),
            "FC1-HYBRID",
        )
        self.assertEqual(short_cluster_label("KM-01", ""), "KM-01")

    def test_cluster_selection_summary_all(self):
        self.assertEqual(cluster_selection_summary([], 24), "All 24 clusters")
        self.assertEqual(cluster_selection_summary(["a"] * 24, 24), "All 24 clusters")

    def test_cluster_selection_summary_partial(self):
        self.assertEqual(cluster_selection_summary(["a", "b"], 24), "2 of 24 selected")

    def test_checklist_value_from_draft_empty_means_all(self):
        all_c = ["A", "B", "C"]
        self.assertEqual(checklist_value_from_draft([], all_c), all_c)
        self.assertEqual(checklist_value_from_draft(["A"], all_c), ["A"])

    def test_draft_from_checklist_full_means_empty(self):
        all_c = ["A", "B", "C"]
        self.assertEqual(draft_from_checklist(all_c, all_c), [])
        self.assertEqual(draft_from_checklist(["A", "B"], all_c), ["A", "B"])


class TestVirtClusterFilterBar(unittest.TestCase):
    def test_build_returns_stores_and_toolbar(self):
        children = build_virt_cluster_filter_bar(
            "classic",
            ["DC13-KM-01", "DC13-KM-02"],
            "Select Classic clusters",
        )
        self.assertEqual(len(children), 5)
        stores = [c for c in children if isinstance(c, dcc.Store)]
        self.assertEqual(len(stores), 3)
        ids = virt_cluster_filter_ids("classic")
        self.assertEqual(ids["applied"], "virt-classic-cluster-applied")
        self.assertEqual(ids["draft"], "virt-classic-cluster-draft")
        self.assertEqual(VIRT_CLUSTER_DEBOUNCE_MS, 800)

    def test_hyperconv_prefix_ids(self):
        ids = virt_cluster_filter_ids("hyperconv")
        self.assertEqual(ids["apply"], "virt-hyperconv-cluster-apply")
        self.assertEqual(ids["checklist"], "virt-hyperconv-cluster-checklist")
        self.assertEqual(ids["popover"], "virt-hyperconv-cluster-popover")

    def test_default_applied_and_draft_are_empty(self):
        children = build_virt_cluster_filter_bar("classic", ["A", "B"], "Pick")
        stores = {c.id: c.data for c in children if isinstance(c, dcc.Store)}
        self.assertEqual(stores["virt-classic-cluster-applied"], [])
        self.assertEqual(stores["virt-classic-cluster-draft"], [])


if __name__ == "__main__":
    unittest.main()
