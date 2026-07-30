"""Platform — Backup Mapping (NetBackup Image/App, Veeam/Zerto separators, multipliers).

Seeded from packaged YAML under ``shared/backup/``. Persist / DB override is not
wired yet; MultiSelects and pattern tables are editable in the UI for review but
Save actions stay disabled until a backend lands (ADR-0030).
"""
from __future__ import annotations

from typing import Any

from dash import dash_table, html
import dash_mantine_components as dmc
from dash_iconify import DashIconify

from shared.backup.policy_classification import load_policy_panel_mapping
from shared.backup.replica_classifier import load_replica_patterns
from src.utils.ui_tokens import card_style, section_header, settings_page_shell


_SNAPSHOT_TABLE_ID = "pbm-snapshot-table"
_VEEAM_TABLE_ID = "pbm-veeam-patterns-table"
_ZERTO_TABLE_ID = "pbm-zerto-patterns-table"
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
                            dmc.Text(
                                "NetBackup policy types rendered under Backup Image "
                                "(CRM inventory / efficiency image basis).",
                                size="xs",
                                c="dimmed",
                                mb="sm",
                            ),
                            dmc.MultiSelect(
                                id="pbm-image-policy-types",
                                label="image_policy_types",
                                data=options,
                                value=image_values,
                                searchable=True,
                                clearable=True,
                                size="sm",
                                placeholder="Select policy types…",
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
                            dmc.Text(
                                "Documentary / UI seed list. Runtime classification still "
                                "treats any type not in Image as Application.",
                                size="xs",
                                c="dimmed",
                                mb="sm",
                            ),
                            dmc.MultiSelect(
                                id="pbm-application-policy-types",
                                label="application_policy_types",
                                data=options,
                                value=app_values,
                                searchable=True,
                                clearable=True,
                                size="sm",
                                placeholder="Select policy types…",
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


def _vendor_panel(
    *,
    vendor: str,
    title: str,
    description: str,
    patterns: dict[str, Any],
    table_id: str,
) -> html.Div:
    vendor_cfg = (patterns.get("vendor_reconciliation") or {}).get(vendor) or {}
    metric = str(vendor_cfg.get("metric") or "—")
    vendor_desc = str(vendor_cfg.get("description") or description)
    replica_rows = _pattern_rows(patterns.get("replica_patterns"))
    silinecek_rows = _pattern_rows(patterns.get("silinecek"))
    styles = _table_style()

    return html.Div(
        [
            dmc.Alert(
                f"{vendor_desc} Metric key: ``{metric}``. "
                "Patterns are the shared YAML seed from ``replica_patterns.yaml``; "
                "DB override is not wired yet.",
                title=f"{title} separator seed",
                color="violet",
                variant="light",
                mb="md",
            ),
            dmc.Paper(
                **card_style(),
                mb="md",
                children=[
                    dmc.Title("Exclude before replica (silinecek)", order=5, mb="xs"),
                    dmc.Text(
                        "Matched names are excluded from billable and replica pools.",
                        size="xs",
                        c="dimmed",
                        mb="sm",
                    ),
                    dash_table.DataTable(
                        id=f"{_SILINECEK_TABLE_ID}-{vendor}",
                        data=silinecek_rows,
                        columns=_pattern_columns(),
                        page_size=10,
                        **styles,
                    ),
                ],
            ),
            dmc.Paper(
                **card_style(),
                children=[
                    dmc.Title("DR / replica name patterns", order=5, mb="xs"),
                    dmc.Text(
                        "Any match classifies the VM into the replica resource pool "
                        f"(shared seed; {title} counter used for reconciliation).",
                        size="xs",
                        c="dimmed",
                        mb="sm",
                    ),
                    dash_table.DataTable(
                        id=table_id,
                        data=replica_rows,
                        columns=_pattern_columns(),
                        page_size=20,
                        filter_action="native",
                        sort_action="native",
                        **styles,
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
                "Nothing is persisted yet — inputs are inert and Save is disabled. "
                "Backend will follow the Resource ratios / calc-config pattern.",
                title="Platform multipliers — preview only",
                color="orange",
                variant="light",
                mb="md",
            ),
            dmc.Paper(
                **card_style(),
                mb="md",
                children=[
                    dmc.Group(
                        justify="space-between",
                        mb="sm",
                        children=[
                            dmc.Title("Add / update multiplier", order=5),
                            dmc.Button(
                                "Reset form",
                                id="pbm-bkp-reset",
                                size="xs",
                                variant="subtle",
                                color="gray",
                                disabled=True,
                            ),
                        ],
                    ),
                    dmc.Grid(
                        gutter="sm",
                        children=[
                            dmc.GridCol(
                                span={"base": 12, "md": 3},
                                children=dmc.TextInput(
                                    id="pbm-bkp-family",
                                    label="family",
                                    size="xs",
                                    placeholder="virt_hyperconverged",
                                    disabled=True,
                                ),
                            ),
                            dmc.GridCol(
                                span={"base": 12, "md": 2},
                                children=dmc.TextInput(
                                    id="pbm-bkp-dc",
                                    label="dc_code",
                                    size="xs",
                                    value="*",
                                    disabled=True,
                                ),
                            ),
                            dmc.GridCol(
                                span={"base": 12, "md": 3},
                                children=dmc.NumberInput(
                                    id="pbm-bkp-multiplier",
                                    label="snapshot multiplier",
                                    size="xs",
                                    value=1.0,
                                    min=0,
                                    step=0.1,
                                    disabled=True,
                                ),
                            ),
                            dmc.GridCol(
                                span={"base": 12, "md": 2},
                                children=dmc.Button(
                                    "Save",
                                    id="pbm-bkp-save",
                                    size="xs",
                                    disabled=True,
                                ),
                            ),
                            dmc.GridCol(
                                span={"base": 12, "md": 12},
                                children=dmc.TextInput(
                                    id="pbm-bkp-notes",
                                    label="notes",
                                    size="xs",
                                    disabled=True,
                                ),
                            ),
                        ],
                    ),
                ],
            ),
            dmc.Paper(
                **card_style(),
                children=[
                    dmc.Title("Nutanix snapshot sources", order=5, mb="xs"),
                    dmc.Text(
                        "Columns are a proposal. No snapshot query is wired yet.",
                        size="xs",
                        c="dimmed",
                        mb="sm",
                    ),
                    dash_table.DataTable(
                        id=_SNAPSHOT_TABLE_ID,
                        data=[],
                        columns=[
                            {"name": "family", "id": "family"},
                            {"name": "dc_code", "id": "dc_code"},
                            {"name": "snapshots", "id": "snapshots", "type": "numeric"},
                            {"name": "raw_gb", "id": "raw_gb", "type": "numeric"},
                            {"name": "multiplier", "id": "multiplier", "type": "numeric"},
                            {"name": "updated_by", "id": "updated_by"},
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


def build_layout(search: str | None = None) -> html.Div:
    _ = search
    mapping = load_policy_panel_mapping()
    patterns = load_replica_patterns()

    return html.Div(
        settings_page_shell(
            [
                section_header(
                    "Backup Mapping",
                    "Platform controls for NetBackup Image vs Application policy mapping, "
                    "Veeam / Zerto replica separators, and Nutanix snapshot multipliers.",
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
                                        dmc.TabsTab(
                                            dmc.Group(
                                                gap=6,
                                                children=[
                                                    DashIconify(
                                                        icon="solar:layers-minimalistic-bold-duotone",
                                                        width=16,
                                                    ),
                                                    "Image vs Application",
                                                ],
                                            ),
                                            value="image-app",
                                        ),
                                        dmc.TabsTab(
                                            dmc.Group(
                                                gap=6,
                                                children=[
                                                    DashIconify(
                                                        icon="solar:server-square-cloud-bold-duotone",
                                                        width=16,
                                                    ),
                                                    "Veeam separator",
                                                ],
                                            ),
                                            value="veeam",
                                        ),
                                        dmc.TabsTab(
                                            dmc.Group(
                                                gap=6,
                                                children=[
                                                    DashIconify(
                                                        icon="solar:restart-bold-duotone",
                                                        width=16,
                                                    ),
                                                    "Zerto separator",
                                                ],
                                            ),
                                            value="zerto",
                                        ),
                                        dmc.TabsTab(
                                            dmc.Group(
                                                gap=6,
                                                children=[
                                                    DashIconify(
                                                        icon="solar:chart-bold-duotone",
                                                        width=16,
                                                    ),
                                                    "Multipliers",
                                                ],
                                            ),
                                            value="multipliers",
                                        ),
                                    ]
                                ),
                                dmc.TabsPanel(
                                    value="image-app",
                                    pt="md",
                                    children=_image_app_panel(mapping),
                                ),
                                dmc.TabsPanel(
                                    value="veeam",
                                    pt="md",
                                    children=_vendor_panel(
                                        vendor="veeam",
                                        title="Veeam",
                                        description=(
                                            "Compare replica pool size to Veeam "
                                            "VSphereReplica object counts."
                                        ),
                                        patterns=patterns,
                                        table_id=_VEEAM_TABLE_ID,
                                    ),
                                ),
                                dmc.TabsPanel(
                                    value="zerto",
                                    pt="md",
                                    children=_vendor_panel(
                                        vendor="zerto",
                                        title="Zerto",
                                        description=(
                                            "Compare replica pool size to Zerto VPG VM counts."
                                        ),
                                        patterns=patterns,
                                        table_id=_ZERTO_TABLE_ID,
                                    ),
                                ),
                                dmc.TabsPanel(
                                    value="multipliers",
                                    pt="md",
                                    children=_multipliers_panel(),
                                ),
                            ],
                        ),
                    ],
                ),
            ]
        )
    )
