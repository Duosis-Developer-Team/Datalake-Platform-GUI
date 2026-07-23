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


def _val(key):
    return {"type": "hmdlcfg-val", "key": key}


def _bool(key):
    return {"type": "hmdlcfg-bool", "key": key}


def test_untouched_inherited_switch_is_not_emitted():
    """sync_devices defaults to true in the Ansible role. It is absent from the
    job template, so the form renders it ON — saving must NOT write it back
    (writing false would silently stop device syncing)."""
    out = page.assemble_extra_vars(
        [], [],
        [_bool("sync_devices"), _bool("dry_run")], [True, False],
        orig_keys=[], init_values={"sync_devices": True, "dry_run": False},
    )
    assert out == {}


def test_changed_inherited_switch_is_emitted():
    out = page.assemble_extra_vars(
        [], [],
        [_bool("sync_devices"), _bool("dry_run")], [False, False],
        orig_keys=[], init_values={"sync_devices": True, "dry_run": False},
    )
    assert out == {"sync_devices": False}


def test_untouched_inherited_number_is_not_emitted():
    """parallel_compare_workers defaults to 20; emitting 0 crashes the playbook
    (ThreadPoolExecutor(max_workers=0) raises ValueError)."""
    out = page.assemble_extra_vars(
        [_val("parallel_compare_workers"), _val("device_limit")], [20, 0],
        [], [],
        orig_keys=[], init_values={"parallel_compare_workers": 20, "device_limit": 0},
    )
    assert out == {}


def test_parallel_compare_workers_never_emits_zero():
    for value in (0, None, ""):
        out = page.assemble_extra_vars(
            [_val("parallel_compare_workers")], [value],
            [], [],
            orig_keys=["parallel_compare_workers"],
            init_values={"parallel_compare_workers": 20},
        )
        assert "parallel_compare_workers" not in out, value
    # a legal value still goes through
    out = page.assemble_extra_vars(
        [_val("parallel_compare_workers")], [8], [], [],
        orig_keys=["parallel_compare_workers"], init_values={"parallel_compare_workers": 20},
    )
    assert out == {"parallel_compare_workers": 8}


def test_key_in_original_is_always_emitted_even_when_unchanged():
    """AWX already manages it, so keep managing it."""
    out = page.assemble_extra_vars(
        [_val("location_filter")], ["DC13"],
        [_bool("dry_run")], [True],
        orig_keys=["location_filter", "dry_run"],
        init_values={"location_filter": "DC13", "dry_run": True},
    )
    assert out == {"location_filter": "DC13", "dry_run": True}


def test_managed_text_cleared_to_empty_string_is_emitted():
    """FIX B: blanking an AWX-managed key must actually clear it server-side."""
    out = page.assemble_extra_vars(
        [_val("location_filter")], [""], [], [],
        orig_keys=["location_filter"], init_values={"location_filter": "DC13"},
    )
    assert out == {"location_filter": ""}


def test_managed_mail_recipients_cleared_to_empty_list_is_emitted():
    out = page.assemble_extra_vars(
        [_val("mail_recipients")], [""], [], [],
        orig_keys=["mail_recipients"], init_values={"mail_recipients": "a@b.c"},
    )
    assert out == {"mail_recipients": []}


def test_inherited_empty_text_is_still_skipped():
    """An inherited-and-untouched blank field writes nothing."""
    out = page.assemble_extra_vars(
        [_val("location_filter"), _val("mail_recipients")], ["", ""], [], [],
        orig_keys=[], init_values={"location_filter": "", "mail_recipients": ""},
    )
    assert out == {}


def test_save_cb_wires_stores_into_assemble():
    with patch.object(page.api, "put_hmdl_awx_config",
                      return_value={"awx_available": True, "extra_vars": {}}) as mock_put:
        page._save_cb(
            1,
            ["DC13"], [_val("location_filter")],
            [True, False], [_bool("sync_devices"), _bool("dry_run")],
            ["location_filter"],
            {"location_filter": "DC13", "sync_devices": True, "dry_run": False},
        )
    # managed key kept, untouched inherited switches dropped
    mock_put.assert_called_once_with({"location_filter": "DC13"})


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
    with patch.object(page.api, "launch_hmdl_awx_job", return_value={"job_id": 501, "ignored_fields": {}}):
        store, poll_disabled, msg = page._run_cb(1, True)
    assert store == {"job_id": 501}
    assert poll_disabled is False
    assert isinstance(msg, dmc.Alert)
    assert msg.color == "blue"


def test_run_cb_warns_when_awx_ignored_the_extra_vars_override():
    """AWX only honours launch-time extra_vars when the job template has
    'Prompt on launch' for Variables; otherwise the run is NOT dry."""
    with patch.object(page.api, "launch_hmdl_awx_job",
                      return_value={"job_id": 501, "ignored_fields": {"extra_vars": {"dry_run": True}}}):
        store, poll_disabled, msg = page._run_cb(1, True)
    assert store == {"job_id": 501}
    assert poll_disabled is False
    assert isinstance(msg, dmc.Alert)
    assert msg.color == "yellow"
    assert "Prompt on launch" in str(msg.children)


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
