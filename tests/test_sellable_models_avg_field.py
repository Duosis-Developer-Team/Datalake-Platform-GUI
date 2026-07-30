"""PanelResult carries a third sellable track."""
from shared.sellable.models import PanelResult


def _panel(**kw) -> PanelResult:
    base = dict(panel_key="p1", label="L", family="virt_classic",
                resource_kind="cpu", display_unit="vCPU")
    return PanelResult(**{**base, **kw})


def test_sellable_avg_util_defaults_to_none():
    assert _panel().sellable_avg_util is None


def test_sellable_avg_util_round_trips_through_to_dict():
    d = _panel(sellable_allocation=10.0, sellable_max_util=40.0,
               sellable_avg_util=55.0).to_dict()
    assert d["sellable_avg_util"] == 55.0
    assert d["sellable_max_util"] == 40.0
    assert d["sellable_allocation"] == 10.0
