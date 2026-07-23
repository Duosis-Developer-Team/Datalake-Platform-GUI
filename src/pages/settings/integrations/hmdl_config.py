"""Integrations — HMDL netbox-zabbix AWX run & schedule configuration (Tier A).

Reads/writes only non-secret runtime variables of the AWX job template.
Secrets (DB/Zabbix/NetBox passwords, tokens, SNMP passphrases) stay in AWX
Credentials / Vault and are never shown or edited here.
"""

from __future__ import annotations

from dash import dcc, html
import dash_mantine_components as dmc

from src.services import api_client as api

_PATH = "/administration/integrations/hmdl/config"

_SOURCE_OPTS = [{"value": "loki", "label": "loki (NetBox)"}, {"value": "datalake", "label": "datalake (Postgres)"}]

# section, key, kind, label. kind ∈ {"select","switch","number","text","tags"}
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
    {"section": "Log & e-posta", "key": "mail_recipients", "kind": "tags", "label": "mail_recipients"},
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
    if kind == "tags":
        # dash-mantine-components 0.14.1 has no dmc.TagsInput; adapted to
        # dmc.MultiSelect seeded with the current values as its option list
        # (so prefilled recipients render as removable chips) while keeping
        # the same list[str] value contract a TagsInput would have produced.
        vals = val if isinstance(val, list) else ([val] if val else [])
        str_vals = [str(v) for v in vals]
        return dmc.MultiSelect(
            id={"type": "hmdlcfg-val", "key": key},
            label=label,
            data=[{"value": v, "label": v} for v in str_vals],
            value=str_vals,
            searchable=True,
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
