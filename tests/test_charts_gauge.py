from __future__ import annotations

import math

from src.components.charts import create_premium_gauge_chart


def _gauge_value(fig) -> float:
    return float(fig.data[0].value)


def _gauge_axis_max(fig) -> float:
    return float(fig.data[0].gauge.axis.range[1])


class TestPremiumGaugeOverflow:
    def test_default_caps_axis_at_100(self):
        fig = create_premium_gauge_chart(278.1, "Test")
        assert _gauge_value(fig) == 278.1
        assert _gauge_axis_max(fig) == 100.0

    def test_allow_over_100_extends_axis(self):
        fig = create_premium_gauge_chart(278.1, "", allow_over_100=True)
        assert _gauge_value(fig) == 278.1
        assert _gauge_axis_max(fig) == float(max(100, math.ceil(278.1 / 50) * 50))

    def test_allow_over_100_keeps_100_axis_when_under_cap(self):
        fig = create_premium_gauge_chart(83.7, "", allow_over_100=True)
        assert _gauge_value(fig) == 83.7
        assert _gauge_axis_max(fig) == 100.0
