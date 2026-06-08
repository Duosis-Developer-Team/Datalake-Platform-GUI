#!/usr/bin/env python3
"""Smoke tests for NetBox visualization settings page."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from src.pages.settings.integrations import netbox_visualization as page


class TestNetboxVisualizationSettings(unittest.TestCase):
    @patch("src.pages.settings.integrations.netbox_visualization.api.get_netbox_viz_exclusions")
    @patch("src.pages.settings.integrations.netbox_visualization.api.get_netbox_device_roles")
    def test_build_layout_renders_tabs(self, mock_roles, mock_exclusions):
        mock_roles.return_value = [{"role": "HOST"}, {"role": "Patch Panel"}]
        mock_exclusions.return_value = [
            {
                "id": 1,
                "view_scope": "datacenter",
                "dimension": "device_role",
                "dimension_value": "Patch Panel",
                "notes": None,
                "updated_by": "settings-ui",
            }
        ]
        layout = page.build_layout()
        self.assertIsNotNone(layout)
        html_str = str(layout)
        self.assertIn("NetBox / Loki visualization filters", html_str)
        self.assertIn("Datacenter", html_str)
        self.assertIn("Customer", html_str)


if __name__ == "__main__":
    unittest.main()
