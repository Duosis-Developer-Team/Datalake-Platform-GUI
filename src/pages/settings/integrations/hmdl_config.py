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

# section, key, kind, label. kind ∈ {"select","switch","number","text","csvlist"}
FIELD_SPECS: list[dict] = [
    # Source routing
    {"section": "Kaynak yönlendirme", "key": "device_source", "kind": "select", "label": "device_source", "opts": _SOURCE_OPTS},
    {"section": "Kaynak yönlendirme", "key": "platform_source", "kind": "select", "label": "platform_source", "opts": _SOURCE_OPTS},
    {"section": "Kaynak yönlendirme", "key": "virtual_fw_source", "kind": "select", "label": "virtual_fw_source", "opts": _SOURCE_OPTS},
    # Sync scope
    {"section": "Sync kapsamı", "key": "sync_devices", "kind": "switch", "label": "sync_devices"},
    {"section": "Sync kapsamı", "key": "sync_platforms", "kind": "switch", "label": "sync_platforms"},
    {"section": "Sync kapsamı", "key": "sync_virtual_fws", "kind": "switch", "label": "sync_virtual_fws"},
    {"section": "Sync kapsamı", "key": "report_izlenmeyecek", "kind": "switch", "label": "report_izlenmeyecek"},
    {"section": "Sync kapsamı", "key": "create_devices_disabled", "kind": "switch", "label": "create_devices_disabled"},
    {"section": "Sync kapsamı", "key": "create_platforms_disabled", "kind": "switch", "label": "create_platforms_disabled"},
    {"section": "Sync kapsamı", "key": "create_virtual_fws_disabled", "kind": "switch", "label": "create_virtual_fws_disabled"},
    # Execution
    {"section": "Çalıştırma", "key": "dry_run", "kind": "switch", "label": "dry_run"},
    {"section": "Çalıştırma", "key": "only_fetch", "kind": "switch", "label": "only_fetch"},
    {"section": "Çalıştırma", "key": "debug_mode", "kind": "switch", "label": "debug_mode"},
    {"section": "Çalıştırma", "key": "parallel_compare_ignore_errors", "kind": "switch", "label": "parallel_compare_ignore_errors"},
    {"section": "Çalıştırma", "key": "device_limit", "kind": "number", "label": "device_limit (0=limitsiz)"},
    {"section": "Çalıştırma", "key": "parallel_compare_workers", "kind": "number", "label": "parallel_compare_workers"},
    {"section": "Çalıştırma", "key": "location_filter", "kind": "text", "label": "location_filter"},
    # Logging + email
    {"section": "Log & e-posta", "key": "hmdl_log_enabled", "kind": "switch", "label": "hmdl_log_enabled"},
    {"section": "Log & e-posta", "key": "mail_recipients", "kind": "csvlist", "label": "mail_recipients (virgülle ayır)"},
    {"section": "Log & e-posta", "key": "mail_from", "kind": "text", "label": "mail_from"},
    # Endpoints (no passwords)
    {"section": "Bağlantı adresleri (parolasız)", "key": "zabbix_url", "kind": "text", "label": "zabbix_url"},
    {"section": "Bağlantı adresleri (parolasız)", "key": "netbox_url", "kind": "text", "label": "netbox_url"},
    {"section": "Bağlantı adresleri (parolasız)", "key": "discovery_db_host", "kind": "text", "label": "discovery_db_host"},
    {"section": "Bağlantı adresleri (parolasız)", "key": "discovery_db_port", "kind": "text", "label": "discovery_db_port"},
    {"section": "Bağlantı adresleri (parolasız)", "key": "discovery_db_name", "kind": "text", "label": "discovery_db_name"},
]


def _build_field(spec: dict, current: dict):
    key = spec["key"]
    kind = spec["kind"]
    label = spec["label"]
    val = current.get(key)
    if kind == "switch":
        return dmc.Switch(
            id={"type": "hmdlcfg-bool", "key": key},
            label=label,
            checked=bool(val),
            size="sm",
        )
    if kind == "select":
        return dmc.Select(
            id={"type": "hmdlcfg-val", "key": key},
            label=label,
            data=spec["opts"],
            value=str(val) if val is not None else None,
            size="xs",
        )
    if kind == "number":
        return dmc.NumberInput(
            id={"type": "hmdlcfg-val", "key": key},
            label=label,
            value=int(val) if isinstance(val, (int, float)) else 0,
            min=0,
            size="xs",
        )
    if kind == "csvlist":
        # dash-mantine-components 0.14.1 has no dmc.TagsInput/creatable
        # MultiSelect, and a MultiSelect seeded only from existing values
        # can't accept a brand-new address. Use a plain comma-delimited
        # TextInput instead; Task 7's callback splits it back into a list.
        vals = val if isinstance(val, list) else ([val] if val else [])
        return dmc.TextInput(
            id={"type": "hmdlcfg-val", "key": key},
            label=label,
            value=", ".join(str(v) for v in vals),
            size="xs",
        )
    # text
    return dmc.TextInput(
        id={"type": "hmdlcfg-val", "key": key},
        label=label,
        value="" if val is None else str(val),
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

    banner = None
    if not available:
        banner = dmc.Alert(
            color="yellow",
            title="AWX yapılandırılmadı",
            children="hmdl-api'de AWX_API_URL / AWX_TOKEN / AWX_NETBOX_ZABBIX_JT_ID ayarlanınca "
                     "değişkenler ve schedule buradan yönetilebilecek. Ekran salt görünümde.",
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
            # job-status polling plumbing (callbacks in Task 7)
            dcc.Store(id="hmdlcfg-job-store"),
            dcc.Interval(id="hmdlcfg-job-poll", interval=4000, disabled=True),
        ]
    )


_NUMERIC_KEYS = {"device_limit", "parallel_compare_workers"}


def assemble_extra_vars(val_ids, val_values, bool_ids, bool_values) -> dict:
    out: dict = {}
    for cid, value in zip(val_ids or [], val_values or []):
        key = cid.get("key")
        if not key:
            continue
        if key == "mail_recipients":
            if isinstance(value, str):
                parts = [v.strip() for v in value.split(",") if v.strip()]
            elif isinstance(value, list):
                parts = [str(v).strip() for v in value if str(v).strip()]
            else:
                parts = []
            if parts:
                out[key] = parts
            continue
        if isinstance(value, str):
            if value == "":
                continue
            out[key] = value
        elif value is None:
            continue
        elif key in _NUMERIC_KEYS:
            out[key] = int(value)
        else:
            out[key] = value
    for cid, value in zip(bool_ids or [], bool_values or []):
        key = cid.get("key")
        if key:
            out[key] = bool(value)
    return out


@callback(
    Output("hmdlcfg-save-msg", "children"),
    Input("hmdlcfg-save", "n_clicks"),
    State({"type": "hmdlcfg-val", "key": dash.ALL}, "value"),
    State({"type": "hmdlcfg-val", "key": dash.ALL}, "id"),
    State({"type": "hmdlcfg-bool", "key": dash.ALL}, "checked"),
    State({"type": "hmdlcfg-bool", "key": dash.ALL}, "id"),
    prevent_initial_call=True,
)
def _save_cb(_n, val_values, val_ids, bool_values, bool_ids):
    extra_vars = assemble_extra_vars(val_ids, val_values, bool_ids, bool_values)
    try:
        api.put_hmdl_awx_config(extra_vars)
        return dmc.Alert(color="green", title="Kaydedildi — bir sonraki (scheduled/manual) çalıştırma bunu kullanır.")
    except Exception as exc:  # noqa: BLE001
        return dmc.Alert(color="red", title="Kaydetme başarısız", children=str(exc))


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
        return {"job_id": job_id}, False, dmc.Alert(color="blue", title=f"Çalıştırıldı — job #{job_id}")
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
