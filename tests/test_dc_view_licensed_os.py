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


def test_unclassified_os_strings_are_listed_for_manual_review():
    """This list used to live on the standalone /licensed-os page. It is how the
    classifier's rule table gets extended, so it moved here rather than dying with
    the page."""
    payload = {**_PAYLOAD, "unknown_samples": ["Other Linux (64-bit)", "Other (64-bit)"]}
    rendered = _text(build_licensed_os_panel(payload))
    assert "Other Linux (64-bit)" in rendered
    assert "Other (64-bit)" in rendered


def test_no_review_block_when_everything_was_classified():
    rendered = _text(build_licensed_os_panel({**_PAYLOAD, "unknown_samples": []}))
    assert "manual review" not in rendered.lower()
    assert "sınıflandırılamayan" not in rendered.lower()


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


# --- powered-on toggle + the AHV note ---------------------------------------

def test_panel_offers_an_all_vs_running_toggle():
    rendered = _text(build_licensed_os_panel(_PAYLOAD))
    assert "dc-licensed-os-scope" in rendered


def test_running_scope_renders_the_running_tally():
    from src.pages.dc_view import build_licensed_os_body

    payload = {
        **_PAYLOAD,
        "totals": {**_PAYLOAD["totals"], "families_running": {"windows": 2900, "rhel": 300, "suse": 400}},
    }
    assert "2,900" in _text(build_licensed_os_body(payload, "running"))
    assert "3,363" in _text(build_licensed_os_body(payload, "all"))


def test_ahv_note_explains_the_cause_and_the_fix_not_just_the_absence():
    """"No telemetry" alone reads as a platform bug. It is not: Nutanix does not
    report guest OS for these VMs because NGT is not installed on them, which is a
    sysadmin action, not a code change. The screen has to say so or the finding
    gets filed against the wrong team."""
    rendered = _text(build_licensed_os_panel(_PAYLOAD))
    assert "NGT" in rendered
    assert "Nutanix Guest Tools" in rendered


def test_ahv_note_is_absent_when_there_are_no_such_guests():
    payload = {
        **_PAYLOAD,
        "architectures": {**_PAYLOAD["architectures"], "pure_nutanix": {"instances": 0, "no_os_telemetry": 0}},
        "totals": {**_PAYLOAD["totals"], "no_os_telemetry": 0},
    }
    assert "NGT" not in _text(build_licensed_os_panel(payload))


def test_panel_says_how_the_crm_match_was_made():
    """Some tenants are hand-mapped, most are matched by name. A reader has to be
    able to tell a recorded decision from a guess."""
    payload = {**_PAYLOAD, "sold": {
        "families": {"windows": 1294, "rhel": 0, "suse": 6},
        "method": "vm_footprint_share",
        "tenant_match": {"alias": 12, "name": 340},
    }}
    rendered = _text(build_licensed_os_panel(payload)).lower()
    assert "12" in rendered and "340" in rendered
    assert "isim" in rendered      # name-matched, i.e. a guess


def test_all_alias_matches_are_not_presented_as_guesses():
    payload = {**_PAYLOAD, "sold": {
        "families": {"windows": 1294, "rhel": 0, "suse": 6},
        "method": "vm_footprint_share",
        "tenant_match": {"alias": 40, "name": 0},
    }}
    rendered = _text(build_licensed_os_panel(payload)).lower()
    assert "isim tahmini" not in rendered


# --- column order + TL -------------------------------------------------------

def _headers(component) -> list[str]:
    """The header strings of the summary card, in render order."""
    out: list[str] = []
    text = _text(component)
    for label in ("Hizmet", "Satılan (tahmini)", "Kullanılan", "Çalışan", "Ekstra Kullanım", "Tahmini Kayıp"):
        idx = text.find(f"children='{label}'")
        if idx >= 0:
            out.append((idx, label))
    return [lbl for _i, lbl in sorted(out)]


def test_columns_follow_the_requested_order():
    """Sold before Used, as in the agreed layout — a reader compares entitlement
    to usage left-to-right."""
    order = _headers(build_licensed_os_panel(_PAYLOAD))
    assert order[:4] == ["Hizmet", "Satılan (tahmini)", "Kullanılan", "Ekstra Kullanım"]


def test_a_tl_column_prices_the_gap():
    payload = {**_PAYLOAD, "prices": {"windows": 446.63, "rhel": 0.0, "suse": 5238.76}}
    rendered = _text(build_licensed_os_panel(payload))
    assert "Tahmini Kayıp" in rendered
    # 3,363 detected - 1,294 attributed = 2,069 extra x 446.63 TL
    assert "924,077" in rendered or "924.077" in rendered


def test_no_tl_column_without_prices():
    assert "Tahmini Kayıp" not in _text(build_licensed_os_panel(_PAYLOAD))


def test_a_family_with_no_known_price_shows_a_dash_not_zero_tl():
    """RHEL has never been sold, so there is no price anywhere. A 0 TL cell would
    read as 'no money at stake' when the truth is 'we cannot price it'."""
    payload = {**_PAYLOAD, "prices": {"windows": 446.63, "rhel": 0.0, "suse": 5238.76}}
    rendered = _text(build_licensed_os_panel(payload))
    assert "0 TL" not in rendered
