"""Integrations — HMDL netbox-zabbix AWX run & schedule configuration (Tier A).

Reads/writes only non-secret runtime variables of the AWX job template.
Secrets (DB/Zabbix/NetBox passwords, tokens, SNMP passphrases) stay in AWX
Credentials / Vault and are never shown or edited here.
"""

from __future__ import annotations

import dash
from dash import Input, Output, State, callback, ctx, dcc, html
import dash_mantine_components as dmc

from src.services import api_client as api

_PATH = "/administration/integrations/hmdl/config"

_SOURCE_OPTS = [{"value": "loki", "label": "loki (NetBox)"}, {"value": "datalake", "label": "datalake (Postgres)"}]

# Shown under every field whose key is ABSENT from the job template extra_vars:
# the widget then displays the Ansible role default, not a fabricated False/0.
_INHERITED_DESC = "rol varsayılanı"

# Prefix used by hmdl-api for the genuinely-not-configured case; any other
# `reason` means AWX *is* configured but the call failed (token, DNS, JT id…).
_NOT_CONFIGURED_PREFIX = "AWX not configured"

# section, key, kind, label, default. kind ∈ {"select","switch","number","text","csvlist"}
# `default` is the ACTUAL value from the Ansible role that runs in AWX:
#   project-zabake/zabbix-netbox/playbooks/roles/netbox_zabbix_sync/defaults/main.yml
# When a key is missing from the job template's extra_vars, the role default is
# what really applies — so that is what the form must show and must not clobber.
FIELD_SPECS: list[dict] = [
    # Source routing
    {"section": "Kaynak yönlendirme", "key": "device_source", "kind": "select", "label": "device_source", "opts": _SOURCE_OPTS, "default": "datalake"},
    {"section": "Kaynak yönlendirme", "key": "platform_source", "kind": "select", "label": "platform_source", "opts": _SOURCE_OPTS, "default": "loki"},
    {"section": "Kaynak yönlendirme", "key": "virtual_fw_source", "kind": "select", "label": "virtual_fw_source", "opts": _SOURCE_OPTS, "default": "loki"},
    # Sync scope
    {"section": "Sync kapsamı", "key": "sync_devices", "kind": "switch", "label": "sync_devices", "default": True},
    {"section": "Sync kapsamı", "key": "sync_platforms", "kind": "switch", "label": "sync_platforms", "default": False},
    {"section": "Sync kapsamı", "key": "sync_virtual_fws", "kind": "switch", "label": "sync_virtual_fws", "default": False},
    {"section": "Sync kapsamı", "key": "report_izlenmeyecek", "kind": "switch", "label": "report_izlenmeyecek", "default": True},
    {"section": "Sync kapsamı", "key": "create_devices_disabled", "kind": "switch", "label": "create_devices_disabled", "default": False},
    {"section": "Sync kapsamı", "key": "create_platforms_disabled", "kind": "switch", "label": "create_platforms_disabled", "default": False},
    {"section": "Sync kapsamı", "key": "create_virtual_fws_disabled", "kind": "switch", "label": "create_virtual_fws_disabled", "default": False},
    # Execution
    {"section": "Çalıştırma", "key": "dry_run", "kind": "switch", "label": "dry_run", "default": False},
    {"section": "Çalıştırma", "key": "only_fetch", "kind": "switch", "label": "only_fetch", "default": False},
    {"section": "Çalıştırma", "key": "debug_mode", "kind": "switch", "label": "debug_mode", "default": False},
    {"section": "Çalıştırma", "key": "parallel_compare_ignore_errors", "kind": "switch", "label": "parallel_compare_ignore_errors", "default": False},
    {"section": "Çalıştırma", "key": "device_limit", "kind": "number", "label": "device_limit (0=limitsiz)", "default": 0, "min": 0},
    # min=1: ThreadPoolExecutor(max_workers=0) raises ValueError, so 0 is never a legal write.
    {"section": "Çalıştırma", "key": "parallel_compare_workers", "kind": "number", "label": "parallel_compare_workers", "default": 20, "min": 1},
    {"section": "Çalıştırma", "key": "location_filter", "kind": "text", "label": "location_filter", "default": ""},
    # Logging + email
    {"section": "Log & e-posta", "key": "hmdl_log_enabled", "kind": "switch", "label": "hmdl_log_enabled", "default": False},
    {"section": "Log & e-posta", "key": "mail_recipients", "kind": "csvlist", "label": "mail_recipients (virgülle ayır)", "default": []},
    {"section": "Log & e-posta", "key": "mail_from", "kind": "text", "label": "mail_from", "default": "infrareport@alert.bulutistan.com"},
    # Endpoints (no passwords)
    {"section": "Bağlantı adresleri (parolasız)", "key": "zabbix_url", "kind": "text", "label": "zabbix_url", "default": ""},
    {"section": "Bağlantı adresleri (parolasız)", "key": "netbox_url", "kind": "text", "label": "netbox_url", "default": ""},
    {"section": "Bağlantı adresleri (parolasız)", "key": "discovery_db_host", "kind": "text", "label": "discovery_db_host", "default": ""},
    {"section": "Bağlantı adresleri (parolasız)", "key": "discovery_db_port", "kind": "text", "label": "discovery_db_port", "default": 5000},
    {"section": "Bağlantı adresleri (parolasız)", "key": "discovery_db_name", "kind": "text", "label": "discovery_db_name", "default": ""},
]


def _effective_value(spec: dict, current: dict):
    """Raw value the run will actually use: the JT override if the key is present,
    otherwise the role default."""
    key = spec["key"]
    return current[key] if key in current else spec.get("default")


def initial_value(spec: dict, current: dict):
    """The value as the widget renders it — the exact thing Dash hands back as the
    component's `value`/`checked` when the operator does not touch the field."""
    kind = spec["kind"]
    val = _effective_value(spec, current)
    if kind == "switch":
        return bool(val)
    if kind == "select":
        return str(val) if val is not None else None
    if kind == "number":
        return int(val) if isinstance(val, (int, float)) and not isinstance(val, bool) else 0
    if kind == "csvlist":
        vals = val if isinstance(val, list) else ([val] if val else [])
        return ", ".join(str(v) for v in vals)
    return "" if val is None else str(val)


def initial_values(current: dict) -> dict:
    """{key: initial_rendered_value} for every field (both val and bool groups)."""
    return {spec["key"]: initial_value(spec, current) for spec in FIELD_SPECS}


def managed_keys(current: dict) -> list[str]:
    """Whitelisted keys that are actually present in the fetched extra_vars."""
    return [spec["key"] for spec in FIELD_SPECS if spec["key"] in (current or {})]


def _build_field(spec: dict, current: dict):
    key = spec["key"]
    kind = spec["kind"]
    label = spec["label"]
    # Absent from AWX -> the role default applies; show it and flag it as inherited.
    desc = None if key in (current or {}) else _INHERITED_DESC
    value = initial_value(spec, current)
    if kind == "switch":
        return dmc.Switch(
            id={"type": "hmdlcfg-bool", "key": key},
            label=label,
            description=desc,
            checked=value,
            size="sm",
        )
    if kind == "select":
        return dmc.Select(
            id={"type": "hmdlcfg-val", "key": key},
            label=label,
            description=desc,
            data=spec["opts"],
            value=value,
            size="xs",
        )
    if kind == "number":
        return dmc.NumberInput(
            id={"type": "hmdlcfg-val", "key": key},
            label=label,
            description=desc,
            value=value,
            min=spec.get("min", 0),
            size="xs",
        )
    if kind == "csvlist":
        # dash-mantine-components 0.14.1 has no dmc.TagsInput/creatable
        # MultiSelect, and a MultiSelect seeded only from existing values
        # can't accept a brand-new address. Use a plain comma-delimited
        # TextInput instead; Task 7's callback splits it back into a list.
        return dmc.TextInput(
            id={"type": "hmdlcfg-val", "key": key},
            label=label,
            description=desc,
            value=value,
            size="xs",
        )
    # text
    return dmc.TextInput(
        id={"type": "hmdlcfg-val", "key": key},
        label=label,
        description=desc,
        value=value,
        size="xs",
    )


def _sections(current: dict):
    order: list[str] = []
    grouped: dict[str, list] = {}
    for spec in FIELD_SPECS:
        sec = spec["section"]
        if sec not in grouped:
            grouped[sec] = []
            order.append(sec)
        grouped[sec].append(_build_field(spec, current))
    papers = []
    for sec in order:
        papers.append(
            dmc.Paper(
                p="md", radius="md", withBorder=True, mb="md",
                children=[
                    dmc.Title(sec, order=5, mb="sm"),
                    dmc.SimpleGrid(cols={"base": 1, "md": 3}, spacing="sm", children=grouped[sec]),
                ],
            )
        )
    return papers


def _last_run_line(last_job: dict | None):
    """Page-load view of the previous run (independent of any job launched via
    'Şimdi çalıştır' in the current session, which is tracked separately by
    hmdlcfg-job-store / the poll callback). Historical runs beyond this last
    one live in the Datalake Sync Health tab."""
    if not last_job:
        return dmc.Text("Son çalıştırma kaydı yok.", id="hmdlcfg-last-run", size="sm", c="dimmed")
    job_id = last_job.get("job_id")
    status = last_job.get("status") or "unknown"
    finished = last_job.get("finished")
    label = f"Son çalıştırma: job #{job_id} — {status}"
    if finished:
        label += f" ({finished})"
    return dmc.Text(label, id="hmdlcfg-last-run", size="sm", c="dimmed")


def _schedule_rows(schedules: list[dict]):
    rows = []
    for s in schedules or []:
        sid = s.get("id")
        rows.append(
            dmc.Group(
                justify="space-between",
                children=[
                    dmc.Text(f"{s.get('name') or sid} — next: {s.get('next_run') or '-'}", size="sm"),
                    dmc.Switch(
                        id={"type": "hmdlcfg-sched", "sid": sid},
                        checked=bool(s.get("enabled")),
                        label="enabled",
                        size="sm",
                    ),
                ],
            )
        )
    return rows or [dmc.Text("Schedule yok.", size="sm", c="dimmed")]


def build_layout(search: str | None = None) -> html.Div:
    cfg = api.get_hmdl_awx_config()
    available = bool(cfg.get("awx_available"))
    current = cfg.get("extra_vars") or {}
    schedules = cfg.get("schedules") or []
    last_job = cfg.get("last_job")

    banner = None
    if not available:
        reason = str(cfg.get("reason") or "")
        if not reason or reason.startswith(_NOT_CONFIGURED_PREFIX):
            # Genuinely not wired up yet.
            body = [
                dmc.Text(
                    "hmdl-api'de AWX_API_URL / AWX_TOKEN / AWX_NETBOX_ZABBIX_JT_ID ayarlanınca "
                    "değişkenler ve schedule buradan yönetilebilecek. Ekran salt görünümde.",
                    size="sm",
                )
            ]
            if reason:
                body.append(dmc.Text(reason, size="xs", c="dimmed", mt="xs"))
            banner = dmc.Alert(color="yellow", title="AWX yapılandırılmadı", children=body, mb="md")
        else:
            # AWX *is* configured but the call failed — show the real reason
            # (expired token, DNS, wrong JT id, timeout) instead of blaming setup.
            banner = dmc.Alert(
                color="red",
                title="AWX'e ulaşılamadı",
                children=[
                    dmc.Text("Yapılandırma okunamadı; ekran salt görünümde.", size="sm"),
                    dmc.Text(reason, size="xs", c="dimmed", mt="xs"),
                ],
                mb="md",
            )

    run_bar = dmc.Paper(
        p="md", radius="md", withBorder=True, mb="md",
        children=[
            dmc.Group(
                children=[
                    dmc.Button("Kaydet", id="hmdlcfg-save", size="sm", disabled=not available),
                    dmc.Button("Şimdi çalıştır", id="hmdlcfg-run", size="sm", color="teal", variant="light", disabled=not available),
                    dmc.Switch(id="hmdlcfg-run-dryrun", label="dry_run override", size="sm"),
                ],
            ),
            html.Div(_last_run_line(last_job), style={"marginTop": "8px"}),
            html.Div(id="hmdlcfg-save-msg", style={"marginTop": "8px"}),
            html.Div(id="hmdlcfg-run-msg", style={"marginTop": "8px"}),
        ],
    )

    return html.Div(
        [
            dmc.Stack(
                gap="xs", mb="md",
                children=[
                    dmc.Title("HMDL netbox-zabbix — Çalıştırma yapılandırması", order=3),
                    dmc.Text(
                        "AWX job template'inin gizli-olmayan çalışma değişkenleri (extra_vars). "
                        "Parolalar/token'lar AWX Credentials/Vault'ta kalır; burada görünmez.",
                        size="sm", c="dimmed",
                    ),
                ],
            ),
            banner if banner else html.Div(),
            run_bar,
            *_sections(current),
            dmc.Paper(
                p="md", radius="md", withBorder=True, mb="md",
                children=[dmc.Title("Schedule", order=5, mb="sm"),
                          html.Div(id="hmdlcfg-sched-msg", style={"marginBottom": "8px"}),
                          dmc.Stack(gap="xs", children=_schedule_rows(schedules))],
            ),
            # Keys AWX already manages (present in the fetched extra_vars) and the
            # value every field rendered with. Save uses both so untouched
            # role-default fields are never written back. See assemble_extra_vars.
            dcc.Store(id="hmdlcfg-orig-store", data=managed_keys(current)),
            dcc.Store(id="hmdlcfg-init-store", data=initial_values(current)),
            # job-status polling plumbing (callbacks in Task 7)
            dcc.Store(id="hmdlcfg-job-store"),
            dcc.Interval(id="hmdlcfg-job-poll", interval=4000, disabled=True),
        ]
    )


_NUMERIC_KEYS = {"device_limit", "parallel_compare_workers"}


def _should_emit(key: str, value, orig: set, init: dict) -> bool:
    """A key is written back only when AWX already manages it (so it stays
    editable AND clearable), or when the operator actually moved the widget off
    the role default. Anything else is left out so the role default keeps
    applying — writing it would silently override e.g. sync_devices=true."""
    if key in orig:
        return True
    if key not in init:
        # No render-time snapshot (legacy/direct call): fall back to emitting.
        return True
    return value != init.get(key)


def assemble_extra_vars(val_ids, val_values, bool_ids, bool_values, orig_keys=None, init_values=None) -> dict:
    orig = set(orig_keys or [])
    init = init_values or {}
    out: dict = {}
    for cid, value in zip(val_ids or [], val_values or []):
        key = cid.get("key")
        if not key:
            continue
        in_orig = key in orig
        if not _should_emit(key, value, orig, init):
            continue
        if key == "mail_recipients":
            if isinstance(value, str):
                parts = [v.strip() for v in value.split(",") if v.strip()]
            elif isinstance(value, list):
                parts = [str(v).strip() for v in value if str(v).strip()]
            else:
                parts = []
            # Emit [] only for an AWX-managed key, so blanking it really clears it.
            if parts or in_orig:
                out[key] = parts
            continue
        if value is None:
            continue
        if key == "parallel_compare_workers" and not value:
            # ThreadPoolExecutor(max_workers=0) raises ValueError — never write 0.
            continue
        if isinstance(value, str):
            # "" is a real clear for an AWX-managed key; for an inherited key it
            # would just pin the role default, so skip it.
            if value == "" and not in_orig:
                continue
            out[key] = value
        elif key in _NUMERIC_KEYS:
            out[key] = int(value)
        else:
            out[key] = value
    for cid, value in zip(bool_ids or [], bool_values or []):
        key = cid.get("key")
        if not key:
            continue
        checked = bool(value)
        if not _should_emit(key, checked, orig, init):
            continue
        out[key] = checked
    return out


@callback(
    Output("hmdlcfg-save-msg", "children"),
    Output("hmdlcfg-orig-store", "data"),
    Output("hmdlcfg-init-store", "data"),
    Input("hmdlcfg-save", "n_clicks"),
    State({"type": "hmdlcfg-val", "key": dash.ALL}, "value"),
    State({"type": "hmdlcfg-val", "key": dash.ALL}, "id"),
    State({"type": "hmdlcfg-bool", "key": dash.ALL}, "checked"),
    State({"type": "hmdlcfg-bool", "key": dash.ALL}, "id"),
    State("hmdlcfg-orig-store", "data"),
    State("hmdlcfg-init-store", "data"),
    prevent_initial_call=True,
)
def _save_cb(_n, val_values, val_ids, bool_values, bool_ids, orig_keys=None, init_values=None):
    extra_vars = assemble_extra_vars(val_ids, val_values, bool_ids, bool_values, orig_keys, init_values)
    try:
        resp = api.put_hmdl_awx_config(extra_vars)
        # Refresh both stores from what AWX now actually has, using the SAME
        # helpers build_layout uses — otherwise a revert-then-save compares
        # against the stale pre-save snapshot and silently no-ops (see FIX 1).
        new_current = (resp or {}).get("extra_vars") or {}
        new_orig = managed_keys(new_current)
        new_init = initial_values(new_current)
        msg = dmc.Alert(color="green", title="Kaydedildi — bir sonraki (scheduled/manual) çalıştırma bunu kullanır.")
        return msg, new_orig, new_init
    except Exception as exc:  # noqa: BLE001
        msg = dmc.Alert(color="red", title="Kaydetme başarısız", children=str(exc))
        return msg, dash.no_update, dash.no_update


@callback(
    Output("hmdlcfg-job-store", "data"),
    Output("hmdlcfg-job-poll", "disabled"),
    Output("hmdlcfg-run-msg", "children"),
    Input("hmdlcfg-run", "n_clicks"),
    State("hmdlcfg-run-dryrun", "checked"),
    prevent_initial_call=True,
)
def _run_cb(_n, dryrun):
    try:
        res = api.launch_hmdl_awx_job({"dry_run": True} if dryrun else None)
        job_id = res.get("job_id")
        ignored = res.get("ignored_fields") or {}
        if "extra_vars" in ignored:
            # AWX drops launch-time extra_vars unless the JT has
            # ask_variables_on_launch ("Prompt on launch" for Variables) set —
            # the job is running WITHOUT the dry_run override.
            msg = dmc.Alert(
                color="yellow",
                title=f"Çalıştırıldı — job #{job_id} (override YOKSAYILDI)",
                children="AWX job template'inde Variables için 'Prompt on launch' işaretli değil; "
                         "dry_run override uygulanmadı, iş kayıtlı extra_vars ile çalışıyor.",
            )
        else:
            msg = dmc.Alert(color="blue", title=f"Çalıştırıldı — job #{job_id}")
        return {"job_id": job_id}, False, msg
    except Exception as exc:  # noqa: BLE001
        return dash.no_update, True, dmc.Alert(color="red", title="Çalıştırma başarısız", children=str(exc))


@callback(
    Output("hmdlcfg-run-msg", "children", allow_duplicate=True),
    Output("hmdlcfg-job-poll", "disabled", allow_duplicate=True),
    Input("hmdlcfg-job-poll", "n_intervals"),
    State("hmdlcfg-job-store", "data"),
    prevent_initial_call=True,
)
def _poll_cb(_n, store):
    job_id = (store or {}).get("job_id")
    if not job_id:
        return dash.no_update, True
    job = api.get_hmdl_awx_job(int(job_id))
    status = job.get("status") or "unknown"
    done = status in ("successful", "failed", "error", "canceled")
    color = "green" if status == "successful" else ("red" if status in ("failed", "error") else "blue")
    return dmc.Alert(color=color, title=f"job #{job_id}: {status}"), bool(done)


@callback(
    Output("hmdlcfg-sched-msg", "children"),
    Input({"type": "hmdlcfg-sched", "sid": dash.ALL}, "checked"),
    State({"type": "hmdlcfg-sched", "sid": dash.ALL}, "id"),
    prevent_initial_call=True,
)
def _sched_cb(checked_values, ids):
    trig = ctx.triggered_id
    if not isinstance(trig, dict) or trig.get("type") != "hmdlcfg-sched":
        return dash.no_update
    sid = trig.get("sid")
    # find the new value for the triggered switch
    new_val = None
    for cid, val in zip(ids or [], checked_values or []):
        if cid.get("sid") == sid:
            new_val = bool(val)
            break
    try:
        api.set_hmdl_awx_schedule(int(sid), bool(new_val))
        return dmc.Alert(color="green", title=f"Schedule #{sid} güncellendi ({'enabled' if new_val else 'disabled'}).")
    except Exception as exc:  # noqa: BLE001
        return dmc.Alert(color="red", title="Schedule güncelleme başarısız", children=str(exc))
