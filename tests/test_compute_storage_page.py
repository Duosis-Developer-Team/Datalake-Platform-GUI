"""Administration -> Platform -> Compute / Storage (drag-and-drop coupling board)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from src.pages.settings.platform import compute_storage as page

_ROWS = [
    {"family": "virt_classic", "dc_code": "*", "mode": "auto", "notes": "", "updated_by": "seed",
     "updated_at": "2026-07-31T10:00:00+00:00"},
    {"family": "virt_hyperconverged", "dc_code": "*", "mode": "merged", "notes": "", "updated_by": "arca",
     "updated_at": "2026-07-31T10:00:00+00:00"},
    {"family": "virt_classic", "dc_code": "DC13", "mode": "separate", "notes": "", "updated_by": "arca",
     "updated_at": "2026-07-31T10:00:00+00:00"},
]


@pytest.fixture
def api_rows():
    with patch("src.services.api_client.get_storage_couplings", return_value=list(_ROWS)), \
         patch("src.services.api_client.get_hmdl_locations", return_value={"items": [{"dc_code": "dc13"},
                                                                                     {"dc_code": "DC14"}]}):
        yield


def _flatten(component) -> list:
    """Depth-first walk over a Dash component tree."""
    out = [component]
    children = getattr(component, "children", None)
    if children is None:
        return out
    if not isinstance(children, (list, tuple)):
        children = [children]
    for child in children:
        if hasattr(child, "children") or hasattr(child, "_prop_names"):
            out.extend(_flatten(child))
    return out


def _cards(layout) -> list:
    return [c for c in _flatten(layout) if getattr(c, "className", "") == "csc-card"]


def _zone_bodies(layout) -> list:
    return [c for c in _flatten(layout) if "csc-zone-body" in str(getattr(c, "className", ""))]


# ---------------------------------------------------------------------------
# registration
# ---------------------------------------------------------------------------


def test_page_is_registered_under_platform():
    from src.pages.settings import shell

    hrefs = [h for h, _l, _c in shell.PLATFORM_TABS]
    assert "/administration/platform/compute-storage" in hrefs
    code, builder = shell._PAGE_BUILDERS["/administration/platform/compute-storage"]
    assert code == "page:settings_platform_compute_storage"
    assert builder is page.build_layout


def test_route_resolves_to_its_own_permission_code():
    """Without this the page would inherit the Backup Mapping fallback."""
    from src.auth.permission_service import resolve_pathname_to_page_code

    assert resolve_pathname_to_page_code("/administration/platform/compute-storage") == (
        "page:settings_platform_compute_storage"
    )


def test_permission_catalog_has_the_node():
    from src.auth.permission_catalog import build_default_permission_roots

    codes: set[str] = set()

    def _walk(nodes):
        for n in nodes:
            codes.add(n.code)
            _walk(list(n.children or []))

    _walk(build_default_permission_roots())
    assert "page:settings_platform_compute_storage" in codes


# ---------------------------------------------------------------------------
# board
# ---------------------------------------------------------------------------


def test_layout_renders_one_draggable_card_per_family(api_rows):
    layout = page.build_layout()
    cards = _cards(layout)

    families = {c.__getattribute__("data-family") for c in cards}
    assert families == set(page._FALLBACK_FAMILIES)
    assert all(c.draggable == "true" for c in cards)
    assert all(c.tabIndex == 0 for c in cards)


def test_replication_families_default_to_separate_without_rows(api_rows):
    """UI matches migration 043 seed when the API has no replication coupling yet."""
    rows, _ = page._load_rows()
    modes = page._mode_map(rows, "*")
    for fam in (
        "backup_veeam_replication_classic",
        "backup_zerto_replication_classic",
        "backup_veeam_replication_hyperconverged",
        "backup_zerto_replication_hyperconverged",
    ):
        assert modes[fam] == "separate"


def test_default_scope_has_no_inherit_zone(api_rows):
    layout = page.build_layout()
    modes = [b.__getattribute__("data-mode") for b in _zone_bodies(layout)]
    assert modes == ["auto", "merged", "separate"]


def test_per_dc_scope_offers_an_inherit_zone(api_rows):
    board = page._board(page._load_rows()[0], "DC13")
    modes = [b.__getattribute__("data-mode") for b in _zone_bodies(board)]
    assert modes == ["inherit", "auto", "merged", "separate"]


def test_cards_carry_their_loaded_mode_for_dirty_tracking(api_rows):
    rows, _ = page._load_rows()
    board = page._board(rows, "*")
    by_family = {c.__getattribute__("data-family"): c for c in _cards(board)}
    assert by_family["virt_hyperconverged"].__getattribute__("data-initial-mode") == "merged"
    assert by_family["virt_classic"].__getattribute__("data-initial-mode") == "auto"


def test_mode_map_inherit_semantics(api_rows):
    rows, _ = page._load_rows()
    assert page._mode_map(rows, "*")["virt_hyperconverged"] == "merged"
    # DC13 has its own virt_classic row; everything else inherits the default.
    dc13 = page._mode_map(rows, "DC13")
    assert dc13["virt_classic"] == "separate"
    assert dc13["virt_hyperconverged"] == "inherit"
    # A DC with no rows at all inherits everything.
    assert set(page._mode_map(rows, "DC14").values()) == {"inherit"}


def test_scope_options_merge_saved_dcs_and_the_location_list(api_rows):
    rows, _ = page._load_rows()
    values = [o["value"] for o in page._scope_options(rows)]
    assert values == ["*", "DC13", "DC14"]


def test_layout_renders_when_the_api_is_down():
    with patch("src.services.api_client.get_storage_couplings", side_effect=RuntimeError("crm-engine down")), \
         patch("src.services.api_client.get_hmdl_locations", side_effect=RuntimeError("down")):
        layout = page.build_layout()
    # Still one card per known family, so the operator sees the board, not a blank page.
    assert len(_cards(layout)) == len(page._FALLBACK_FAMILIES)


# ---------------------------------------------------------------------------
# save
# ---------------------------------------------------------------------------


def test_save_sends_only_the_moved_families(api_rows):
    state = {
        "virt_classic": "merged",          # changed (was auto)
        "virt_hyperconverged": "merged",   # unchanged
        "virt_power": "separate",          # changed (had no row -> auto)
        "virt_km": "auto",                 # unchanged
        "virt_intel_hana": "auto",
        "virt_power_hana": "auto",
    }
    with patch("src.services.api_client.put_storage_couplings", return_value={"status": "ok"}) as put, \
         patch("src.services.api_client.delete_storage_coupling") as delete:
        page._save(1, state, "*", False)

    delete.assert_not_called()
    rows = put.call_args[0][0]
    assert rows == [
        {"family": "virt_classic", "dc_code": "*", "scope_kind": "family", "scope_key": "",
         "mode": "merged"},
        {"family": "virt_power", "dc_code": "*", "scope_kind": "family", "scope_key": "",
         "mode": "separate"},
    ]


def test_save_deletes_the_override_when_a_card_goes_back_to_inherit(api_rows):
    state = dict.fromkeys(page._FALLBACK_FAMILIES, "inherit")
    with patch("src.services.api_client.put_storage_couplings") as put, \
         patch("src.services.api_client.delete_storage_coupling") as delete:
        page._save(1, state, "DC13", False)

    put.assert_not_called()
    # Only virt_classic actually had a DC13 row; the rest were already inheriting.
    delete.assert_called_once_with("virt_classic", "DC13", scope_kind="family", scope_key="")


def test_save_without_changes_touches_nothing(api_rows):
    state = page._mode_map(page._load_rows()[0], "*")
    with patch("src.services.api_client.put_storage_couplings") as put, \
         patch("src.services.api_client.delete_storage_coupling") as delete:
        msg, *_ = page._save(1, state, "*", False)

    put.assert_not_called()
    delete.assert_not_called()
    assert "No changes" in str(msg.children)


def test_save_surfaces_the_api_error_instead_of_raising(api_rows):
    state = {"virt_classic": "separate"}
    with patch("src.services.api_client.put_storage_couplings", side_effect=RuntimeError("503 unavailable")), \
         patch("src.services.api_client.delete_storage_coupling"):
        msg, *_ = page._save(1, state, "*", False)

    assert "503 unavailable" in str(msg.children)


# ---------------------------------------------------------------------------
# cluster detail (migration 038)
# ---------------------------------------------------------------------------


@pytest.fixture
def api_clusters():
    """Two host-based families with clusters in DC13."""
    with patch("src.services.api_client.get_classic_cluster_list", return_value=["CL-A"]), \
         patch("src.services.api_client.get_hyperconv_cluster_list", return_value=["HCI-1", "HCI-2"]):
        yield


def test_clusters_are_never_offered_for_the_global_scope(api_clusters):
    """Cluster names are DC-local, so a '*' cluster rule would be ambiguous."""
    assert page._clusters_for("*") == []
    assert page._clusters_for("DC13") == [
        ("backup_veeam_replication_classic", "CL-A"),
        ("backup_veeam_replication_hyperconverged", "HCI-1"),
        ("backup_veeam_replication_hyperconverged", "HCI-2"),
        ("backup_zerto_replication_classic", "CL-A"),
        ("backup_zerto_replication_hyperconverged", "HCI-1"),
        ("backup_zerto_replication_hyperconverged", "HCI-2"),
        ("virt_classic", "CL-A"),
        ("virt_hyperconverged", "HCI-1"),
        ("virt_hyperconverged", "HCI-2"),
    ]


def test_cluster_key_round_trips_names_containing_a_colon():
    key = page._cluster_key("virt_classic", "DC13:CL-A")
    assert page._split_cluster_key(key) == ("virt_classic", "DC13:CL-A")
    assert page._split_cluster_key("virt_classic") is None


def test_detail_board_has_one_card_per_cluster(api_rows, api_clusters):
    rows, _ = page._load_rows()
    board = page._board(rows, "DC13", detail=True, clusters=page._clusters_for("DC13"))
    keys = {c.__getattribute__("data-card-key") for c in _cards(board)}
    assert keys == {
        "cluster:backup_veeam_replication_classic:CL-A",
        "cluster:backup_veeam_replication_hyperconverged:HCI-1",
        "cluster:backup_veeam_replication_hyperconverged:HCI-2",
        "cluster:backup_zerto_replication_classic:CL-A",
        "cluster:backup_zerto_replication_hyperconverged:HCI-1",
        "cluster:backup_zerto_replication_hyperconverged:HCI-2",
        "cluster:virt_classic:CL-A",
        "cluster:virt_hyperconverged:HCI-1",
        "cluster:virt_hyperconverged:HCI-2",
    }
    # Every cluster starts on 'inherit' — no cluster rows exist yet.
    modes = [b.__getattribute__("data-mode") for b in _zone_bodies(board)]
    assert modes == ["inherit", "auto", "merged", "separate"]


def test_detail_board_explains_itself_when_a_dc_has_no_clusters(api_rows):
    with patch("src.services.api_client.get_classic_cluster_list", return_value=[]), \
         patch("src.services.api_client.get_hyperconv_cluster_list", return_value=[]):
        board = page._board(page._load_rows()[0], "DC14", detail=True, clusters=[])
    assert "No clusters" in str(board.title)


def test_cluster_cards_show_the_family_rule_they_would_override(api_rows, api_clusters):
    rows, _ = page._load_rows()
    board = page._board(rows, "DC13", detail=True, clusters=page._clusters_for("DC13"))
    labels = {
        c.__getattribute__("data-card-key"): str(c.children[1].children)
        for c in _cards(board)
    }
    # virt_classic has its own DC13 row (separate); hyperconverged falls back to '*' (merged).
    assert "separate" in labels["cluster:virt_classic:CL-A"]
    assert "merged" in labels["cluster:virt_hyperconverged:HCI-1"]


def test_save_writes_cluster_scoped_rows(api_rows, api_clusters):
    state = {
        "cluster:virt_classic:CL-A": "merged",
        "cluster:virt_hyperconverged:HCI-1": "inherit",  # unchanged, no row exists
    }
    with patch("src.services.api_client.put_storage_couplings", return_value={"status": "ok"}) as put, \
         patch("src.services.api_client.delete_storage_coupling") as delete:
        page._save(1, state, "DC13", True)

    delete.assert_not_called()
    assert put.call_args[0][0] == [
        {"family": "virt_classic", "dc_code": "DC13", "scope_kind": "cluster",
         "scope_key": "CL-A", "mode": "merged"},
    ]


def test_save_deletes_a_cluster_row_dropped_back_to_inherit(api_clusters):
    rows = list(_ROWS) + [
        {"family": "virt_classic", "dc_code": "DC13", "scope_kind": "cluster", "scope_key": "CL-A",
         "mode": "merged", "notes": "", "updated_by": "arca", "updated_at": "2026-07-31T10:00:00+00:00"},
    ]
    with patch("src.services.api_client.get_storage_couplings", return_value=rows), \
         patch("src.services.api_client.get_hmdl_locations", return_value={"items": []}), \
         patch("src.services.api_client.put_storage_couplings") as put, \
         patch("src.services.api_client.delete_storage_coupling") as delete:
        page._save(1, {"cluster:virt_classic:CL-A": "inherit"}, "DC13", True)

    put.assert_not_called()
    delete.assert_called_once_with(
        "virt_classic", "DC13", scope_kind="cluster", scope_key="CL-A"
    )


def test_saving_the_family_board_never_touches_cluster_rows(api_rows, api_clusters):
    """The store can only ever hold one granularity; guard against a stale one."""
    state = {"cluster:virt_classic:CL-A": "merged", "virt_classic": "merged"}
    with patch("src.services.api_client.put_storage_couplings", return_value={"status": "ok"}) as put, \
         patch("src.services.api_client.delete_storage_coupling") as delete:
        page._save(1, state, "DC13", False)

    delete.assert_not_called()
    assert put.call_args[0][0] == [
        {"family": "virt_classic", "dc_code": "DC13", "scope_kind": "family", "scope_key": "",
         "mode": "merged"},
    ]


def test_detail_switch_is_disabled_and_reset_when_scope_goes_global(api_rows, api_clusters):
    _board, _state, disabled, checked = page._switch_scope("*")
    assert disabled is True and checked is False
    _board, _state, disabled, checked = page._switch_scope("DC13")
    assert disabled is False and checked is False


# ---------------------------------------------------------------------------
# assets — the drag-and-drop lives in plain JS, so keep the contract pinned
# ---------------------------------------------------------------------------


def test_drag_and_drop_assets_match_the_layout_hooks():
    root = Path(__file__).resolve().parents[1]
    js = (root / "assets" / "coupling_board.js").read_text(encoding="utf-8")
    css = (root / "assets" / "coupling_board.css").read_text(encoding="utf-8")

    assert page._BOARD_ID in js
    assert page._STORE_ID in js
    assert "data-coupling-card" in js
    assert "data-coupling-zone-body" in js
    # Cluster cards share a family, so the store must key off the card key.
    assert "data-card-key" in js
    assert "dash_clientside" in js and "set_props" in js
    # Keyboard fallback for operators who cannot drag.
    assert "ArrowLeft" in js and "ArrowRight" in js
    assert ".csc-card" in css and ".csc-zone-body" in css
