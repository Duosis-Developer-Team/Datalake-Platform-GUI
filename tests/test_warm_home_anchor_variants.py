"""Warm must populate BOTH the anchor_latest and non-anchor cache keys for the
home/overview + datacenters data, because the pages fetch with anchor_latest
(a user toggle) but the old warm only cached the non-anchor key — so the page
missed the warm and hit the slow backend cold every time.
"""
from unittest.mock import patch

from src.services import app_background_warm as warm


def test_warm_home_bundle_warms_both_anchor_variants():
    seen = []
    with patch("src.services.api_client.get_global_dashboard", side_effect=lambda t: seen.append(("gd", t))), \
         patch("src.services.api_client.get_all_datacenters_summary", side_effect=lambda t: seen.append(("dc", t))):
        warm._warm_home_bundle({"preset": "7d", "start": "a", "end": "b"})

    anchors = {bool(t.get("anchor_latest")) for _, t in seen}
    assert anchors == {True, False}, "both anchor_latest and non-anchor keys must be warmed"
