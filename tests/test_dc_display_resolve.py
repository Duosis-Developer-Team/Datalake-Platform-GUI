"""Tests for datacenter display name resolution from summary cache."""


def test_resolve_dc_display_from_summary():
    from unittest.mock import patch

    from src.utils.dc_display import resolve_dc_display_from_summary

    summary = [
        {
            "id": "DC13",
            "name": "DC13",
            "description": "Equinox IL2 DC",
            "location": "Istanbul",
        },
    ]
    with patch("src.services.api_client.get_all_datacenters_summary", return_value=summary):
        display, loc = resolve_dc_display_from_summary("DC13", {"preset": "7d"})

    assert display == "DC13 - Equinox IL2 DC"
    assert loc == "Istanbul"
