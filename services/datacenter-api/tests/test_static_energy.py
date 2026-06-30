"""Unit tests for temporary static aggregate energy display overrides."""

from __future__ import annotations

import unittest

from shared.display.static_energy import (
    STATIC_TOTAL_ENERGY_KW,
    apply_static_aggregate_energy,
    resolve_static_total_energy_kw,
    scale_energy_breakdown,
)


class TestResolveStaticTotalEnergyKw(unittest.TestCase):
    def test_default_constant_when_env_none(self):
        self.assertEqual(resolve_static_total_energy_kw(None), STATIC_TOTAL_ENERGY_KW)

    def test_disabled_when_zero(self):
        self.assertIsNone(resolve_static_total_energy_kw(0))
        self.assertIsNone(resolve_static_total_energy_kw("0"))

    def test_custom_positive_value(self):
        self.assertEqual(resolve_static_total_energy_kw(500), 500.0)
        self.assertEqual(resolve_static_total_energy_kw("500"), 500.0)

    def test_invalid_env_falls_back_to_default(self):
        self.assertEqual(resolve_static_total_energy_kw("not-a-number"), STATIC_TOTAL_ENERGY_KW)


class TestScaleEnergyBreakdown(unittest.TestCase):
    def test_preserves_ratio(self):
        ibm, vc = scale_energy_breakdown(8.0, 4.0, 780.0)
        self.assertAlmostEqual(ibm + vc, 780.0, places=2)
        self.assertAlmostEqual(ibm / vc, 2.0, places=2)

    def test_zero_live_total_splits_fifty_fifty(self):
        ibm, vc = scale_energy_breakdown(0.0, 0.0, 780.0)
        self.assertEqual(ibm, 390.0)
        self.assertEqual(vc, 390.0)


class TestApplyStaticAggregateEnergy(unittest.TestCase):
    def test_overrides_overview_and_breakdown(self):
        overview = {"total_energy_kw": 12.5}
        breakdown = {"ibm_kw": 8.0, "vcenter_kw": 4.0}
        apply_static_aggregate_energy(overview, breakdown, target_kw=780.0)
        self.assertEqual(overview["total_energy_kw"], 780.0)
        self.assertAlmostEqual(breakdown["ibm_kw"] + breakdown["vcenter_kw"], 780.0, places=2)

    def test_no_op_when_target_none(self):
        overview = {"total_energy_kw": 12.5}
        breakdown = {"ibm_kw": 8.0, "vcenter_kw": 4.0}
        apply_static_aggregate_energy(overview, breakdown, target_kw=None)
        self.assertEqual(overview["total_energy_kw"], 12.5)
        self.assertEqual(breakdown["ibm_kw"], 8.0)
        self.assertEqual(breakdown["vcenter_kw"], 4.0)


if __name__ == "__main__":
    unittest.main()
