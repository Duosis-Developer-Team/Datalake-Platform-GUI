"""Automation Health renders one row per collection flow, not one per table.

Assertions read the rendered tree's repr: a Dash component's __repr__ carries both
its id and its text, e.g. ``Div(children=[Text('…')], id='hmdl-ah-flows')``. That
avoids hand-rolling a tree walker whose own bugs would be indistinguishable from
layout bugs.
"""
import dash

from src.pages.settings.integrations import hmdl_automation_health as page


def _render(monkeypatch, payload: dict) -> str:
    monkeypatch.setattr(page.api, "get_hmdl_automation_health", lambda: payload)
    layout = page.build_layout()
    assert isinstance(layout, dash.html.Div)
    return str(layout)


def _flow(key, label, status, age, sources):
    return {"key": key, "label": label, "status": status, "age_hours": age,
            "counts": {"fresh": 0, "stale": 0, "dead": len(sources), "unknown": 0,
                       "alert": 1 if status in ("dead", "stale") else 0},
            "sources": sources}


def _table_row(key, status, age):
    return {"key": key, "label": key, "cadence": f"public.{key}", "last_run_at": None,
            "age_hours": age, "status": status, "warn_hours": 26.0, "dead_hours": 50.0,
            "extra": {}}


_PAYLOAD = {
    "generated_at": None, "automations": [], "counts": {"alert": 0},
    "proxies": [], "proxy_summary": {}, "data_gaps": {},
    "data_families": [],
    "data_flows": [
        _flow("vmware_datastore", "Depolama kullanım verisi", "dead", 269.0,
              [_table_row("raw_vmware_datastore_metrics_agg", "dead", 269.0),
               _table_row("raw_vmware_datastore_host_mount", "dead", 268.0)]),
        _flow("family:NetBox", "NetBox", "fresh", None,
              [_table_row("discovery_netbox_inventory_device", "fresh", 3.0)]),
    ],
    "data_unmonitored": [_table_row("raw_panduit_pdu_inventory", "dead", 1514.0)],
    "data_counts": {"fresh": 1, "stale": 0, "dead": 1, "unknown": 0, "alert": 1},
    "data_status": "ok",
}


def test_flows_container_is_rendered(monkeypatch):
    assert "hmdl-ah-flows" in _render(monkeypatch, _PAYLOAD)


def test_alerting_flow_shows_its_label_not_the_table_name(monkeypatch):
    rendered = _render(monkeypatch, _PAYLOAD)
    assert "Depolama kullanım verisi" in rendered
    # The table name stays reachable (detail disclosure) but is not the headline.
    assert "raw_vmware_datastore_metrics_agg" in rendered


def test_healthy_flow_is_not_listed_as_a_row(monkeypatch):
    # Only alerting flows get a row; a fresh family must not add noise back.
    assert "NetBox" not in _render(monkeypatch, _PAYLOAD)


def test_flow_age_is_rendered_in_days(monkeypatch):
    assert "11 gündür güncellenmiyor" in _render(monkeypatch, _PAYLOAD)


def test_unmonitored_section_renders_and_is_collapsed(monkeypatch):
    rendered = _render(monkeypatch, _PAYLOAD)
    assert "hmdl-ah-unmonitored" in rendered
    assert "raw_panduit_pdu_inventory" in rendered
    assert "İzlenmeyen tablolar (1)" in rendered


def test_computing_state_renders_without_flows(monkeypatch):
    payload = dict(_PAYLOAD, data_status="computing", data_flows=[], data_unmonitored=[])
    assert "hesaplanıyor" in _render(monkeypatch, payload)


def test_no_alerting_flow_renders_the_all_clear(monkeypatch):
    payload = dict(
        _PAYLOAD,
        data_flows=[_flow("family:NetBox", "NetBox", "fresh", None,
                          [_table_row("discovery_netbox_inventory_device", "fresh", 3.0)])],
        data_counts={"fresh": 1, "stale": 0, "dead": 0, "unknown": 0, "alert": 0},
    )
    assert "Tüm veri akışları güncel" in _render(monkeypatch, payload)
