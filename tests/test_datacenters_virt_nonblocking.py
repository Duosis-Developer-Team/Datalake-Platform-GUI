"""Data Centers page must render without blocking on the slow per-DC sellable fetch.

The synchronous `_seed_from_api_cache` fetched virt sellable for every DC (crm-engine,
15-80s each cold) inside `resolve_virt_sellable_for_dcs`, which runs on the page-render
path — so the whole /datacenters page stayed BLANK for minutes. The two-phase design
(Interval poll + background warm) already exists; resolve must return immediately in a
loading state and let the background warm + poll fill the data.
"""
from unittest.mock import patch
from src.utils import datacenters_virt_sellable as dvs


def _reset_cache():
    with dvs._VIRT_CACHE_LOCK:
        dvs._VIRT_TL_CACHE.clear()
        dvs._VIRT_CACHE_WARMING = False
        dvs._VIRT_CACHE_TR_KEY = ""


def test_resolve_does_not_fetch_synchronously_on_render_path():
    _reset_cache()
    tr = {"start": "2026-06-08", "end": "2026-06-14", "preset": "7d", "anchor_latest": True}
    with patch.object(dvs, "_seed_from_api_cache") as seed, \
         patch.object(dvs, "start_virt_cache_warm", return_value=True) as warm:
        out = dvs.resolve_virt_sellable_for_dcs(["DC1", "DC2"], tr)
    # The blocking synchronous seed-fetch must NOT run on the render path.
    seed.assert_not_called()
    # Instead a background warm is kicked off (non-blocking).
    warm.assert_called_once()
    # Page renders in loading state; the Interval poll fills the values later.
    assert out["loading"] is True
    assert out["total_potential_tl"] == 0.0


def test_resolve_serves_warm_cache_without_refetch():
    _reset_cache()
    tr = {"start": "2026-06-08", "end": "2026-06-14", "preset": "7d", "anchor_latest": True}
    tr_key = dvs.virt_cache_tr_key(tr)
    with dvs._VIRT_CACHE_LOCK:
        dvs._VIRT_TL_CACHE.update({"DC1": 100.0, "DC2": 200.0})
        dvs._VIRT_CACHE_TR_KEY = tr_key
    with patch.object(dvs, "_seed_from_api_cache") as seed, \
         patch.object(dvs, "start_virt_cache_warm", return_value=True) as warm:
        out = dvs.resolve_virt_sellable_for_dcs(["DC1", "DC2"], tr)
    seed.assert_not_called()
    warm.assert_not_called()          # cache complete -> no warm needed
    assert out["loading"] is False
    assert out["total_potential_tl"] == 300.0
