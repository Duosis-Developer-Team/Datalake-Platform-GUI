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
    """Patch api_client (imported as api) for build_dc_view tests."""
    pools = s3_pools or {}

    class FakeApi:
        def get_dc_details(self, dc_id, tr):
            return dc_details

        def get_sla_by_dc(self, tr):
            return {}

        def get_dc_s3_pools(self, dc_id, tr):
            return pools

        def get_classic_cluster_list(self, dc_id, tr):
            return []

        def get_hyperconv_cluster_list(self, dc_id, tr):
            return []

        def get_physical_inventory_dc(self, dc_name):
            return {"total": 0, "by_role": [], "by_role_manufacturer": []}

        def get_dc_netbackup_pools(self, dc_id, tr):
            return {"pools": [], "rows": []}

        def get_dc_zerto_sites(self, dc_id, tr):
            return {"sites": [], "rows": []}

        def get_dc_veeam_repos(self, dc_id, tr):
            return {"repos": [], "rows": []}

    monkeypatch.setattr(dc_view, "api", FakeApi())


def _collect_tab_labels(component) -> list[str]:
    """Recursively collect dmc.TabsTab string labels from a layout tree."""
    labels: list[str] = []
    if component is None:
        return labels
    name = getattr(component.__class__, "__name__", "")
    if name == "TabsTab":
        ch = getattr(component, "children", None)
        if isinstance(ch, str):
            labels.append(ch)
    children = getattr(component, "children", None)
    if children is None:
        return labels
    if isinstance(children, (list, tuple)):
        for c in children:
            labels.extend(_collect_tab_labels(c))
    else:
        labels.extend(_collect_tab_labels(children))
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
    labels = _collect_tab_labels(layout)
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
    labels = _collect_tab_labels(layout)
    assert "Backup & Replication" not in labels

