"""Behavior tests for HMDL config page helper + save/run/poll/schedule callbacks."""

from unittest.mock import patch

import dash_mantine_components as dmc

from src.pages.settings.integrations import hmdl_config as page


def test_assemble_extra_vars_merges_val_and_bool():
    val_ids = [{"type": "hmdlcfg-val", "key": "device_source"}, {"type": "hmdlcfg-val", "key": "device_limit"}]
    val_values = ["loki", 7]
    bool_ids = [{"type": "hmdlcfg-bool", "key": "dry_run"}]
    bool_values = [True]
    out = page.assemble_extra_vars(val_ids, val_values, bool_ids, bool_values)
    assert out == {"device_source": "loki", "device_limit": 7, "dry_run": True}


def test_assemble_extra_vars_skips_empty_text():
    val_ids = [{"type": "hmdlcfg-val", "key": "location_filter"}, {"type": "hmdlcfg-val", "key": "mail_from"}]
    val_values = ["", "a@b.c"]
    out = page.assemble_extra_vars(val_ids, val_values, [], [])
    assert out == {"mail_from": "a@b.c"}  # empty string dropped


def test_assemble_extra_vars_splits_mail_recipients_csv_string():
    val_ids = [{"type": "hmdlcfg-val", "key": "mail_recipients"}]
    val_values = ["a@b.c, d@e.f"]
    out = page.assemble_extra_vars(val_ids, val_values, [], [])
    assert out == {"mail_recipients": ["a@b.c", "d@e.f"]}


def test_assemble_extra_vars_empty_mail_recipients_string_yields_no_key():
    val_ids = [{"type": "hmdlcfg-val", "key": "mail_recipients"}]
    val_values = [""]
    out = page.assemble_extra_vars(val_ids, val_values, [], [])
    assert "mail_recipients" not in out


def test_save_cb_success():
    # _save_cb(n_clicks, val_values, val_ids, bool_values, bool_ids) — argument
    # order mirrors the @callback State declaration order (value before id),
    # which is how Dash actually invokes it.
    with patch.object(page.api, "put_hmdl_awx_config", return_value={"awx_available": True, "extra_vars": {}}) as mock_put:
        msg = page._save_cb(
            1,
            ["loki"], [{"type": "hmdlcfg-val", "key": "device_source"}],
            [True], [{"type": "hmdlcfg-bool", "key": "dry_run"}],
        )
    assert isinstance(msg, dmc.Alert)
    assert msg.color == "green"
    mock_put.assert_called_once_with({"device_source": "loki", "dry_run": True})


def test_save_cb_error_surfaces_alert():
    with patch.object(page.api, "put_hmdl_awx_config", side_effect=Exception("nope")):
        msg = page._save_cb(
            1,
            ["loki"], [{"type": "hmdlcfg-val", "key": "device_source"}],
            [], [],
        )
    assert isinstance(msg, dmc.Alert)
    assert msg.color == "red"


def test_run_cb_starts_poll_and_stores_job():
    with patch.object(page.api, "launch_hmdl_awx_job", return_value={"job_id": 501}):
        store, poll_disabled, msg = page._run_cb(1, True)
    assert store == {"job_id": 501}
    assert poll_disabled is False
    assert isinstance(msg, dmc.Alert)


def test_run_cb_error_surfaces_alert_and_keeps_poll_disabled():
    with patch.object(page.api, "launch_hmdl_awx_job", side_effect=Exception("boom")):
        store, poll_disabled, msg = page._run_cb(1, False)
    assert store is page.dash.no_update
    assert poll_disabled is True
    assert isinstance(msg, dmc.Alert)
    assert msg.color == "red"


def test_poll_cb_running_keeps_polling():
    with patch.object(page.api, "get_hmdl_awx_job", return_value={"job_id": 501, "status": "running"}):
        msg, disabled = page._poll_cb(1, {"job_id": 501})
    assert isinstance(msg, dmc.Alert)
    assert msg.color == "blue"
    assert disabled is False


def test_poll_cb_successful_stops_polling():
    with patch.object(page.api, "get_hmdl_awx_job", return_value={"job_id": 501, "status": "successful"}):
        msg, disabled = page._poll_cb(1, {"job_id": 501})
    assert isinstance(msg, dmc.Alert)
    assert msg.color == "green"
    assert disabled is True


def test_poll_cb_failed_stops_polling():
    with patch.object(page.api, "get_hmdl_awx_job", return_value={"job_id": 501, "status": "failed"}):
        msg, disabled = page._poll_cb(1, {"job_id": 501})
    assert isinstance(msg, dmc.Alert)
    assert msg.color == "red"
    assert disabled is True


def test_poll_cb_no_job_disables_immediately():
    msg, disabled = page._poll_cb(1, {})
    assert msg is page.dash.no_update
    assert disabled is True


def test_sched_cb_toggles_and_returns_alert():
    with patch.object(page.api, "set_hmdl_awx_schedule", return_value={"id": 3, "enabled": True}):
        with patch.object(page, "ctx") as mock_ctx:
            mock_ctx.triggered_id = {"type": "hmdlcfg-sched", "sid": 3}
            msg = page._sched_cb([True], [{"type": "hmdlcfg-sched", "sid": 3}])
    assert isinstance(msg, dmc.Alert)
    assert msg.color == "green"


def test_sched_cb_error_surfaces_alert():
    with patch.object(page.api, "set_hmdl_awx_schedule", side_effect=Exception("nope")):
        with patch.object(page, "ctx") as mock_ctx:
            mock_ctx.triggered_id = {"type": "hmdlcfg-sched", "sid": 3}
            msg = page._sched_cb([True], [{"type": "hmdlcfg-sched", "sid": 3}])
    assert isinstance(msg, dmc.Alert)
    assert msg.color == "red"
