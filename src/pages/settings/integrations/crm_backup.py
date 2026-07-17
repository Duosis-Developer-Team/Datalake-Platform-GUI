"""Integrations - Backup multipliers for Nutanix snapshot capacity.

PLACEHOLDER. This tab renders the intended shape only: nothing is persisted and
no snapshot data is fetched. There is no backend behind it yet -- no table, no
endpoint, no callbacks. The inputs are inert and Save is disabled on purpose, so
the panel cannot be mistaken for a working editor during a demo.

When this gets wired, the sibling tabs are the template: a typed row table plus
crm-engine endpoints (see crm_resource_ratios.py / gui_panel_resource_ratio), or
the generic gui_crm_calc_config key/value store for a handful of scalars. Any
write that feeds a computation must also invalidate the sellable cache prefixes
(api_client._invalidate_sellable_caches), otherwise SWR serves stale values.

The field set below is a proposal, not a settled contract -- confirm the real
multiplier semantics before building the backend.
"""
from __future__ import annotations

from dash import dash_table, html
import dash_mantine_components as dmc


_SNAPSHOT_TABLE_ID = "bkp-snapshot-table"


def _placeholder_badge() -> dmc.Badge:
    return dmc.Badge(
        "Placeholder - not wired",
        color="orange",
        variant="light",
        size="lg",
    )


def _empty_note(text: str) -> dmc.Text:
    return dmc.Text(text, size="sm", c="dimmed", ta="center", py="xl")


def build_layout(search: str | None = None) -> html.Div:
    return html.Div([
        dmc.Stack(gap="xs", mb="md", children=[
            dmc.Group(justify="space-between", align="center", children=[
                dmc.Title("Backup", order=3),
                _placeholder_badge(),
            ]),
            dmc.Text(
                "Nutanix snapshot multipliers. The multiplier is meant to convert raw "
                "snapshot capacity into the figure the sellable calculation consumes, "
                "the way Resource ratios constrains a family's sellable potential. "
                "dc_code='*' would be the default; per-DC rows would override it.",
                size="sm", c="dimmed",
            ),
            dmc.Alert(
                "Nothing here is connected yet. The snapshot table stays empty, the "
                "inputs do not persist, and Save is disabled. This tab exists so the "
                "shape can be reviewed before the backend is built.",
                title="Preview only",
                color="orange",
                variant="light",
            ),
        ]),

        dmc.Paper(p="md", radius="md", withBorder=True, mb="md", children=[
            dmc.Group(justify="space-between", mb="sm", children=[
                dmc.Title("Add / update multiplier", order=5),
                dmc.Button("Reset form", id="bkp-reset", size="xs", variant="subtle",
                           color="gray", disabled=True),
            ]),
            dmc.Grid(gutter="sm", children=[
                dmc.GridCol(span={"base": 12, "md": 3}, children=dmc.TextInput(
                    id="bkp-family", label="family", size="xs",
                    placeholder="virt_hyperconverged", disabled=True)),
                dmc.GridCol(span={"base": 12, "md": 2}, children=dmc.TextInput(
                    id="bkp-dc", label="dc_code", size="xs", value="*", disabled=True)),
                dmc.GridCol(span={"base": 12, "md": 3}, children=dmc.NumberInput(
                    id="bkp-multiplier", label="snapshot multiplier", size="xs",
                    value=1.0, min=0, step=0.1, disabled=True)),
                dmc.GridCol(span={"base": 12, "md": 2}, children=dmc.Button(
                    "Save", id="bkp-save", size="xs", disabled=True)),
                dmc.GridCol(span={"base": 12, "md": 12}, children=dmc.TextInput(
                    id="bkp-notes", label="notes", size="xs", disabled=True)),
            ]),
        ]),

        dmc.Paper(p="md", radius="md", withBorder=True, children=[
            dmc.Title("Nutanix snapshot sources", order=5, mb="xs"),
            dmc.Text(
                "Columns are a proposal. No snapshot query is wired, so this table "
                "stays empty by design -- it is not an outage and not an empty result.",
                size="xs", c="dimmed", mb="sm",
            ),
            dash_table.DataTable(
                id=_SNAPSHOT_TABLE_ID,
                data=[],
                columns=[
                    {"name": "family",     "id": "family"},
                    {"name": "dc_code",    "id": "dc_code"},
                    {"name": "snapshots",  "id": "snapshots",  "type": "numeric"},
                    {"name": "raw_gb",     "id": "raw_gb",     "type": "numeric"},
                    {"name": "multiplier", "id": "multiplier", "type": "numeric"},
                    {"name": "updated_by", "id": "updated_by"},
                ],
                page_size=20,
                style_table={"overflowX": "auto"},
                style_cell={"fontSize": "12px", "padding": "6px 8px", "textAlign": "left"},
                style_header={"backgroundColor": "#F4F7FE", "color": "#2B3674",
                              "fontWeight": "700", "border": "none"},
            ),
            _empty_note("No snapshot source is connected yet."),
        ]),
    ])
