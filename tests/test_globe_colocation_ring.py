"""Globe points carry coloc_* fields; the DC info card renders a Kolokasyon ring."""
from unittest.mock import patch

from src.pages import global_view as gv


def test_build_globe_data_carries_coloc_fields():
    summaries = [{
        "id": "DC13", "site_name": "IST", "name": "DC13", "description": "Equinix",
        "status": "active", "vm_count": 10, "host_count": 2, "stats": {"used_cpu_pct": 40, "used_ram_pct": 50},
        "coloc_total_u": 3616, "coloc_used_u": 1817, "coloc_free_u": 1799,
    }]
    pts = gv._build_globe_data(summaries)
    assert pts and pts[0]["coloc_free_u"] == 1799
    assert pts[0]["coloc_used_u"] == 1817
    assert pts[0]["coloc_total_u"] == 3616


def test_coloc_fields_default_zero_when_absent():
    summaries = [{
        "id": "DC13", "site_name": "IST", "name": "DC13", "description": "",
        "status": "active", "vm_count": 1, "host_count": 1, "stats": {},
    }]
    pts = gv._build_globe_data(summaries)
    assert pts[0]["coloc_total_u"] == 0 and pts[0]["coloc_free_u"] == 0


# ---------------------------------------------------------------------------
# build_dc_info_card: Kolokasyon ring smoke tests (must never raise, even when
# colocation data is missing/unavailable).
# ---------------------------------------------------------------------------

_DC_DETAILS = {
    "meta": {"name": "DC13", "description": "Equinix", "location": "Istanbul"},
    "intel": {"cpu_cap": 100.0, "cpu_used": 40.0, "ram_cap": 100.0, "ram_used": 50.0,
              "storage_cap": 100.0, "storage_used": 30.0, "hosts": 2, "vms": 10},
    "power": {"hosts": 0, "lpar_count": 0},
    "energy": {"total_kw": 12.5},
    "platforms": {},
}


def _find_texts(node, out=None):
    """Recursively collect every string found anywhere in a Dash component
    tree — walks not just `children` but every set prop (e.g. RingProgress's
    `label`), since that's where the percentage Text actually lives."""
    if out is None:
        out = []
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, (list, tuple)):
        for c in node:
            _find_texts(c, out)
    elif hasattr(node, "_prop_names"):
        for prop in vars(node):
            if prop.startswith("_") or prop in ("available_properties", "available_wildcard_properties"):
                continue
            _find_texts(getattr(node, prop), out)
    return out


def test_build_dc_info_card_renders_kolokasyon_ring_with_data():
    # total=3616, used=2712, free=904 -> 75% used, distinct from the
    # CPU (40%) / RAM (50%) / Storage (30%) rings so the assertions below
    # can only be satisfied by the new Kolokasyon tile.
    with patch.object(gv.api, "get_dc_details", return_value=_DC_DETAILS), \
         patch.object(gv.api, "get_dc_racks_occupancy",
                      return_value={"racks": [], "summary": {"total_u": 3616, "used_u": 2712, "free_u": 904}}):
        card = gv.build_dc_info_card("DC13", {"preset": "7d"}, "IST")
    assert card is not None
    texts = _find_texts(card)
    assert "Kolokasyon" in texts
    assert "904U boş" in texts
    assert "75%" in texts

    # The stat grid grew from 3 rings + 1 text tile (cols=4) to 4 rings +
    # 1 text tile (cols=5) — the pre-existing Hosts/VMs/kW tile must survive.
    stat_grid = card.children[2]
    assert isinstance(stat_grid, gv.dmc.SimpleGrid)
    assert stat_grid.cols == 5
    assert len(stat_grid.children) == 5
    hosts_text = _find_texts(stat_grid.children[-1])
    assert any("Hosts" in t for t in hosts_text)
    assert any("VMs" in t for t in hosts_text)
    assert any("kW" in t for t in hosts_text)


def test_build_dc_info_card_renders_when_coloc_fetch_fails():
    """api_client raising must not break card rendering; ring defaults to 0."""
    with patch.object(gv.api, "get_dc_details", return_value=_DC_DETAILS), \
         patch.object(gv.api, "get_dc_racks_occupancy", side_effect=RuntimeError("boom")):
        card = gv.build_dc_info_card("DC13", {"preset": "7d"}, "IST")
    assert card is not None
    texts = _find_texts(card)
    assert "Kolokasyon" in texts
    assert "0U boş" in texts
    assert "0%" in texts


def test_build_dc_info_card_renders_when_coloc_summary_empty():
    """An empty (but non-raising) summary dict also defaults to 0, no ZeroDivisionError."""
    with patch.object(gv.api, "get_dc_details", return_value=_DC_DETAILS), \
         patch.object(gv.api, "get_dc_racks_occupancy", return_value={"racks": [], "summary": {}}):
        card = gv.build_dc_info_card("DC13", {"preset": "7d"}, "IST")
    assert card is not None
    texts = _find_texts(card)
    assert "Kolokasyon" in texts
    assert "0U boş" in texts
