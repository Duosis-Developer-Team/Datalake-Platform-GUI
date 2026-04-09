"""Unit tests for DC Summary arch_usage display helpers in home page."""

import unittest

from src.pages.home import effective_max_pct


class TestEffectiveMaxPct(unittest.TestCase):
    def test_uses_max_when_positive(self):
        self.assertEqual(effective_max_pct(80.0, 50.0), 80.0)
        self.assertEqual(effective_max_pct(12.34, 0.0), 12.3)

    def test_falls_back_when_max_zero_or_missing(self):
        self.assertEqual(effective_max_pct(0, 45.2), 45.2)
        self.assertEqual(effective_max_pct(None, 30.0), 30.0)

    def test_falls_back_when_max_invalid(self):
        self.assertEqual(effective_max_pct("bad", 10.0), 10.0)

    def test_zero_when_both_invalid(self):
        self.assertEqual(effective_max_pct(0, None), 0.0)
        self.assertEqual(effective_max_pct(0, "x"), 0.0)


if __name__ == "__main__":
    unittest.main()
