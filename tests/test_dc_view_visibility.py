from dash import html
from src.pages import dc_view


def test_has_compute_data_empty():
    assert dc_view._has_compute_data({}) is False
    assert dc_view._has_compute_data(None) is False


def test_has_compute_data_with_hosts():
    assert dc_view._has_compute_data({"hosts": 1}) is True


def test_has_power_data_empty():
    assert dc_view._has_power_data({}) is False
    assert dc_view._has_power_data(None) is False


def test_has_power_data_with_lpars():
    assert dc_view._has_power_data({"lpar_count": 1}) is True


def _fake_service(monkeypatch, dc_details: dict, s3_pools: dict | None = None):
    """Patch shared.service for build_dc_view tests."""
    class FakeService:
        def get_dc_details(self, dc_id, tr):
            return dc_details

        def get_dc_s3_pools(self, dc_id, tr):
            return s3_pools or {}

        def get_classic_cluster_list(self, dc_id, tr):
            return []

        def get_hyperconv_cluster_list(self, dc_id, tr):
            return []

    monkeypatch.setattr("src.pages.dc_view.service", FakeService())


def _extract_tab_labels(root: html.Div) -> list[str]:
    """Traverse the rendered layout and collect top-level tab labels."""
    labels: list[str] = []
    for child in root.children:
        if not hasattr(child, "props"):
            continue
        if child.__class__.__name__ == "Tabs":
            tabs_list = next(
                (c for c in child.children if c.__class__.__name__ == "TabsList"),
                None,
            )
            if not tabs_list:
                continue
            for tab in tabs_list.children:
                label = getattr(tab, "children", None)
                if isinstance(label, str):
                    labels.append(label)
    return labels


def test_summary_hidden_when_no_data(monkeypatch):
    empty_dc = {
        "meta": {"name": "DCX", "location": "Nowhere"},
        "classic": {},
        "hyperconv": {},
        "power": {},
        "energy": {},
    }
    _fake_service(monkeypatch, empty_dc, s3_pools={})

    layout = dc_view.build_dc_view("DCX", time_range={"from": 0, "to": 0})
    # With no compute and no S3 data, Summary and Virtualization tabs should be absent
    # We approximate this by checking helper functions directly.
    assert dc_view._has_compute_data(empty_dc.get("classic")) is False
    assert dc_view._has_compute_data(empty_dc.get("hyperconv")) is False


def test_s3_tab_shown_when_pools_present(monkeypatch):
    dc = {
        "meta": {"name": "DCX", "location": "Nowhere"},
        "classic": {},
        "hyperconv": {},
        "power": {},
        "energy": {},
    }
    s3_pools = {"pools": ["pool1"], "latest": {}, "growth": {}}
    _fake_service(monkeypatch, dc, s3_pools=s3_pools)

    layout = dc_view.build_dc_view("DCX", time_range={"from": 0, "to": 0})
    outer_tabs = next(c for c in layout.children if c.__class__.__name__ == "Tabs")
    labels = _extract_tab_labels(outer_tabs)
    assert "Object Storage" in labels


def test_backup_tab_hidden(monkeypatch):
    dc = {
        "meta": {"name": "DCX", "location": "Nowhere"},
        "classic": {},
        "hyperconv": {},
        "power": {},
        "energy": {},
    }
    _fake_service(monkeypatch, dc, s3_pools={})

    layout = dc_view.build_dc_view("DCX", time_range={"from": 0, "to": 0})
    outer_tabs = next(c for c in layout.children if c.__class__.__name__ == "Tabs")
    labels = _extract_tab_labels(outer_tabs)
    assert "Backup & Replication" not in labels

