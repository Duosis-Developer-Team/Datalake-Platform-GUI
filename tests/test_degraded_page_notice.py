"""P0-4, part 2 (UI): a page that got no data says so instead of drawing zeros.

api_client now marks the payloads it fabricates (see
test_degraded_fallback_marker.py). This file pins the other half: the pages have
to *look*, and having looked, must not render the fabricated numbers anyway.

The negative tests matter more than the positive ones. A notice that appears when
the backend is merely slow, or when a DC legitimately has nothing in it, would be
a worse regression than the zeros it replaces — so every page is also tested for
building normally on an ordinary payload.
"""
from __future__ import annotations

from unittest.mock import patch

import dash
import pytest

from src.components.degraded_notice import DEGRADED_NOTICE_ID, build_degraded_notice
from src.services import api_client as api


def _flat(component) -> str:
    return repr(component)


# --- the component -----------------------------------------------------------

def test_the_notice_identifies_itself():
    assert DEGRADED_NOTICE_ID in _flat(build_degraded_notice())


def _visible_text(component) -> str:
    """Every string a reader actually sees, ignoring style props and icon names."""
    import dash_mantine_components as dmc

    out: list[str] = []

    def walk(node):
        if isinstance(node, str):
            return
        if isinstance(node, (list, tuple)):
            for child in node:
                walk(child)
            return
        children = getattr(node, "children", None)
        if isinstance(node, dmc.Text) and isinstance(children, str):
            out.append(children)
            return
        if children is not None:
            walk(children)

    walk(component)
    return " ".join(out)


def test_the_notice_asks_for_a_retry_rather_than_reporting_a_number():
    """Any digit on this card reads as a measurement, which is the failure mode
    the card exists to avoid — so the copy carries none."""
    text = _visible_text(build_degraded_notice())

    assert "Veri alınamadı" in text
    assert "tekrar deneyin" in text
    assert not any(ch.isdigit() for ch in text), f"figure in the degraded copy: {text!r}"


def test_the_notice_can_name_what_failed():
    assert "Data Center DC13" in _flat(build_degraded_notice("Data Center DC13"))


# --- Overview ----------------------------------------------------------------

def test_overview_shows_the_notice_instead_of_zero_kpis():
    from src.pages import home

    with patch.object(api, "get_global_dashboard", return_value=api._degraded_fallback(api._EMPTY_DASHBOARD)):
        with patch.object(api, "get_all_datacenters_summary") as summaries:
            out = home.build_overview({"preset": "7d"})

    assert DEGRADED_NOTICE_ID in _flat(out)
    assert "Total VMs" not in _flat(out), "the zero KPI strip is the thing being replaced"
    summaries.assert_not_called(), "no reason to keep fetching for a page that will not render"


def test_overview_builds_normally_when_the_payload_is_real():
    from src.pages import home

    with patch.object(api, "get_global_dashboard", return_value=dict(api._EMPTY_DASHBOARD)):
        out = home.build_overview({"preset": "7d"})

    assert DEGRADED_NOTICE_ID not in _flat(out)
    assert "Total VMs" in _flat(out), (
        "an all-zero payload the backend actually returned is data, not a failure"
    )


# --- Data Centers ------------------------------------------------------------

def test_datacenters_shows_the_notice_instead_of_an_empty_grid():
    from src.pages import datacenters

    with patch.object(api, "get_all_datacenters_summary", return_value=api._DegradedList()):
        with patch.object(api, "get_sla_by_dc") as sla:
            out = datacenters.build_datacenters({"preset": "7d"})

    assert DEGRADED_NOTICE_ID in _flat(out)
    sla.assert_not_called()


def test_datacenters_poll_holds_the_screen_rather_than_blanking_it():
    """The refresh callback has no error slot to render into, so the honest move
    is to leave the last good render on screen and try again next tick."""
    from src.pages import datacenters

    with patch.object(api, "get_all_datacenters_summary", return_value=api._DegradedList()):
        with patch.object(datacenters, "is_virt_cache_warming", return_value=False):
            with patch.object(
                datacenters, "resolve_virt_sellable_for_dcs", return_value={"loading": False}
            ):
                with pytest.raises(dash.exceptions.PreventUpdate):
                    datacenters.poll_virt_sellable_refresh(
                        1, {"loading": True, "dc_ids": ["DC13"]}, {"preset": "7d"}
                    )


# --- DC View -----------------------------------------------------------------

def test_dc_view_shows_the_notice_instead_of_an_empty_datacenter():
    from src.pages import dc_view

    degraded = api._degraded_fallback(api._EMPTY_DC_DETAIL)
    with patch.object(api, "get_dc_details", return_value=degraded):
        with patch.object(api, "get_sla_by_dc", return_value={}):
            out = dc_view.build_dc_view("DC13", {"preset": "7d"}, eager_tabs=frozenset({"summary"}))

    flat = _flat(out)
    assert DEGRADED_NOTICE_ID in flat
    assert "DC13" in flat, "the notice names the DC that failed"


# --- Unmapped Resources ------------------------------------------------------

def test_unmapped_shows_the_notice_instead_of_zero_gaps():
    from src.pages import unmapped_resources

    degraded = api._degraded_fallback(api._EMPTY_UNMAPPED)
    with patch.object(api, "get_unmapped_resources", return_value=degraded):
        out = unmapped_resources.build_body({"preset": "7d"})

    assert DEGRADED_NOTICE_ID in _flat(out)


def test_unmapped_builds_normally_when_there_is_genuinely_nothing_to_map():
    """The most likely false positive on this page: a healthy platform with no
    alias gaps returns exactly the empty payload, and must still render tabs."""
    from src.pages import unmapped_resources

    clean = {"rows": [], "total": 0, "alias_gap_count": 0, "orphan_count": 0, "ambiguous_count": 0}
    with patch.object(api, "get_unmapped_resources", return_value=clean):
        out = unmapped_resources.build_body({"preset": "7d"})

    assert DEGRADED_NOTICE_ID not in _flat(out)


# --- Customer View -----------------------------------------------------------

def test_customer_view_shows_the_notice_in_every_section():
    """Sections are rendered into separate tabs, so a notice in one is invisible
    from the others. All of them carry it or the operator finds the empty tab
    first and believes it."""
    from src.pages import customer_view

    degraded = api._degraded_fallback(api._EMPTY_CUSTOMER)
    with patch.object(api, "get_customer_resources", return_value=degraded):
        out = customer_view._customer_content("ACME", {"preset": "7d"})

    for perspective in ("manager", "customer"):
        for section in ("summary", "virt", "backup"):
            assert DEGRADED_NOTICE_ID in _flat(out[perspective][section]), (
                f"{perspective}/{section} rendered without the notice"
            )
    assert out["customer_name"] == "ACME"
