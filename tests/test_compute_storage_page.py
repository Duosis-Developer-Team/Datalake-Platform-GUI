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
        page._save(1, state, "*")

    delete.assert_not_called()
    rows = put.call_args[0][0]
    assert rows == [
        {"family": "virt_classic", "dc_code": "*", "mode": "merged"},
        {"family": "virt_power", "dc_code": "*", "mode": "separate"},
    ]


def test_save_deletes_the_override_when_a_card_goes_back_to_inherit(api_rows):
    state = dict.fromkeys(page._FALLBACK_FAMILIES, "inherit")
    with patch("src.services.api_client.put_storage_couplings") as put, \
         patch("src.services.api_client.delete_storage_coupling") as delete:
        page._save(1, state, "DC13")

    put.assert_not_called()
    # Only virt_classic actually had a DC13 row; the rest were already inheriting.
    delete.assert_called_once_with("virt_classic", "DC13")


def test_save_without_changes_touches_nothing(api_rows):
    state = page._mode_map(page._load_rows()[0], "*")
    with patch("src.services.api_client.put_storage_couplings") as put, \
         patch("src.services.api_client.delete_storage_coupling") as delete:
        msg, *_ = page._save(1, state, "*")

    put.assert_not_called()
    delete.assert_not_called()
    assert "No changes" in str(msg.children)


def test_save_surfaces_the_api_error_instead_of_raising(api_rows):
    state = {"virt_classic": "separate"}
    with patch("src.services.api_client.put_storage_couplings", side_effect=RuntimeError("503 unavailable")), \
         patch("src.services.api_client.delete_storage_coupling"):
        msg, *_ = page._save(1, state, "*")

    assert "503 unavailable" in str(msg.children)


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
    assert "dash_clientside" in js and "set_props" in js
    # Keyboard fallback for operators who cannot drag.
    assert "ArrowLeft" in js and "ArrowRight" in js
    assert ".csc-card" in css and ".csc-zone-body" in css
