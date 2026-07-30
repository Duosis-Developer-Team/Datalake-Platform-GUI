"""API/snapshot contract for the avg sellable track."""
from app.services.inventory_overview_service import _sellable_track_fields
from shared.sellable.models import PanelResult


def _panel(**kw) -> PanelResult:
    base = dict(panel_key="p1", label="CPU", family="virt_classic",
                resource_kind="cpu", display_unit="vCPU",
                unit_price_tl=100.0, has_price=True, has_infra_source=True)
    return PanelResult(**{**base, **kw})


class TestTrackFields:
    def test_exposes_avg_qty_and_tl(self):
        out = _sellable_track_fields(
            _panel(sellable_allocation=10.0, sellable_max_util=40.0,
                   sellable_avg_util=55.0, potential_tl_min=1000.0,
                   potential_tl_max=4000.0),
            has_infra=True, hide_used=True,
        )
        assert out["sellable_avg_qty"] == 55.0
        assert out["potential_tl_avg"] == 55.0 * 100.0

    def test_avg_is_none_when_track_absent(self):
        # Missing avg must render as an em-dash, not as 0 and not as a mean.
        out = _sellable_track_fields(
            _panel(sellable_allocation=10.0, sellable_max_util=40.0),
            has_infra=True, hide_used=True,
        )
        assert out["sellable_avg_qty"] is None
        assert out["potential_tl_avg"] is None

    def test_no_infra_source_returns_none_avg(self):
        out = _sellable_track_fields(_panel(), has_infra=False, hide_used=True)
        assert out["sellable_avg_qty"] is None
        assert out["potential_tl_avg"] is None

    def test_avg_tl_is_none_without_a_price(self):
        # A quantity with no unit price must not produce a TL figure.
        out = _sellable_track_fields(
            _panel(sellable_avg_util=55.0, has_price=False),
            has_infra=True, hide_used=True,
        )
        assert out["sellable_avg_qty"] == 55.0
        assert out["potential_tl_avg"] is None


class TestSerializationRoundTrip:
    def test_avg_survives_serialize_then_hydrate(self):
        from app.services.sellable_service import SellableService
        payload = SellableService._panel_summary_dict(_panel(sellable_avg_util=55.0))
        assert payload["sellable_avg_util"] == 55.0
        restored = SellableService._panel_result_from_dict(payload)
        assert restored.sellable_avg_util == 55.0

    def test_legacy_payload_without_avg_hydrates_to_none(self):
        # Snapshots written before this change must not break.
        from app.services.sellable_service import SellableService
        payload = SellableService._panel_summary_dict(_panel(sellable_avg_util=55.0))
        del payload["sellable_avg_util"]
        assert SellableService._panel_result_from_dict(payload).sellable_avg_util is None

    def test_zero_avg_hydrates_as_zero_not_none(self):
        # 0.0 means "nothing sellable"; None means "not computed". The
        # `is not None` idiom must keep them distinct.
        from app.services.sellable_service import SellableService
        payload = SellableService._panel_summary_dict(_panel(sellable_avg_util=0.0))
        assert SellableService._panel_result_from_dict(payload).sellable_avg_util == 0.0


class TestPowerFamiliesUnaffected:
    def test_allocation_only_nulls_the_avg_track(self):
        from app.services.sellable_service import SellableService
        p = _panel(family="virt_power", sellable_constrained=5.0,
                   sellable_max_util=9.0, sellable_avg_util=9.0)
        SellableService._apply_allocation_only_pricing(p)
        assert p.sellable_max_util is None
        assert p.sellable_avg_util is None
