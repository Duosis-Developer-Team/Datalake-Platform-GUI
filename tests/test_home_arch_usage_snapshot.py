"""DC Summary arch_usage cells show the live snapshot value with no "max" label.

The Overview table used to label every badge "max" (a leftover from a period-peak
design that never actually shipped — the max field was stripped by the API schema,
so the badge showed the average mislabeled as max). The metric is now a live
snapshot that reconciles with the Datacenters cards, so the misleading "max" label
must be gone and the snapshot percentage must be rendered.
"""

import unittest

from src.pages.home import _arch_usage_cell


def _text_leaves(component):
    """Recursively collect all string leaves from a Dash component tree."""
    leaves = []

    def walk(node):
        if isinstance(node, str):
            leaves.append(node)
        elif isinstance(node, (list, tuple)):
            for child in node:
                walk(child)
        else:
            children = getattr(node, "children", None)
            if children is not None:
                walk(children)

    walk(component)
    return leaves


class TestArchUsageCellSnapshot(unittest.TestCase):
    def test_renders_snapshot_value(self):
        cell = _arch_usage_cell({"cpu_pct": 30.0, "ram_pct": 40.0})
        texts = _text_leaves(cell)
        self.assertIn("30.0%", texts)
        self.assertIn("40.0%", texts)

    def test_does_not_render_max_label(self):
        cell = _arch_usage_cell({"cpu_pct": 30.0, "ram_pct": 40.0})
        texts = _text_leaves(cell)
        self.assertNotIn("max", texts)

    def test_handles_missing_values_as_dash(self):
        cell = _arch_usage_cell({})
        texts = _text_leaves(cell)
        self.assertNotIn("max", texts)


if __name__ == "__main__":
    unittest.main()
