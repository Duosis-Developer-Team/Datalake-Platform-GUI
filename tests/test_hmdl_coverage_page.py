"""Smoke test for HMDL Datalake Coverage page builder."""

from unittest.mock import patch

from src.pages.settings.integrations import hmdl_coverage as page


_EMPTY_TOPO = {"dcs": [], "totals": {"dcs": 0, "clusters": 0, "hosts": 0, "vms": 0, "running": 0}}

_TOPO = {
    "dcs": [{"name": "DC13", "counts": {"clusters": 1, "hosts": 1, "vms": 2, "running": 1},
             "clusters": [{"name": "CL1", "counts": {"hosts": 1, "vms": 2, "running": 1},
               "hosts": [{"name": "esx1", "counts": {"vms": 2, "running": 1},
                 "vms": [{"name": "web-01", "os_family": "windows", "power_state": "poweredOn"}]}]}]}],
    "totals": {"dcs": 1, "clusters": 1, "hosts": 1, "vms": 2, "running": 1},
}


@patch("src.pages.settings.integrations.hmdl_coverage.api.get_vm_topology", return_value=_EMPTY_TOPO)
@patch("src.pages.settings.integrations.hmdl_coverage.api.get_hmdl_coverage")
@patch("src.pages.settings.integrations.hmdl_coverage.api.get_hmdl_locations")
def test_hmdl_coverage_page_builds(mock_locations, mock_coverage, mock_topo):
    mock_locations.return_value = {
        "items": [{"dc_code": "DC13", "environment_status": "connected"}],
    }
    mock_coverage.return_value = {
        "summary": {"cluster": {"all": {"total": 0, "collected": 0, "missing": 0, "live": 0}}},
        "clusters": [],
        "ibm_hosts": [],
        "locations": ["DC13"],
    }
    layout = page.build_layout(search="?dc=DC13")
    assert layout is not None


@patch("src.pages.settings.integrations.hmdl_coverage.api.get_vm_topology", return_value=_TOPO)
@patch("src.pages.settings.integrations.hmdl_coverage.api.get_hmdl_coverage", return_value={})
@patch("src.pages.settings.integrations.hmdl_coverage.api.get_hmdl_locations", return_value={"items": []})
def test_coverage_page_has_topology_section(mock_locations, mock_coverage, mock_topo):
    text = str(page.build_layout())
    assert "Envanter Topolojisi" in text
    assert "DC13" in text and "esx1" in text


LOCATIONS = [
    {"dc_code": "AZ11", "environment_status": "connected"},
    {"dc_code": "DC13", "environment_status": "connected"},
]


def test_parse_dc_reads_selected_dc():
    assert page._parse_dc("?dc=DC13") == "DC13"
    assert page._parse_dc("?dc=dc13") == "DC13"


def test_parse_dc_keeps_all_locations_selected():
    """"All locations" must stay all — not collapse to the first DC (AZ11)."""
    assert page._parse_dc("") == ""
    assert page._parse_dc(None) == ""
    assert page._parse_dc("?dc=") == ""


@patch("src.pages.settings.integrations.hmdl_coverage.api.get_vm_topology", return_value=_EMPTY_TOPO)
@patch("src.pages.settings.integrations.hmdl_coverage.api.get_hmdl_coverage")
@patch("src.pages.settings.integrations.hmdl_coverage.api.get_hmdl_locations")
def test_all_locations_queries_every_dc(mock_locations, mock_coverage, mock_topo):
    mock_locations.return_value = {"items": LOCATIONS}
    mock_coverage.return_value = {
        "summary": {"cluster": {"all": {"total": 0, "collected": 0, "missing": 0, "live": 0}}},
        "clusters": [],
        "ibm_hosts": [],
        "locations": ["AZ11", "DC13"],
    }

    page.build_layout(search="")

    mock_coverage.assert_called_once_with(dc=None)
