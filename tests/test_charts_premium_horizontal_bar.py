"""Tests for premium horizontal bar chart edge cases."""

from src.components.charts import create_premium_horizontal_bar_chart


def test_create_premium_horizontal_bar_chart_empty_data_no_crash():
    """Empty labels/values must not call max() on an empty sequence."""
    fig = create_premium_horizontal_bar_chart([], [], title="Top interfaces", unit_suffix="Gbps")
    assert fig is not None
    assert fig.layout.height is not None
    # Empty state annotation
    assert fig.layout.annotations
    assert fig.layout.annotations[0].text == "No data"
