#!/usr/bin/env python3
"""Unit tests for NetBox visualization UI helpers."""
from __future__ import annotations

import unittest

from src.utils.netbox_viz_ui import (
    compute_exclusion_summary,
    filter_exclusions_by_scope,
    role_options,
    scope_table_count_label,
)


class TestNetboxVizUi(unittest.TestCase):
    def test_role_options_filters_empty(self):
        opts = role_options([{"role": "HOST"}, {"role": ""}, {}])
        self.assertEqual(opts, [{"value": "HOST", "label": "HOST"}])

    def test_compute_exclusion_summary(self):
        exclusions = [
            {"view_scope": "datacenter", "dimension_value": "Patch Panel"},
            {"view_scope": "customer", "dimension_value": "HOST"},
            {"view_scope": "customer", "dimension_value": "CAMERA"},
        ]
        roles = [{"role": "HOST"}, {"role": "Patch Panel"}, {"role": "CAMERA"}]
        summary = compute_exclusion_summary(exclusions, roles)
        self.assertEqual(summary["datacenter"], 1)
        self.assertEqual(summary["customer"], 2)
        self.assertEqual(summary["catalog"], 3)

    def test_filter_exclusions_by_scope_and_search(self):
        exclusions = [
            {"view_scope": "datacenter", "dimension_value": "Patch Panel", "notes": "noise"},
            {"view_scope": "datacenter", "dimension_value": "HOST", "notes": ""},
            {"view_scope": "customer", "dimension_value": "HOST", "notes": ""},
        ]
        scoped = filter_exclusions_by_scope(exclusions, "datacenter")
        self.assertEqual(len(scoped), 2)
        filtered = filter_exclusions_by_scope(exclusions, "datacenter", "patch")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["dimension_value"], "Patch Panel")

    def test_scope_table_count_label(self):
        rows = [{"id": 1}]
        self.assertEqual(scope_table_count_label(rows, None), "1 exclusion(s)")
        self.assertEqual(scope_table_count_label([], "x"), "No matches")


if __name__ == "__main__":
    unittest.main()
