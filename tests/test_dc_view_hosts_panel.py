"""Tests for the DC view Hosts panel (collapsible, cluster-filtered) and the
storage sellable range display in the inline sellable KPI card."""
from __future__ import annotations

import dash_mantine_components as dmc

from src.pages import dc_view


def _walk(component):
    yield component
    children = getattr(component, "children", None)
    if children is None:
        return
    if isinstance(children, (list, tuple)):
        for c in children:
            if c is not None:
                yield from _walk(c)
    else:
        yield from _walk(children)


def _ids(component) -> set[str]:
    return {getattr(c, "id") for c in _walk(component) if getattr(c, "id", None)}


def _texts(component) -> str:
    out = []
    for c in _walk(component):
        ch = getattr(c, "children", None)
        if isinstance(ch, str):
            out.append(ch)
    return " ".join(out)


_SAMPLE_HOST = {
    "host": "hv1dc13.blt.vc",
    "cluster": "DC13-KM-CLS-1",
    "vm_count": 14,
    "cpu_cap_ghz": 224.0,
    "cpu_used_ghz": 48.0,
    "cpu_used_pct": 21.4,
    "cpu_alloc_ghz": 120.0,
    "cpu_alloc_pct": 53.6,
    "mem_cap_gb": 6143.7,
    "mem_used_gb": 2221.3,
    "mem_used_pct": 36.2,
    "mem_alloc_gb": 4100.0,
    "mem_alloc_pct": 66.7,
}


# --------------------------------------------------------------- shell / RBAC


def test_hosts_panel_shell_contains_expected_ids():
    shell = dc_view._build_hosts_panel_shell("classic", "blue")
    ids = _ids(shell)
    assert "hosts-collapse-classic" in ids
    assert "hosts-panel-classic" in ids
    assert "hosts-count-classic" in ids
    assert "hosts-toggle-classic" in ids


def test_hosts_panel_shell_collapse_starts_closed():
    shell = dc_view._build_hosts_panel_shell("hyperconv", "teal")
    collapse = next(c for c in _walk(shell) if getattr(c, "id", None) == "hosts-collapse-hyperconv")
    assert getattr(collapse, "in") is False


def test_hosts_permission_code_in_catalog():
    from src.auth.permission_catalog import build_default_permission_roots

    def _codes(nodes):
        for n in nodes:
            yield n.code
            yield from _codes(getattr(n, "children", None) or [])

    codes = set(_codes(build_default_permission_roots()))
    assert "sub:dc_view:virt:hosts" in codes


# ------------------------------------------------------------------- content


def test_hosts_panel_content_renders_host_card():
    content = dc_view._build_hosts_panel_content({"hosts": [_SAMPLE_HOST], "host_count": 1})
    text = _texts(content)
    assert "hv1dc13.blt.vc" in text
    badges = [c for c in _walk(content) if c.__class__.__name__ == "Badge"]
    badge_texts = {getattr(b, "children", "") for b in badges}
    assert "DC13-KM-CLS-1" in badge_texts
    assert "14 VM" in badge_texts


def test_hosts_panel_content_empty_shows_alert():
    content = dc_view._build_hosts_panel_content({"hosts": [], "host_count": 0})
    assert content.__class__.__name__ == "Alert"


def test_host_card_shows_pct_and_numeric_values():
    card = dc_view._host_card(_SAMPLE_HOST, "blue")
    text = _texts(card)
    assert "Util %21.4" in text          # CPU used pct
    assert "48.0 / 224.0 GHz" in text
    assert "%36.2" in text          # RAM used pct
    assert "Tahsis" in text         # sales allocation line


def test_host_card_hci_storage_row_only_when_present():
    no_disk = _texts(dc_view._host_card(_SAMPLE_HOST, "teal"))
    assert "Storage" not in no_disk

    hci_host = {**_SAMPLE_HOST, "stor_cap_gb": 40960.0, "stor_used_host_gb": 10240.0}
    with_disk = _texts(dc_view._host_card(hci_host, "teal"))
    assert "Storage" in with_disk


def test_host_card_km_storage_and_constraint_tags():
    km_host = {
        **_SAMPLE_HOST,
        "stor_cap_gb": 2048.0,
        "stor_used_gb": 512.0,
        "stor_provisioned_gb": 800.0,
        "stor_free_gb": 1200.0,
        "stor_exclusive_free_gb": 400.0,
        "datastore_mounts": [{"shared": True, "free_gb": 800.0}],
        "constraint_tags": ["40 GB RAM ratio-bound", "600 GB Storage ratio-bound"],
        "sellable_sales_n_min": 4.0,
        "sellable_sales_n_max": 8.0,
        "sellable_peak_n_min": 6.0,
        "sellable_peak_n_max": 10.0,
    }
    text = _texts(dc_view._host_card(km_host, "blue"))
    assert "Storage" in text
    assert "shared datastore mount" in text
    assert "40 GB RAM ratio-bound" in text
    assert "Sellable (sales alloc): 4.0 – 8.0" in text
    assert "Sellable (peak util): 6.0 – 10.0" in text


# --------------------------------------------------------- backing badge


def test_ds_backing_badge_labels():
    ibm = dc_view._ds_backing_badge("ibm")
    intel = dc_view._ds_backing_badge("intel")
    default = dc_view._ds_backing_badge(None)
    assert ibm.children == "IBM"
    assert intel.children == "INTEL"
    assert default.children == "INTEL"


# ----------------------------------------------- sellable KPI range display


def _sellable_panels_with_range():
    base = {
        "family": "virt_classic",
        "dc_code": "DC13",
        "threshold_pct": 80.0,
        "ratio_bound": False,
        "has_infra_source": True,
        "has_price": True,
        "notes": [],
    }
    return [
        {**base, "panel_key": "virt_classic_cpu", "resource_kind": "cpu", "display_unit": "vCPU",
         "total": 100.0, "allocated": 40.0, "sellable_raw": 40.0, "sellable_constrained": 30.0,
         "unit_price_tl": 10.0, "potential_tl": 300.0},
        {**base, "panel_key": "virt_classic_ram", "resource_kind": "ram", "display_unit": "GB",
         "total": 800.0, "allocated": 200.0, "sellable_raw": 440.0, "sellable_constrained": 120.0,
         "unit_price_tl": 1.0, "potential_tl": 120.0},
        {**base, "panel_key": "virt_classic_storage", "resource_kind": "storage", "display_unit": "TB",
         "total": 500.0, "allocated": 300.0, "sellable_raw": 140.0, "sellable_constrained": 100.0,
         "unit_price_tl": 2.0, "potential_tl": 200.0,
         "sellable_min": 100.0, "sellable_max": 140.0,
         "potential_tl_min": 200.0, "potential_tl_max": 280.0},
    ]


def test_sellable_inline_kpi_renders_storage_range(monkeypatch):
    class FakeApi:
        @staticmethod
        def get_sellable_by_panel(dc_code="*", family=None, clusters=None):
            return _sellable_panels_with_range()

    monkeypatch.setattr(dc_view, "api", FakeApi())
    card = dc_view._build_sellable_inline_kpi("DC13", "virt_classic", "Test", color="blue")
    text = _texts(card)
    # Range "min – max" must be visible for storage and total potential.
    assert "100 – 140 TB" in text
    assert "paylaşımlı" in text.lower()


def test_sellable_inline_kpi_single_value_without_range(monkeypatch):
    panels = _sellable_panels_with_range()
    for p in panels:
        p.pop("sellable_min", None)
        p.pop("sellable_max", None)
        p.pop("potential_tl_min", None)
        p.pop("potential_tl_max", None)

    class FakeApi:
        @staticmethod
        def get_sellable_by_panel(dc_code="*", family=None, clusters=None):
            return panels

    monkeypatch.setattr(dc_view, "api", FakeApi())
    card = dc_view._build_sellable_inline_kpi("DC13", "virt_classic", "Test", color="blue")
    text = _texts(card)
    assert "100 TB" in text
    assert "100 – 140" not in text


# ------------------------------------------------------- dmc API smoke check


def test_dmc_collapse_supports_in_prop():
    """Guards against dash-mantine-components API drift for Collapse."""
    collapse = dmc.Collapse(id="x", **{"in": False}, children=[])
    assert getattr(collapse, "in") is False
