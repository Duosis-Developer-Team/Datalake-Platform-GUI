"""Platform — Backup Mapping (NetBackup Image/App, name-pattern buckets, multipliers).

Seeded from packaged YAML under ``shared/backup/``. Persist / DB override is not
wired yet; pattern tables are editable in the UI for review but Save actions
stay disabled until a backend lands.
"""
from __future__ import annotations

from typing import Any

from dash import dash_table, html
import dash_mantine_components as dmc
from dash_iconify import DashIconify

from shared.backup.policy_classification import load_policy_panel_mapping
from shared.backup.replica_classifier import load_replica_patterns, load_veeam_session_mapping
from src.utils.ui_tokens import card_style, section_header, settings_page_shell


_SNAPSHOT_TABLE_ID = "pbm-snapshot-table"
_VEEAM_DR_TABLE_ID = "pbm-veeam-dr-patterns-table"
_ALTRA_TABLE_ID = "pbm-altra-patterns-table"
_CUSTOM_TABLE_ID = "pbm-custom-patterns-table"
_SILINECEK_TABLE_ID = "pbm-silinecek-table"


def _policy_options(mapping: dict[str, Any]) -> list[dict[str, str]]:
    """Union of image + application policy types for MultiSelect data."""
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for key in ("image_policy_types", "application_policy_types"):
        for pt in mapping.get(key) or []:
            text = str(pt).strip()
            if not text or text.upper() in seen:
                continue
            seen.add(text.upper())
            out.append({"value": text, "label": text})
    return out


def _pattern_rows(rules: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rule in rules or []:
        if not isinstance(rule, dict):
            continue
        rows.append(
            {
                "id": str(rule.get("id") or ""),
                "match": str(rule.get("match") or "contains"),
                "value": str(rule.get("value") or ""),
                "case_insensitive": "yes" if rule.get("case_insensitive", True) else "no",
            }
        )
    return rows


def _table_style() -> dict[str, Any]:
    return {
        "style_table": {"overflowX": "auto"},
        "style_cell": {"fontSize": "12px", "padding": "6px 8px", "textAlign": "left"},
        "style_header": {
            "backgroundColor": "#F4F7FE",
            "color": "#2B3674",
            "fontWeight": "700",
            "border": "none",
        },
    }


def _pattern_columns() -> list[dict[str, str]]:
    return [
        {"name": "id", "id": "id"},
        {"name": "match", "id": "match"},
        {"name": "value", "id": "value"},
        {"name": "case_insensitive", "id": "case_insensitive"},
    ]


def _pattern_table_paper(
    *,
    title: str,
    description: str,
    table_id: str,
    rows: list[dict[str, Any]],
    editable: bool = True,
) -> dmc.Paper:
    styles = _table_style()
    return dmc.Paper(
        **card_style(),
        mb="md",
        children=[
            dmc.Title(title, order=5, mb="xs"),
            dmc.Text(description, size="xs", c="dimmed", mb="sm"),
            dash_table.DataTable(
                id=table_id,
                data=rows,
                columns=_pattern_columns(),
                page_size=20,
                filter_action="native",
                sort_action="native",
                editable=editable,
                row_deletable=editable,
                **styles,
            ),
        ],
    )


def _image_app_panel(mapping: dict[str, Any]) -> html.Div:
    options = _policy_options(mapping)
    image_values = [str(t) for t in (mapping.get("image_policy_types") or [])]
    app_values = [str(t) for t in (mapping.get("application_policy_types") or [])]

    return html.Div(
        [
            dmc.Alert(
                "Values are seeded from ``shared/backup/policy_panel_mapping.yaml``. "
                "Classification rule: policy types listed under Image map to the Image "
                "panel; everything else (including unknown) maps to Application. "
                "Database overrides will replace this seed later — Save is disabled for now.",
                title="YAML seed — DB override coming later",
                color="indigo",
                variant="light",
                mb="md",
            ),
            dmc.SimpleGrid(
                cols={"base": 1, "md": 2},
                spacing="md",
                children=[
                    dmc.Paper(
                        **card_style(),
                        children=[
                            dmc.Group(
                                gap="sm",
                                mb="sm",
                                children=[
                                    DashIconify(icon="solar:gallery-bold-duotone", width=18, color="#4318FF"),
                                    dmc.Text("Image panel policy types", fw=700, size="sm", c="#2B3674"),
                                ],
                            ),
                            dmc.MultiSelect(
                                id="pbm-image-policy-types",
                                label="image_policy_types",
                                data=options,
                                value=image_values,
                                searchable=True,
                                clearable=True,
                                size="sm",
                            ),
                        ],
                    ),
                    dmc.Paper(
                        **card_style(),
                        children=[
                            dmc.Group(
                                gap="sm",
                                mb="sm",
                                children=[
                                    DashIconify(icon="solar:programming-bold-duotone", width=18, color="#4318FF"),
                                    dmc.Text("Application panel policy types", fw=700, size="sm", c="#2B3674"),
                                ],
                            ),
                            dmc.MultiSelect(
                                id="pbm-application-policy-types",
                                label="application_policy_types",
                                data=options,
                                value=app_values,
                                searchable=True,
                                clearable=True,
                                size="sm",
                            ),
                        ],
                    ),
                ],
            ),
            dmc.Group(
                justify="flex-end",
                mt="md",
                children=[
                    dmc.Button(
                        "Save mapping",
                        id="pbm-policy-save",
                        size="sm",
                        disabled=True,
                        leftSection=DashIconify(icon="solar:diskette-bold-duotone", width=16),
                    ),
                ],
            ),
        ]
    )


def _silinecek_paper(patterns: dict[str, Any]) -> dmc.Paper:
    return _pattern_table_paper(
        title="Exclude before classification (silinecek)",
        description="Matched names are excluded from billable and all replica pools.",
        table_id=_SILINECEK_TABLE_ID,
        rows=_pattern_rows(patterns.get("silinecek")),
    )


def _veeam_dr_panel(patterns: dict[str, Any]) -> html.Div:
    vendor = (patterns.get("vendor_reconciliation") or {}).get("veeam") or {}
    return html.Div(
        [
            dmc.Alert(
                str(vendor.get("description") or "")
                + " Default seeds: ``_DR``, ``_DRC``, embedded ``-dr-`` / ``_dr_``. "
                "Veeam Replica vs Backup is also split via session_type / jobs.type. "
                "Save/DB persist is not wired yet — edit the YAML seed for now.",
                title="Veeam DR name patterns (default)",
                color="violet",
                variant="light",
                mb="md",
            ),
            _silinecek_paper(patterns),
            _pattern_table_paper(
                title="Veeam DR patterns",
                description="Name matches → veeam_dr bucket (Veeam replication).",
                table_id=_VEEAM_DR_TABLE_ID,
                rows=_pattern_rows(patterns.get("veeam_dr_patterns")),
            ),
        ]
    )


def _altra_panel(patterns: dict[str, Any]) -> html.Div:
    vendor = (patterns.get("vendor_reconciliation") or {}).get("altra") or {}
    return html.Div(
        [
            dmc.Alert(
                str(vendor.get("description") or "")
                + " Default seeds: ``_replica``, ``_replika``, contains replica/replika. "
                "CRM service matching for Altra is deferred. Save disabled for now.",
                title="Altra / external replica patterns",
                color="grape",
                variant="light",
                mb="md",
            ),
            _pattern_table_paper(
                title="Altra / external replica patterns",
                description="Name matches → altra_replica bucket (external DR / Cloud Connect style).",
                table_id=_ALTRA_TABLE_ID,
                rows=_pattern_rows(patterns.get("altra_replica_patterns")),
            ),
        ]
    )


def _custom_panel(patterns: dict[str, Any]) -> html.Div:
    return html.Div(
        [
            dmc.Alert(
                "Non-standard operator patterns (e.g. ALT-TRA-DER, ALT-TRA-DISASTER). "
                "Empty by default. Add rows here when Save/DB override lands; until then "
                "edit ``replica_patterns.yaml`` custom_patterns.",
                title="Custom name patterns",
                color="orange",
                variant="light",
                mb="md",
            ),
            _pattern_table_paper(
                title="Custom patterns",
                description="Name matches → custom bucket (treated as replica-like).",
                table_id=_CUSTOM_TABLE_ID,
                rows=_pattern_rows(patterns.get("custom_patterns")),
            ),
            dmc.Group(
                justify="flex-end",
                children=[
                    dmc.Button(
                        "Save patterns",
                        id="pbm-patterns-save",
                        size="sm",
                        disabled=True,
                        leftSection=DashIconify(icon="solar:diskette-bold-duotone", width=16),
                    ),
                ],
            ),
        ]
    )


def _zerto_panel(patterns: dict[str, Any]) -> html.Div:
    vendor = (patterns.get("vendor_reconciliation") or {}).get("zerto") or {}
    return html.Div(
        [
            dmc.Alert(
                str(vendor.get("description") or "")
                + " Zerto VMs are identified from ``raw_zerto_vm_metrics`` / VPG matrix — "
                "not from VM name patterns. This tab is read-only documentation.",
                title="Zerto — vendor matrix (read-only)",
                color="blue",
                variant="light",
                mb="md",
            ),
            dmc.Paper(
                **card_style(),
                children=[
                    dmc.Title("Zerto identification", order=5, mb="xs"),
                    dmc.Text(
                        "Protected VMs come from Zerto VPG / VM metrics. "
                        "Reconcile against SUM(vmscount). Architecture (classic vs "
                        "hyperconverged) is derived from cluster / Nutanix mirror rules.",
                        size="sm",
                        c="#2B3674",
                    ),
                    dmc.Text(
                        f"Metric key: ``{vendor.get('metric') or 'vmscount'}``",
                        size="xs",
                        c="dimmed",
                        mt="sm",
                    ),
                ],
            ),
        ]
    )


def _multipliers_panel() -> html.Div:
    """Migrated from CRM Integrations Backup placeholder; labelled Platform."""
    styles = _table_style()
    return html.Div(
        [
            dmc.Alert(
                "Nutanix snapshot multipliers for Platform sellable capacity. "
                "Nothing is persisted yet — inputs are inert and Save is disabled.",
                title="Platform multipliers — preview only",
                color="orange",
                variant="light",
                mb="md",
            ),
            dmc.Paper(
                **card_style(),
                children=[
                    dmc.Title("Nutanix snapshot sources", order=5, mb="xs"),
                    dash_table.DataTable(
                        id=_SNAPSHOT_TABLE_ID,
                        data=[],
                        columns=[
                            {"name": "family", "id": "family"},
                            {"name": "dc_code", "id": "dc_code"},
                            {"name": "snapshots", "id": "snapshots", "type": "numeric"},
                            {"name": "raw_gb", "id": "raw_gb", "type": "numeric"},
                            {"name": "multiplier", "id": "multiplier", "type": "numeric"},
                        ],
                        page_size=20,
                        **styles,
                    ),
                    dmc.Text(
                        "No snapshot source is connected yet.",
                        size="sm",
                        c="dimmed",
                        ta="center",
                        py="xl",
                    ),
                ],
            ),
        ]
    )


def _veeam_session_types_panel(session_cfg: dict[str, Any]) -> html.Div:
    """Backup Configuration: Veeam session types → Replication / Image / Application."""
    rep_vals = [str(t) for t in (session_cfg.get("veeam_replication_session_types") or [])]
    img_vals = [str(t) for t in (session_cfg.get("veeam_image_backup_session_types") or [])]
    if not img_vals:
        img_vals = [str(t) for t in (session_cfg.get("veeam_backup_session_types") or [])]
    app_vals = [str(t) for t in (session_cfg.get("veeam_application_backup_session_types") or [])]
    options = sorted(
        {v for v in (rep_vals + img_vals + app_vals) if v},
        key=lambda s: s.casefold(),
    )
    data = [{"value": o, "label": o} for o in options]
    for extra in (
        "ReplicaJob", "VSphereReplica", "BackupJob", "Backup", "BackupCopyJob",
        "SqlBackup", "OracleBackup", "SapBackup", "ExchangeBackup", "ApplicationBackup",
    ):
        if extra not in {d["value"] for d in data}:
            data.append({"value": extra, "label": extra})

    return html.Div(
        [
            dmc.Alert(
                "Exact session_type / jobs.type strings listed here classify Veeam "
                "work as Replication, Image Backup, or Application Backup "
                "(DC Backup tabs). Seed: ``shared/backup/veeam_session_mapping.yaml``. "
                "Save/DB persist is disabled — edit the YAML for now.",
                title="Veeam session types — Backup Configuration",
                color="cyan",
                variant="light",
                mb="md",
            ),
            dmc.SimpleGrid(
                cols={"base": 1, "md": 3},
                spacing="md",
                children=[
                    dmc.Paper(
                        **card_style(),
                        children=[
                            dmc.Text("Replication", fw=700, size="sm", c="#2B3674", mb="sm"),
                            dmc.MultiSelect(
                                id="pbm-veeam-replication-session-types",
                                data=data,
                                value=rep_vals,
                                searchable=True,
                                clearable=True,
                                size="sm",
                                placeholder="Select replication types…",
                            ),
                        ],
                    ),
                    dmc.Paper(
                        **card_style(),
                        children=[
                            dmc.Text("Image Backup", fw=700, size="sm", c="#2B3674", mb="sm"),
                            dmc.MultiSelect(
                                id="pbm-veeam-image-backup-session-types",
                                data=data,
                                value=img_vals,
                                searchable=True,
                                clearable=True,
                                size="sm",
                                placeholder="Select image backup types…",
                            ),
                        ],
                    ),
                    dmc.Paper(
                        **card_style(),
                        children=[
                            dmc.Text("Application Backup", fw=700, size="sm", c="#2B3674", mb="sm"),
                            dmc.MultiSelect(
                                id="pbm-veeam-application-backup-session-types",
                                data=data,
                                value=app_vals,
                                searchable=True,
                                clearable=True,
                                size="sm",
                                placeholder="Select application backup types…",
                            ),
                        ],
                    ),
                ],
            ),
            dmc.Group(
                justify="flex-end",
                mt="md",
                children=[
                    dmc.Button(
                        "Save session mapping",
                        id="pbm-veeam-session-save",
                        size="sm",
                        disabled=True,
                        leftSection=DashIconify(icon="solar:diskette-bold-duotone", width=16),
                    ),
                ],
            ),
        ]
    )


def _tab(label: str, icon: str, value: str) -> dmc.TabsTab:
    return dmc.TabsTab(
        dmc.Group(
            gap=6,
            children=[
                DashIconify(icon=icon, width=16),
                label,
            ],
        ),
        value=value,
    )


def build_layout(search: str | None = None) -> html.Div:
    _ = search
    mapping = load_policy_panel_mapping()
    patterns = load_replica_patterns()
    session_cfg = load_veeam_session_mapping()

    return html.Div(
        settings_page_shell(
            [
                section_header(
                    "Backup Mapping",
                    "Platform controls for NetBackup Image vs Application, "
                    "Veeam session types (Backup Configuration), "
                    "Veeam DR / Altra / custom name patterns, Zerto matrix notes, "
                    "and Nutanix snapshot multipliers.",
                    icon="solar:cloud-storage-bold-duotone",
                ),
                dmc.Paper(
                    p="md",
                    radius="md",
                    withBorder=True,
                    style=card_style()["style"],
                    children=[
                        dmc.Tabs(
                            value="image-app",
                            children=[
                                dmc.TabsList(
                                    children=[
                                        _tab("Image vs Application", "solar:layers-minimalistic-bold-duotone", "image-app"),
                                        _tab("Veeam session types", "solar:settings-bold-duotone", "veeam-sessions"),
                                        _tab("Veeam DR patterns", "solar:server-square-cloud-bold-duotone", "veeam-dr"),
                                        _tab("Altra / external replica", "solar:global-bold-duotone", "altra"),
                                        _tab("Custom patterns", "solar:pen-new-square-bold-duotone", "custom"),
                                        _tab("Zerto (read-only)", "solar:restart-bold-duotone", "zerto"),
                                        _tab("Multipliers", "solar:chart-bold-duotone", "multipliers"),
                                    ]
                                ),
                                dmc.TabsPanel(value="image-app", pt="md", children=_image_app_panel(mapping)),
                                dmc.TabsPanel(
                                    value="veeam-sessions",
                                    pt="md",
                                    children=_veeam_session_types_panel(session_cfg),
                                ),
                                dmc.TabsPanel(value="veeam-dr", pt="md", children=_veeam_dr_panel(patterns)),
                                dmc.TabsPanel(value="altra", pt="md", children=_altra_panel(patterns)),
                                dmc.TabsPanel(value="custom", pt="md", children=_custom_panel(patterns)),
                                dmc.TabsPanel(value="zerto", pt="md", children=_zerto_panel(patterns)),
                                dmc.TabsPanel(value="multipliers", pt="md", children=_multipliers_panel()),
                            ],
                        ),
                    ],
                ),
            ]
        )
    )
