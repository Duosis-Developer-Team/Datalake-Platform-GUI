"""P0-6: the filtered-compute cache must key on the window it actually queried.

`anchor_latest` is a per-browser user setting ("pin the window's end to the
latest ingested timestamp") that the GUI sends as a query param. Two operators
looking at the same DC, same preset, same cluster selection, one with the
setting on and one with it off, are asking two different questions:

    off →  2026-07-28 .. 2026-08-03   (wall clock)
    on  →  2026-07-10 .. 2026-07-16   (ingestion stopped on the 16th)

`get_classic_metrics_filtered` built its cache key from the *pre-anchor* tr and
applied the anchor afterwards, so both questions hashed to one key. Whichever
request arrived first populated it, and for the next ten minutes the other
operator was served an answer to a question they did not ask — CPU/RAM/storage
for a window they never selected. Reload after the TTL and the numbers change
under them with nothing on screen to explain it.

`get_hyperconv_metrics_filtered` had the same key and never anchored at all,
which produces a second, sharper version: it falls through to `get_dc_details`
(which *does* anchor) whenever the selection is empty or covers every cluster,
so deselecting a single cluster silently moved the time window.

Every sibling method in this file — get_dc_details, get_all_datacenters_summary,
get_global_overview, get_global_dashboard, get_datastore_mapping — already
anchors before it builds its key. These two were the outliers.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from psycopg2 import OperationalError

from app.services.dc_service import DatabaseService

# Ingestion is 18 days behind wall clock — the DC14 situation, and the reason
# anchor_latest exists at all.
LATEST_TS = datetime(2026, 7, 16, 9, 30, 0, tzinfo=timezone.utc)

PRESET_7D = {"start": "2026-07-28", "end": "2026-08-03", "preset": "7d"}
PRESET_7D_ANCHORED = {**PRESET_7D, "anchor_latest": True}

CLUSTERS = ["KM-1"]


def _make_service():
    with patch(
        "app.services.dc_service.pg_pool.ThreadedConnectionPool",
        side_effect=OperationalError("no db"),
    ):
        svc = DatabaseService()
    svc._dc_list = ["DC13"]
    return svc


class _Cur:
    pass


class _Ctx:
    def __enter__(self):
        return _Cur()

    def __exit__(self, *a):
        return False


class _Conn:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return _Ctx()


class _Recorder:
    """Drives either filtered-metrics body without a database.

    Records the cache keys the method asked for and the SQL bounds it ran with,
    which is the pair the bug decouples: the key said one window, the query used
    another.
    """

    def __init__(self):
        self.keys: list[str] = []
        self.starts: list[datetime] = []

    def get_cached(self, key, _factory=None):
        self.keys.append(key)
        return None  # always a miss, so the body runs every time

    def set_cached(self, key, value):
        pass

    def run_row(self, cur, sql, params):
        # start_ts is the 3rd bind in both merged queries.
        self.starts.append(params[2])
        return None

    def run_value(self, cur, sql, params):
        return 0


def _expected_anchored_start():
    """Where an anchored 7d window starts, read off the service's own table.

    Not hard-coded: _RELATIVE_PRESET_OFFSETS uses 7 days for "7d" while
    preset_to_range uses 6 (7 calendar days inclusive), so an anchored window is
    one day wider than the unanchored one with the same name. That predates this
    change and applies to every anchored path in the service; pinning the number
    here would only make this test a second place to update.
    """
    return LATEST_TS.date() - DatabaseService._RELATIVE_PRESET_OFFSETS["7d"]


def _drive(svc, method, tr, rec, latest_ts=LATEST_TS):
    """Call a *_metrics_filtered method with every DB touchpoint stubbed."""
    with patch.object(svc, "_compute_cached_or_revalidate", rec.get_cached), \
         patch.object(svc, "_set_compute_cached", rec.set_cached), \
         patch.object(svc, "_is_full_cluster_selection", return_value=False), \
         patch.object(svc, "_get_latest_data_ts", return_value=latest_ts), \
         patch.object(svc, "_get_connection", return_value=_Conn()), \
         patch.object(svc, "_run_row", rec.run_row), \
         patch.object(svc, "_run_value", rec.run_value), \
         patch.object(svc, "get_classic_storage_vm", return_value={}), \
         patch.object(svc, "get_hyperconv_storage_vm", return_value={}), \
         patch.object(svc, "get_classic_mem_peak_raw", return_value=None), \
         patch.object(svc, "get_hyperconv_mem_peak_raw", return_value=None), \
         patch.object(svc, "get_unit_prices_tl", return_value={}), \
         patch.object(svc, "_km_datastore_storage_gb", return_value=(0.0, 0.0)), \
         patch.object(svc, "_apply_classic_mem_stats", side_effect=lambda s, *a, **k: s):
        return getattr(svc, method)("DC13", CLUSTERS, dict(tr))


# --- the key itself ---------------------------------------------------------


def test_the_anchor_flag_is_part_of_the_cache_key():
    """Pinned at the key builder as well as at the call sites.

    The flag is belt-and-braces next to anchoring-before-keying: it is what
    keeps the two requests apart on the days _smart_1h_tr cannot resolve an
    anchor and hands the window back untouched.
    """
    plain = DatabaseService._compute_cache_key("classic", "DC13", PRESET_7D, CLUSTERS)
    anchored = DatabaseService._compute_cache_key("classic", "DC13", PRESET_7D_ANCHORED, CLUSTERS)

    assert plain != anchored


def test_the_key_still_separates_kinds_dcs_windows_and_clusters():
    """The dimensions that were already right must stay right."""
    base = DatabaseService._compute_cache_key("classic", "DC13", PRESET_7D, CLUSTERS)

    assert base != DatabaseService._compute_cache_key("hyperconv", "DC13", PRESET_7D, CLUSTERS)
    assert base != DatabaseService._compute_cache_key("classic", "DC14", PRESET_7D, CLUSTERS)
    assert base != DatabaseService._compute_cache_key(
        "classic", "DC13", {**PRESET_7D, "end": "2026-08-02"}, CLUSTERS
    )
    assert base != DatabaseService._compute_cache_key("classic", "DC13", PRESET_7D, ["KM-2"])


def test_cluster_order_does_not_change_the_key():
    """Selection order is UI noise, not a different question."""
    assert DatabaseService._compute_cache_key(
        "classic", "DC13", PRESET_7D, ["KM-2", "KM-1"]
    ) == DatabaseService._compute_cache_key("classic", "DC13", PRESET_7D, ["KM-1", "KM-2"])


# --- classic: key and query must describe the same window -------------------


def test_classic_keys_on_the_window_it_actually_queries():
    """The core defect. The key was built before the anchor was applied, so it
    named the wall-clock window while the SQL ran against the anchored one."""
    rec = _Recorder()
    _drive(_make_service(), "get_classic_metrics_filtered", PRESET_7D_ANCHORED, rec)

    assert rec.starts, "the body did not reach the SQL"
    queried_start = rec.starts[0]
    assert queried_start.date() == _expected_anchored_start()
    assert queried_start.strftime("%Y-%m-%d") in rec.keys[0], (
        f"key {rec.keys[0]!r} names a window the query never used ({queried_start})"
    )
    assert "2026-07-28" not in rec.keys[0], "the pre-anchor window must not survive into the key"


def test_classic_anchored_and_unanchored_requests_do_not_share_an_entry():
    """The user-visible symptom: two operators, one setting apart, one answer."""
    svc = _make_service()
    plain, anchored = _Recorder(), _Recorder()

    _drive(svc, "get_classic_metrics_filtered", PRESET_7D, plain)
    _drive(svc, "get_classic_metrics_filtered", PRESET_7D_ANCHORED, anchored)

    assert plain.keys[0] != anchored.keys[0]
    assert plain.starts[0] != anchored.starts[0], "different keys, and genuinely different windows"


def test_classic_keys_stay_apart_when_anchoring_finds_nothing_to_anchor_to():
    """_smart_1h_tr returns the range untouched when no ingested timestamp is
    available — DB down, or the 60 s `latest_vm_ts` lookup failed. Without the
    explicit flag the two requests would collapse back onto one key at exactly
    the moment the platform is least healthy."""
    svc = _make_service()
    plain, anchored = _Recorder(), _Recorder()

    _drive(svc, "get_classic_metrics_filtered", PRESET_7D, plain, latest_ts=None)
    _drive(svc, "get_classic_metrics_filtered", PRESET_7D_ANCHORED, anchored, latest_ts=None)

    assert plain.starts[0] == anchored.starts[0], "no anchor available: same window, as expected"
    assert plain.keys[0] != anchored.keys[0], "but still not the same cache entry"


# --- hyperconv: the same key, plus an anchor it never applied ---------------


def test_hyperconv_honours_the_anchor_setting():
    """It ignored anchor_latest outright, so the Hyperconverged panel reported a
    different time window than the Classic panel beside it on the same page."""
    rec = _Recorder()
    _drive(_make_service(), "get_hyperconv_metrics_filtered", PRESET_7D_ANCHORED, rec)

    assert rec.starts, "the body did not reach the SQL"
    assert rec.starts[0].date() == _expected_anchored_start()


def test_hyperconv_filtered_matches_the_unfiltered_page_it_falls_through_to():
    """Selecting every cluster returns get_dc_details' section, which anchors.
    Deselecting one dropped into this body, which did not — so the window moved
    when the operator touched the cluster picker, and nothing said so."""
    svc = _make_service()
    rec = _Recorder()

    _drive(svc, "get_hyperconv_metrics_filtered", PRESET_7D_ANCHORED, rec)

    with patch.object(svc, "_get_latest_data_ts", return_value=LATEST_TS):
        expected = svc._smart_1h_tr(dict(PRESET_7D_ANCHORED))
    assert rec.starts[0].strftime("%Y-%m-%d") == expected["start"]


def test_hyperconv_anchored_and_unanchored_requests_do_not_share_an_entry():
    svc = _make_service()
    plain, anchored = _Recorder(), _Recorder()

    _drive(svc, "get_hyperconv_metrics_filtered", PRESET_7D, plain)
    _drive(svc, "get_hyperconv_metrics_filtered", PRESET_7D_ANCHORED, anchored)

    assert plain.keys[0] != anchored.keys[0]
    assert plain.starts[0] != anchored.starts[0]


# --- the fall-through paths must keep working -------------------------------


def test_an_empty_selection_still_returns_the_unfiltered_section():
    svc = _make_service()
    with patch.object(svc, "get_dc_details", return_value={"classic": {"hosts": 9}}):
        assert svc.get_classic_metrics_filtered("DC13", [], PRESET_7D_ANCHORED)["hosts"] == 9


def test_a_full_selection_still_returns_the_unfiltered_section():
    svc = _make_service()
    with patch.object(svc, "_is_full_cluster_selection", return_value=True), \
         patch.object(svc, "get_dc_details", return_value={"hyperconv": {"hosts": 4}}):
        out = svc.get_hyperconv_metrics_filtered("DC13", CLUSTERS, PRESET_7D_ANCHORED)
    assert out["hosts"] == 4
