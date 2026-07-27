"""DC View › Virtualization › Lisanslı OS.

Licensed OS moved out of the sidebar and into the DC it describes: a licence gap
is a fact about one datacenter's estate, not a standalone report. The tab shows
all three architectures side by side (that comparison is the point), and each
architecture sub-tab also carries its own card.
"""
from __future__ import annotations

from dash import html

from src.pages.dc_view import build_licensed_os_panel, build_licensed_os_card

_PAYLOAD = {
    "dc_code": "DC13",
    "architectures": {
        "classic": {
            "instances": 1863,
            "families": {"windows": 951, "rhel": 152, "suse": 81, "free": 400, "unknown": 279},
        },
        "hyperconverged": {
            "instances": 5214,
            "families": {"windows": 2412, "rhel": 160, "suse": 52, "free": 1800, "unknown": 790},
        },
        "pure_nutanix": {"instances": 1483, "no_os_telemetry": 1483},
        "power": {
            "instances": 335,
            "families": {"windows": 0, "rhel": 0, "suse": 300, "free": 0, "unknown": 35},
        },
    },
    "totals": {
        "families": {"windows": 3363, "rhel": 312, "suse": 433, "free": 2200, "unknown": 1104},
        "licensed": 4108,
        "instances": 7412,
        "no_os_telemetry": 1483,
    },
    "sold": {"families": {"windows": 1294, "rhel": 0, "suse": 6}, "method": "vm_footprint_share"},
}


def _text(component) -> str:
    return str(component)


def test_panel_shows_every_architecture_side_by_side():
    rendered = _text(build_licensed_os_panel(_PAYLOAD))
    for label in ("Klasik Mimari", "Hyperconverged", "Power", "Pure Nutanix"):
        assert label in rendered


def test_panel_shows_detected_counts_per_family():
    rendered = _text(build_licensed_os_panel(_PAYLOAD))
    assert "951" in rendered      # classic Windows
    assert "2,412" in rendered    # hyperconverged Windows
    assert "300" in rendered      # power SUSE


def test_pure_nutanix_is_reported_as_missing_telemetry_not_as_zero_licences():
    """1,483 AHV guests have no guest OS in any source. Rendering them as
    '0 Windows' would read as a finding; it is missing data."""
    rendered = _text(build_licensed_os_panel(_PAYLOAD))
    assert "1,483" in rendered
    assert "telemetri" in rendered.lower() or "telemetry" in rendered.lower()


def test_sold_vs_detected_is_shown_and_labelled_as_an_estimate():
    """CRM sells per customer, not per DC — the DC figure is an allocation."""
    rendered = _text(build_licensed_os_panel(_PAYLOAD))
    assert "1,294" in rendered
    assert "tahmin" in rendered.lower() or "estimate" in rendered.lower()


def test_missing_sales_resolution_says_so_instead_of_showing_zero():
    payload = {**_PAYLOAD, "sold": None}
    rendered = _text(build_licensed_os_panel(payload))
    assert "1,294" not in rendered
    # A DC that cannot resolve CRM must not claim zero licences were sold.
    assert "0 sold" not in rendered.lower()


def test_per_architecture_card_renders_that_architecture_only():
    card = _text(build_licensed_os_card(_PAYLOAD, "classic"))
    assert "951" in card
    assert "2,412" not in card


def test_power_card_uses_the_lpar_wording():
    card = _text(build_licensed_os_card(_PAYLOAD, "power"))
    assert "300" in card


def test_pure_nutanix_card_states_the_gap():
    card = _text(build_licensed_os_card(_PAYLOAD, "pure_nutanix")).lower()
    assert "telemetri" in card or "telemetry" in card


def test_empty_payload_renders_without_raising():
    for build in (
        lambda: build_licensed_os_panel({}),
        lambda: build_licensed_os_panel(None),
        lambda: build_licensed_os_card({}, "classic"),
        lambda: build_licensed_os_card(None, "power"),
    ):
        assert isinstance(build(), (html.Div, object))


def test_unknown_architecture_key_does_not_raise():
    assert build_licensed_os_card(_PAYLOAD, "nope") is not None
