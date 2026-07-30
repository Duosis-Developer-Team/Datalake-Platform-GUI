# tests/test_floor_map_load_lens.py
from src.pages import floor_map as fm


def test_unmonitored_rack_is_not_coloured_as_idle():
    # A rack with no metrics must never read as prime free capacity.
    assert fm._color_by_load("active", None) == fm.LOAD_PALETTE["unmonitored"]


def test_load_thresholds_match_the_colocation_lens_steps():
    assert fm._color_by_load("active", 10.0) == fm.LOAD_PALETTE["green"]
    assert fm._color_by_load("active", 49.9) == fm.LOAD_PALETTE["green"]
    assert fm._color_by_load("active", 50.0) == fm.LOAD_PALETTE["orange"]
    assert fm._color_by_load("active", 80.0) == fm.LOAD_PALETTE["orange"]
    assert fm._color_by_load("active", 80.1) == fm.LOAD_PALETTE["red"]


def test_closed_beats_load():
    # Mirrors _color_by_fill's closed-before-empty ordering.
    for status in ("inactive", "planned", "closed"):
        assert fm._color_by_load(status, 95.0) == fm.LOAD_PALETTE["closed"]


def test_closed_beats_unmonitored_too():
    # The guard order is the point: a closed rack is gray whether its load is
    # hot, cold, or absent. Checking None first would flip this to near-white
    # and every other test in this file would still pass.
    for status in ("inactive", "planned", "closed"):
        assert fm._color_by_load(status, None) == fm.LOAD_PALETTE["closed"]


def test_load_palette_has_no_turquoise_idle_step():
    # A 0% reading is far more often a silent collector than idle hardware.
    assert "empty" not in fm.LOAD_PALETTE
    assert fm._color_by_load("active", 0.0) == fm.LOAD_PALETTE["green"]


def test_legends_are_english_and_lens_specific():
    coloc = str(fm.build_lens_legend("coloc"))
    load = str(fm.build_lens_legend("load"))
    assert "Fully free (sellable)" in coloc
    assert "Closed / inactive" in coloc
    assert "Not monitored" in load
    assert "Heavy load" in load
    assert "Fully free (sellable)" not in load
    for text in (coloc, load):
        for turkish in ("Tamamen boş", "Çok dolu", "Bilinmiyor", "Kapalı"):
            assert turkish not in text


def test_not_monitored_legend_entry_explains_customer_owned_hardware():
    # "Not monitored" is the Load lens's largest, permanent category:
    # customer-owned colocation racks are never monitored by Bulutistan, on
    # principle, not as a temporary gap. That needs to be visible somewhere
    # near the swatch, not just known tribal knowledge.
    load = str(fm.build_lens_legend("load"))
    assert "customer" in load.lower()
    assert "Bulutistan" in load


def test_coloc_legend_has_no_unmonitored_tooltip():
    # The tooltip is Load-specific copy; the Colocation legend's "Unknown"
    # swatch means something different (occupancy not yet fetched) and must
    # not pick up load-lens wording.
    coloc = str(fm.build_lens_legend("coloc"))
    assert fm._UNMONITORED_TOOLTIP not in coloc


def test_load_coverage_note_treats_truthy_zero_total_as_unavailable():
    # total_racks=0 is a real, non-None value get_dc_racks_load's own
    # DB-outage fallback returns (HTTP 200, not an exception) -- it is not a
    # "no summary" sentinel. `not total` must catch it; `total is None`
    # alone would not, and would print "Load data: 0 of 0 racks monitored"
    # as if that were real coverage. A DC that genuinely has zero racks
    # never reaches this function (build_recolored_floor_map_figure returns
    # (None, None) first), so total_racks == 0 here always means the
    # backend could not answer.
    note = str(fm.build_load_coverage_note({"monitored_racks": 0, "total_racks": 0}))
    assert "unavailable" in note
    assert "0 of 0" not in note


def test_load_coverage_note_reports_real_nonzero_coverage():
    note = str(fm.build_load_coverage_note({"monitored_racks": 38, "total_racks": 214}))
    assert "38 of 214 racks monitored" in note


def test_load_hover_device_counts_fall_back_to_unknown_not_zero():
    # aggregate_rack_load always sets monitored_devices/total_devices
    # alongside a real load_pct, so this path can't fire today -- but the
    # fallback for a missing key must still read "unknown" (this file's
    # established em-dash convention), never a confident "0", consistent
    # with the rest of the hover text (doluluk_str/free_str/pwr/rh/...).
    racks = [{"id": "R1", "name": "104", "status": "active", "u_height": 47, "hall_name": "DH7"}]
    load = {"104": {"load_pct": 42.0}}  # monitored_devices/total_devices missing
    fig = fm.build_floor_map_figure(racks, dc_id="DC13-load-fallback", load=load, lens="load")
    load_str = fig.data[0].customdata[0][12]
    assert load_str == "42% (—/— devices)"
    assert "0/0 devices" not in load_str
