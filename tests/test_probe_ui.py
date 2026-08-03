"""Collector Probe panel rendering."""

from __future__ import annotations

from dash import html

from src.utils.hmdl_probe_ui import (
    build_probe_endpoint_table,
    build_probe_matrix,
    build_probe_reason_cards,
    build_probe_runner_alert,
    build_probe_section,
    probe_inline_badge,
)

_DATA = {
    "summary": {"endpoints": 3, "probes": 5, "ok": 2, "fail": 3, "scripts": 3},
    "scripts": [
        {
            "probe_id": "nutanix_vm",
            "product": "nutanix",
            "collector_type": "Nutanix",
            "bucket": "heavy",
            "endpoints": 2,
            "ok": 1,
            "fail": 1,
            "status": "partial",
        },
        {
            "probe_id": "ibm_hmc",
            "product": "ibm",
            "collector_type": "IBM-HMC",
            "bucket": "heavy",
            "endpoints": 1,
            "ok": 0,
            "fail": 1,
            "status": "fail",
        },
    ],
    "matrix": [
        {"probe_id": "nutanix_vm", "dc": "DC13", "ok": 1, "fail": 0, "total": 1, "status": "ok"},
        {"probe_id": "nutanix_vm", "dc": "DC18", "ok": 0, "fail": 1, "total": 1, "status": "fail"},
        {"probe_id": "ibm_hmc", "dc": "DC14", "ok": 0, "fail": 1, "total": 1, "status": "fail"},
    ],
    "reasons": [
        {
            "category": "script_missing",
            "reason": "script_missing",
            "count": 1,
            "probe_ids": ["ibm_hmc"],
            "dcs": ["DC14"],
        },
        {
            "category": "timeout",
            "reason": "timeout_1800s",
            "count": 1,
            "probe_ids": ["nutanix_vm"],
            "dcs": ["DC18"],
        },
    ],
    "items": [
        {
            "probe_id": "nutanix_vm",
            "dc": "DC13",
            "target_host": "10.0.0.1",
            "entity_name": "Prism-1",
            "success": True,
            "reason": "ok",
            "reason_category": "ok",
            "duration_sec": 12.0,
        },
        {
            "probe_id": "nutanix_vm",
            "dc": "DC18",
            "target_host": "10.0.0.2",
            "entity_name": "Prism-2",
            "success": False,
            "reason": "timeout_1800s",
            "reason_category": "timeout",
            "duration_sec": 1800.0,
        },
        {
            "probe_id": "ibm_hmc",
            "dc": "DC14",
            "target_host": "10.0.0.3",
            "entity_name": "HMC_DC14",
            "success": False,
            "reason": "script_missing",
            "reason_category": "script_missing",
            "duration_sec": None,
        },
    ],
    "runner_errors": [],
    "dcs": ["DC13", "DC14", "DC18"],
}


def _text(component) -> str:
    return str(component)


def test_matrix_renders_a_row_per_script_and_a_column_per_dc():
    rendered = _text(build_probe_matrix(_DATA["scripts"], _DATA["matrix"], _DATA["dcs"]))
    assert "nutanix_vm" in rendered
    assert "ibm_hmc" in rendered
    for dc in _DATA["dcs"]:
        assert dc in rendered


def test_matrix_cells_are_clickable_only_where_a_probe_ran():
    rendered = _text(build_probe_matrix(_DATA["scripts"], _DATA["matrix"], _DATA["dcs"]))
    # nutanix_vm never ran in DC14 and ibm_hmc never ran in DC13/DC18: 3 buttons, not 6.
    assert rendered.count("'type': 'hmdl-probe-cell'") == 3


def test_matrix_without_probes_explains_itself():
    assert "Probe kaydı yok" in _text(build_probe_matrix([], [], []))


def test_reason_cards_group_failures_by_owner():
    rendered = _text(build_probe_reason_cards(_DATA["reasons"]))
    assert "Script yok (NiFi deploy)" in rendered
    assert "Süre aşımı" in rendered


def test_reason_cards_say_so_when_nothing_fails():
    assert "Fail eden collector script yok" in _text(build_probe_reason_cards([]))


def test_section_defaults_to_every_failing_run():
    rendered = _text(build_probe_section(_DATA))
    assert "Fail eden tüm çalıştırmalar (2)" in rendered
    assert "Prism-2" in rendered
    assert "HMC_DC14" in rendered
    assert "Hata nedenleri özeti" in rendered
    assert "Genel skor" in rendered
    assert "Son çalışma" in _text(build_probe_endpoint_table(_DATA["items"]))
    assert "En kötü script" not in rendered


def test_section_with_a_selected_cell_shows_only_that_script_and_dc():
    rendered = _text(build_probe_section(_DATA, selected=("ibm_hmc", "DC14")))
    assert "ibm_hmc · DC14 — 1 endpoint" in rendered
    assert "HMC_DC14" in rendered
    assert "Prism-2" not in rendered


def test_endpoint_table_lists_failures_before_successes():
    rendered = _text(build_probe_endpoint_table(_DATA["items"]))
    assert rendered.index("Prism-2") < rendered.index("Prism-1")


def test_runner_errors_are_reported_apart_from_collector_verdicts():
    assert build_probe_runner_alert([]) is None
    alert = build_probe_runner_alert(
        [{"dc": "ICT21", "run_id": "probe-1", "reason": "batch_parse:Extra data"}]
    )
    assert "Probe altyapı hatası" in _text(alert)


def test_parent_badge_only_appears_when_the_endpoint_was_probed():
    assert probe_inline_badge({"endpoint_ip": "10.0.0.9"}) is None
    badge = probe_inline_badge(
        {"probe_ok": 2, "probe_total": 3, "probe_status": "partial", "probe_reasons": "auth_failed"}
    )
    assert "probe 2/3" in _text(badge)
    assert "auth_failed" in _text(badge)


def test_coverage_parent_rows_carry_the_probe_badge():
    from src.utils.hmdl_sync_ui import build_vcenter_expand_table

    rendered = _text(
        build_vcenter_expand_table(
            [
                {
                    "source": "nutanix",
                    "parent_key": "10.0.0.1",
                    "endpoint_name": "Prism-1",
                    "endpoint_ip": "10.0.0.1",
                    "dc": "DC13",
                    "status": "live",
                    "probe_ok": 2,
                    "probe_total": 3,
                    "probe_status": "partial",
                    "probe_reasons": "auth_failed",
                }
            ],
            [],
        )
    )
    assert "probe 2/3" in rendered


def test_section_is_safe_on_an_empty_contract():
    assert isinstance(build_probe_section({}), html.Div)
