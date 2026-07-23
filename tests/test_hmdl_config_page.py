"""Smoke + behavior tests for the HMDL configuration page."""

from unittest.mock import patch

import dash_mantine_components as dmc
from dash import html

from src.pages.settings.integrations import hmdl_config as page


def _walk(node):
    yield node
    children = getattr(node, "children", None)
    if children is None:
        return
    if not isinstance(children, (list, tuple)):
        children = [children]
    for c in children:
        yield from _walk(c)


def _ids(layout):
    out = []
    for n in _walk(layout):
        cid = getattr(n, "id", None)
        if cid is not None:
            out.append(cid)
    return out


def _by_id(layout, pattern_id):
    """Find a node whose id matches the given pattern-matching id dict."""
    for n in _walk(layout):
        if getattr(n, "id", None) == pattern_id:
            return n
    return None


def _first_alert(layout):
    for n in _walk(layout):
        if isinstance(n, dmc.Alert):
            return n
    return None


def _store_data(layout, store_id):
    for n in _walk(layout):
        if getattr(n, "id", None) == store_id:
            return n.data
    return None


def _spec(key):
    return next(s for s in page.FIELD_SPECS if s["key"] == key)


def test_layout_renders_banner_when_awx_unavailable():
    with patch.object(page.api, "get_hmdl_awx_config",
                      return_value={"awx_available": False, "extra_vars": {}, "schedules": []}):
        layout = page.build_layout()
    assert isinstance(layout, html.Div)
    # a visible Alert somewhere in the tree
    alert = _first_alert(layout)
    assert alert is not None
    assert alert.color == "yellow"
    assert "yapılandırılmadı" in alert.title


def test_banner_shows_not_configured_reason_from_service():
    reason = "AWX not configured: API_AUTH_REQUIRED must be true when AWX_ENABLED is true."
    with patch.object(page.api, "get_hmdl_awx_config",
                      return_value={"awx_available": False, "reason": reason,
                                    "extra_vars": {}, "schedules": []}):
        layout = page.build_layout()
    alert = _first_alert(layout)
    assert alert.color == "yellow"
    texts = [n.children for n in _walk(alert) if isinstance(n, dmc.Text)]
    assert reason in texts


def test_banner_distinguishes_real_failure_from_not_configured():
    """An expired token / DNS failure / wrong JT id must NOT read as
    'you haven't configured AWX'."""
    reason = "Client error '401 Unauthorized' for url 'https://awx/api/v2/job_templates/42/'"
    with patch.object(page.api, "get_hmdl_awx_config",
                      return_value={"awx_available": False, "reason": reason,
                                    "extra_vars": {}, "schedules": []}):
        layout = page.build_layout()
    alert = _first_alert(layout)
    assert alert.color == "red"
    assert "yapılandırılmadı" not in alert.title
    texts = [n.children for n in _walk(alert) if isinstance(n, dmc.Text)]
    assert reason in texts


def test_layout_prefills_fields_from_extra_vars():
    with patch.object(page.api, "get_hmdl_awx_config",
                      return_value={"awx_available": True,
                                    "extra_vars": {"dry_run": True, "device_limit": 7, "device_source": "loki"},
                                    "schedules": []}):
        layout = page.build_layout()
    ids = _ids(layout)
    # value fields and bool fields are addressed by pattern-matching ids
    assert {"type": "hmdlcfg-val", "key": "device_source"} in ids
    assert {"type": "hmdlcfg-bool", "key": "dry_run"} in ids
    assert {"type": "hmdlcfg-val", "key": "device_limit"} in ids

    # rendered state must actually reflect the mocked extra_vars, not just
    # the presence of the id
    dry_run_switch = _by_id(layout, {"type": "hmdlcfg-bool", "key": "dry_run"})
    assert isinstance(dry_run_switch, dmc.Switch)
    assert dry_run_switch.checked is True

    device_limit_input = _by_id(layout, {"type": "hmdlcfg-val", "key": "device_limit"})
    assert isinstance(device_limit_input, dmc.NumberInput)
    assert device_limit_input.value == 7

    device_source_select = _by_id(layout, {"type": "hmdlcfg-val", "key": "device_source"})
    assert isinstance(device_source_select, dmc.Select)
    assert device_source_select.value == "loki"


def test_mail_recipients_renders_as_csv_textinput_seeded_from_list():
    with patch.object(page.api, "get_hmdl_awx_config",
                      return_value={"awx_available": True,
                                    "extra_vars": {"mail_recipients": ["a@b.c", "d@e.f"]},
                                    "schedules": []}):
        layout = page.build_layout()
    mail_field = _by_id(layout, {"type": "hmdlcfg-val", "key": "mail_recipients"})
    assert isinstance(mail_field, dmc.TextInput)
    assert "a@b.c" in mail_field.value
    assert "d@e.f" in mail_field.value


def test_field_specs_cover_whitelist():
    keys = [f["key"] for f in page.FIELD_SPECS]
    assert len(keys) == len(set(keys))
    assert "dry_run" in keys and "device_source" in keys and "mail_recipients" in keys


def test_every_field_spec_carries_a_role_default():
    for spec in page.FIELD_SPECS:
        assert "default" in spec, f"{spec['key']} has no role default"


def test_role_defaults_match_the_ansible_role():
    """Verbatim from
    project-zabake/zabbix-netbox/playbooks/roles/netbox_zabbix_sync/defaults/main.yml.
    If the role changes, this must change with it."""
    expected = {
        "device_source": "datalake", "platform_source": "loki", "virtual_fw_source": "loki",
        "sync_devices": True, "sync_platforms": False, "sync_virtual_fws": False,
        "report_izlenmeyecek": True,
        "create_devices_disabled": False, "create_platforms_disabled": False,
        "create_virtual_fws_disabled": False,
        "dry_run": False, "only_fetch": False, "debug_mode": False,
        "parallel_compare_ignore_errors": False,
        "device_limit": 0, "parallel_compare_workers": 20, "location_filter": "",
        "hmdl_log_enabled": False,
        "mail_recipients": [], "mail_from": "infrareport@alert.bulutistan.com",
        "zabbix_url": "", "netbox_url": "",
        "discovery_db_host": "", "discovery_db_port": 5000, "discovery_db_name": "",
    }
    assert {s["key"]: s["default"] for s in page.FIELD_SPECS} == expected


def test_absent_keys_render_at_role_default_and_are_marked_inherited():
    """A key missing from extra_vars must NOT render as off/0 — the role default
    is what the automation actually uses."""
    with patch.object(page.api, "get_hmdl_awx_config",
                      return_value={"awx_available": True, "extra_vars": {"dry_run": True},
                                    "schedules": []}):
        layout = page.build_layout()

    sync_devices = _by_id(layout, {"type": "hmdlcfg-bool", "key": "sync_devices"})
    assert sync_devices.checked is True                       # role default is true
    assert sync_devices.description == page._INHERITED_DESC

    workers = _by_id(layout, {"type": "hmdlcfg-val", "key": "parallel_compare_workers"})
    assert workers.value == 20                                # role default is 20
    assert workers.min == 1                                   # max_workers=0 is illegal
    assert workers.description == page._INHERITED_DESC

    platform_source = _by_id(layout, {"type": "hmdlcfg-val", "key": "platform_source"})
    assert platform_source.value == "loki"
    assert platform_source.description == page._INHERITED_DESC

    mail_from = _by_id(layout, {"type": "hmdlcfg-val", "key": "mail_from"})
    assert mail_from.value == "infrareport@alert.bulutistan.com"

    # a key that IS present is not flagged as inherited
    dry_run = _by_id(layout, {"type": "hmdlcfg-bool", "key": "dry_run"})
    assert dry_run.description is None


def test_layout_captures_managed_keys_and_initial_values_in_stores():
    with patch.object(page.api, "get_hmdl_awx_config",
                      return_value={"awx_available": True,
                                    "extra_vars": {"dry_run": True, "device_limit": 7},
                                    "schedules": []}):
        layout = page.build_layout()
    orig = _store_data(layout, "hmdlcfg-orig-store")
    assert sorted(orig) == ["device_limit", "dry_run"]

    init = _store_data(layout, "hmdlcfg-init-store")
    assert set(init) == {s["key"] for s in page.FIELD_SPECS}
    assert init["dry_run"] is True and init["device_limit"] == 7
    assert init["sync_devices"] is True            # inherited role default
    assert init["parallel_compare_workers"] == 20  # inherited role default


def test_not_configured_sentinel_matches_service_contract():
    """FIX 4: the 'not configured' marker is duplicated across the service
    boundary (this GUI module vs services/hmdl-api/app/services/awx_client.py).
    Pin the exact literal here AND on the service side (see hmdl-api's
    test_awx_client.py::test_not_configured_prefix_matches_gui_contract) so a
    one-sided change to either fails its own suite instead of silently
    breaking the yellow/red banner distinction (see _NOT_CONFIGURED_PREFIX)."""
    assert page._NOT_CONFIGURED_PREFIX == "AWX not configured"


def test_initial_value_matches_what_the_widget_renders():
    """The init store must mirror the widget exactly, otherwise 'unchanged'
    detection in assemble_extra_vars is wrong."""
    current = {"mail_recipients": ["a@b.c", "d@e.f"], "device_source": "loki"}
    with patch.object(page.api, "get_hmdl_awx_config",
                      return_value={"awx_available": True, "extra_vars": current, "schedules": []}):
        layout = page.build_layout()
    init = _store_data(layout, "hmdlcfg-init-store")
    for spec in page.FIELD_SPECS:
        node = _by_id(layout, {"type": "hmdlcfg-bool" if spec["kind"] == "switch" else "hmdlcfg-val",
                               "key": spec["key"]})
        rendered = node.checked if spec["kind"] == "switch" else node.value
        assert init[spec["key"]] == rendered, spec["key"]
