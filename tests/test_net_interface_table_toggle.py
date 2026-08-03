"""The interface table waits for a switch instead of loading with the page.

DC View's Network tab draws a handful of gauges and, underneath them, the
Interface Utilization Table. On a real DC that table is the expensive part —
DC13 has ~4,060 interfaces behind it — and until now it was fetched twice
before the operator had even scrolled to it: once while the page was being
assembled server-side, and again by update_net_interface_table, which has no
prevent_initial_call and so runs on first render.

Nobody opens the Network tab for the table. They open it for the gauges. So
the table is now behind a switch, off by default: the page costs what the
gauges cost, and the table is fetched the moment someone says they want it.
"""

from __future__ import annotations

from unittest.mock import patch

from src.pages import dc_view


def _find_by_id(node, target_id):
    if node is None:
        return None
    if getattr(node, "id", None) == target_id:
        return node
    children = getattr(node, "children", None)
    if isinstance(children, (list, tuple)):
        for c in children:
            found = _find_by_id(c, target_id)
            if found is not None:
                return found
    elif children is not None:
        return _find_by_id(children, target_id)
    return None


def _page(interface_table=None):
    return dc_view._build_network_interface_page(
        net_filters={"manufacturers": ["M1"], "devices_by_manufacturer": {"M1": ["sw-01"]}},
        port_summary={"device_count": 1, "total_ports": 10, "active_ports": 5, "avg_icmp_loss_pct": 0.0},
        percentile_data={"overall_port_utilization_pct": 40.0, "top_interfaces": []},
        interface_table=interface_table or {},
        top_scope="switch",
        switch_role="backbone",
    )


def test_the_page_carries_a_switch_for_the_table():
    assert _find_by_id(_page(), "net-interface-table-toggle") is not None


def test_the_switch_starts_off():
    """Off is the whole point: on means the page pays for the table again."""
    toggle = _find_by_id(_page(), "net-interface-table-toggle")
    assert getattr(toggle, "checked", None) is False


def test_the_table_starts_empty():
    table = _find_by_id(_page(), "net-interface-table")
    assert table is not None
    assert getattr(table, "data", None) == []


def test_the_footer_says_the_table_is_waiting_rather_than_that_it_is_empty():
    """An empty table with "Showing 1-0 of 0 interfaces" under it reads as
    "this DC has no interfaces", which is a different and wrong statement."""
    footer = _find_by_id(_page(), "net-interface-table-footer")
    text = str(getattr(footer, "children", ""))
    assert "0 interfaces" not in text
    assert text.strip()


def test_a_page_built_with_data_already_in_hand_shows_it():
    """The switch tracks whether the table has been loaded, not a preference.
    If a caller ever hands this function a payload again, hiding it behind an
    off switch would be the component lying about what it was given."""
    page = _page({"items": [{"host": "sw-01", "interface_name": "eth0", "p95_total_bps": 1e9,
                             "speed_bps": 10e9, "utilization_pct": 10.0}], "total": 1})
    assert getattr(_find_by_id(page, "net-interface-table-toggle"), "checked", None) is True
    assert len(getattr(_find_by_id(page, "net-interface-table"), "data", [])) == 1


def _call_table_callback(app_module, mock_api, *, toggle):
    return app_module.update_net_interface_table(
        "switch",
        "backbone",
        None,
        None,
        "",
        0,
        "50",
        toggle,
        {"preset": "last_7d"},
        "/datacenter/DC13",
    )


def test_the_callback_does_not_query_while_the_switch_is_off():
    """The callback fires on first render whether anyone asked for it or not.
    With the switch off it has to come back without touching the upstream —
    otherwise the switch saves nothing and the page still waits on 4,060 rows."""
    import app as app_module

    with patch.object(app_module, "api") as mock_api:
        rows, *_ = _call_table_callback(app_module, mock_api, toggle=False)

        mock_api.get_dc_network_interface_table.assert_not_called()
        assert rows == []


def test_the_callback_queries_once_the_switch_is_on():
    import app as app_module

    with patch.object(app_module, "api") as mock_api:
        mock_api.get_dc_network_interface_table.return_value = {
            "items": [{"host": "sw-01", "interface_name": "eth0", "p95_total_bps": 1e9,
                       "speed_bps": 10e9, "utilization_pct": 10.0}],
            "total": 42,
        }

        rows, _columns, _page_size, _page_count, _page_current, footer = _call_table_callback(
            app_module, mock_api, toggle=True
        )

        mock_api.get_dc_network_interface_table.assert_called_once()
        assert len(rows) == 1
        assert "42" in str(footer)


def test_the_footer_explains_the_empty_table_rather_than_leaving_it_blank():
    """Turning the switch off again should say why the rows went away."""
    import app as app_module

    with patch.object(app_module, "api"):
        *_, footer = _call_table_callback(app_module, None, toggle=False)

    assert isinstance(footer, str)
    assert footer.strip()
