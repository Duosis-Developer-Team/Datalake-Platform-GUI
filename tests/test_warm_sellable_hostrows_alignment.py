"""GAP3.2: align the existing sellable + host_rows warm with warm_mode (long
timeout) and — for the time-windowed host_rows — both anchor_latest key variants,
so those warms populate the keys the pages actually read.
"""
from unittest.mock import patch

from src.services import api_client as api
from src.services import app_background_warm as warm


def test_warm_host_rows_warms_both_anchor_variants():
    seen = []
    with patch("src.services.api_client.get_classic_host_rows", side_effect=lambda dc, c, t: seen.append(t)), \
         patch("src.services.api_client.get_hyperconv_host_rows", side_effect=lambda dc, c, t: seen.append(t)):
        warm._warm_host_rows_for_dcs(["DC1"], {"preset": "7d", "start": "a", "end": "b"})

    assert {bool(t.get("anchor_latest")) for t in seen} == {True, False}


def test_warm_host_rows_runs_in_warm_mode():
    observed = []

    def fake(dc, c, t):
        observed.append(api._WARM_MODE.get())

    with patch("src.services.api_client.get_classic_host_rows", side_effect=fake), \
         patch("src.services.api_client.get_hyperconv_host_rows", side_effect=fake):
        warm._warm_host_rows_for_dcs(["DC1"], {"preset": "7d"})

    assert all(observed) and observed, "host_rows warm must run with warm mode (long timeout)"


def test_warm_sellable_runs_in_warm_mode():
    observed = []

    def fake_collect(dc):
        observed.append(api._WARM_MODE.get())

    with patch("src.utils.virt_sellable_aggregate.collect_virt_sellable_panels", side_effect=fake_collect):
        warm._warm_sellable_for_dcs(["DC1"], {"preset": "7d"})

    assert observed == [True], "sellable warm must run with warm mode (long timeout)"
