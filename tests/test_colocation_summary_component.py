"""build_colocation_summary: KPI tiles + a 100% stacked bar (External/Internal/
Untagged) showing where a DC's used rack-U goes. English labels only."""
from src.components.colocation_summary import build_colocation_summary


def test_summary_renders_tiles_bar_and_split_labels():
    agg = {"total_u": 1000, "used_u": 600, "free_u": 400, "rack_count": 10,
           "external_u": 149, "internal_u": 300, "untagged_u": 151,
           "external_customer_count": 5}
    text = str(build_colocation_summary(agg))
    assert "Total U" in text and "600" in text and "Racks" in text
    assert "External 149U (5 customers)" in text
    assert "Internal 300U" in text
    assert "Untagged 151U" in text


def test_summary_hides_bar_when_split_absent():
    text = str(build_colocation_summary({"total_u": 5, "used_u": 0, "free_u": 5, "rack_count": 1}))
    assert "Total U" in text            # tiles still render
    assert "where it goes" not in text  # no bar when split is all zero


def test_summary_customer_count_override():
    agg = {"total_u": 100, "used_u": 60, "free_u": 40, "rack_count": 3,
           "external_u": 20, "internal_u": 25, "untagged_u": 15,
           "external_customer_count": 9}
    text = str(build_colocation_summary(agg, customer_count=2))
    assert "External 20U (2 customers)" in text
