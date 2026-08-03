"""P0-5: Overview must not report two different totals for the same thing.

The KPI strip read /dashboard/overview and the treemap and DC table read
/datacenters/summary. Two endpoints, two cache keys, two independent ages — so
whichever refreshed last won, and the page showed 16.903 VMs at the top and
16.892 in the chart directly beneath it. Both were real numbers, seconds apart.
Neither was wrong; the page was.

An operator cannot act on that. Which figure goes in the capacity report? The
answer has to be "there is only one", so the counts that appear in both places
are now derived once, from the per-DC rows the rest of the page already uses.

What stays on /dashboard/overview: platform count and energy, which the summary
rows do not carry. Those still age on their own key — narrower than the bug
being fixed, and called out here so the remaining gap is on the record rather
than assumed closed.
"""
from __future__ import annotations

from unittest.mock import patch

from src.services import api_client as api


def _summary_row(name: str, hosts: int, vms: int) -> dict:
    """A row shaped the way the DC table indexes it — bracket access, not .get."""
    return {
        "id": name,
        "name": name,
        "location": "Istanbul",
        "description": "",
        "platform_count": 3,
        "host_count": hosts,
        "vm_count": vms,
        "stats": {"used_cpu_pct": 10.0, "used_ram_pct": 20.0, "arch_usage": {}},
    }


def _overview_payload(dc_count: int, hosts: int, vms: int) -> dict:
    payload = {k: dict(v) if isinstance(v, dict) else v for k, v in api._EMPTY_DASHBOARD.items()}
    payload["overview"] = dict(payload["overview"])
    payload["overview"].update(
        {"dc_count": dc_count, "total_hosts": hosts, "total_vms": vms,
         "total_platforms": 7, "total_energy_kw": 123.0}
    )
    return payload


def _render(summaries: list[dict], overview: dict) -> str:
    from src.pages import home

    with patch.object(api, "get_all_datacenters_summary", return_value=summaries):
        with patch.object(api, "get_global_dashboard", return_value=overview):
            return repr(home.build_overview({"preset": "7d"}))


def test_kpi_totals_come_from_the_same_rows_as_the_treemap():
    """The reproduction: the two endpoints disagree, and the page must not.

    The overview payload here claims 16.903 VMs while the per-DC rows sum to
    16.892 — the exact split measured in production.
    """
    summaries = [_summary_row("DC13", 900, 16_000), _summary_row("DC14", 120, 892)]
    flat = _render(summaries, _overview_payload(dc_count=9, hosts=9_999, vms=16_903))

    assert "16,892" in flat, "KPI must show the sum of the rows the chart draws"
    assert "16,903" not in flat, "the second endpoint's total must not appear anywhere"


def test_host_and_dc_counts_are_derived_too():
    summaries = [_summary_row("DC13", 900, 16_000), _summary_row("DC14", 120, 892)]
    flat = _render(summaries, _overview_payload(dc_count=9, hosts=9_999, vms=16_903))

    assert "1,020" in flat, "hosts summed from the same rows"
    assert "9,999" not in flat
    # dc_count is the row count, not the other endpoint's 9
    assert ">'2'" in flat or "'2'" in flat


def test_fields_with_no_per_dc_equivalent_still_come_from_the_overview_endpoint():
    """Platforms and energy are not in the summary rows. Deriving them would mean
    inventing them, which is the failure mode this whole wave is about."""
    summaries = [_summary_row("DC13", 900, 16_000)]
    flat = _render(summaries, _overview_payload(dc_count=1, hosts=900, vms=16_000))

    assert "123 kW" in flat
    assert "7" in flat


def test_missing_counts_in_a_row_contribute_zero_rather_than_raising():
    """Summary rows are backend output, not a guaranteed contract, and this sum
    sits on the render path.

    Tested against the derivation rather than a full render: the DC table below
    indexes the same rows with brackets and would raise on this input regardless.
    That fragility predates P0-5 and is not what this change is about — but the
    totals it introduces must not add a second way to fail.
    """
    from src.pages import home

    dc_count, hosts, vms = home._overview_totals(
        [_summary_row("DC13", 900, 16_000), {"id": "DC14", "name": "DC14"}]
    )

    assert (dc_count, hosts, vms) == (2, 900, 16_000)


def test_totals_of_no_rows_are_zero():
    from src.pages import home

    assert home._overview_totals([]) == (0, 0, 0)


def test_empty_summaries_render_zero_rather_than_the_other_endpoints_number():
    """A measured-empty list is an answer (the degraded case returns earlier, see
    test_degraded_page_notice). Zero is then the honest total, and taking it from
    the other endpoint instead would resurrect the disagreement."""
    flat = _render([], _overview_payload(dc_count=9, hosts=9_999, vms=16_903))

    assert "16,903" not in flat
    assert "9,999" not in flat
