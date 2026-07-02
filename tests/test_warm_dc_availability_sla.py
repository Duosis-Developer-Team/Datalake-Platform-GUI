"""GAP3.1: warm the Data Centers (get_sla_by_dc) and Availability
(get_dc_availability_sla_items_for_dcs) aggregate calls with the long warm
timeout and both anchor_latest key variants — those calls were never warmed, so
those pages hit a cold >20s SLA query and spun.
"""
from unittest.mock import patch

from src.services import app_background_warm as warm


def test_warm_dc_and_availability_sla_warms_both_getters_and_variants():
    seen_sla, seen_avail = [], []
    with patch("src.services.api_client.get_sla_by_dc", side_effect=lambda t: seen_sla.append(t)), \
         patch("src.services.api_client.get_dc_availability_sla_items_for_dcs",
               side_effect=lambda rows, t: seen_avail.append(t)):
        warm._warm_dc_and_availability_sla([{"id": "DC1"}], {"preset": "7d", "start": "a", "end": "b"})

    assert {bool(t.get("anchor_latest")) for t in seen_sla} == {True, False}
    assert {bool(t.get("anchor_latest")) for t in seen_avail} == {True, False}


def test_warm_dc_and_availability_sla_skips_availability_without_rows():
    seen_sla = []
    with patch("src.services.api_client.get_sla_by_dc", side_effect=lambda t: seen_sla.append(t)), \
         patch("src.services.api_client.get_dc_availability_sla_items_for_dcs") as m_avail:
        warm._warm_dc_and_availability_sla([], {"preset": "7d"})

    assert len(seen_sla) == 2  # sla_by_dc still warmed (both variants)
    m_avail.assert_not_called()  # no dc rows -> nothing to match availability against
