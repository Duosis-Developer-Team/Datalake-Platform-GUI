"""Integrations — CRM customer source mappings (gui_crm_customer_source_mapping).

Slide-in edit panel (Users/Teams pattern) + searchable paginated html.Table.
"""
from __future__ import annotations

import dash_mantine_components as dmc
from dash import dcc, html
from dash_iconify import DashIconify

from src.services import api_client as api
from src.utils.crm_source_mapping_ui import (
    DEFAULT_ALIAS_TABLE_PAGE_SIZE,
    MATCH_METHOD_OPTIONS,
    UI_COLUMNS,
    aliases_to_table_rows,
    compute_summary,
    filter_alias_table_rows,
    page_count_for_rows,
    paginate_alias_table_rows,
)
from src.utils.ui_tokens import ON_SURFACE

TABLE_PAGE_SIZE = DEFAULT_ALIAS_TABLE_PAGE_SIZE
_STATUS_COLORS = {
    "configured": "teal",
    "seed": "blue",
    "empty": "gray",
}
_SECTION_ROW_STYLE = {"transition": "opacity 0.15s ease-in-out"}


def summary_strip(aliases: list[dict]) -> dmc.Group:
    stats = compute_summary(aliases)
    return dmc.Group(
        gap="xs",
        mb="md",
        children=[
            dmc.Badge(f"Total: {stats['total']}", color="indigo", variant="light", size="lg"),
            dmc.Badge(f"Configured: {stats['configured']}", color="teal", variant="light", size="lg"),
            dmc.Badge(f"Empty: {stats['empty']}", color="gray", variant="light", size="lg"),
            dmc.Badge(
                f"Boyner mappings: {stats['boyner_mappings']}",
                color="blue" if stats["boyner_mappings"] else "gray",
                variant="light",
                size="lg",
            ),
        ],
    )


def _filled_mapping_count(entries: list[dict]) -> int:
    return len([e for e in entries if str(e.get("match_value") or "").strip()])


def _render_mapping_entry(section_key: str, data_sources: tuple[str, ...], entry: dict, index: int):
    source_options = [{"label": s, "value": s} for s in data_sources]
    return dmc.Paper(
        withBorder=True,
        p="xs",
        mb="xs",
        children=[
            dmc.Group(
                gap="xs",
                wrap="wrap",
                align="flex-end",
                children=[
                    dmc.Select(
                        id={"type": "alias-edit-method", "section": section_key, "index": index},
                        label="Method" if index == 0 else None,
                        data=MATCH_METHOD_OPTIONS,
                        value=entry.get("match_method") or "contains",
                        size="xs",
                        style={"minWidth": "120px", "flex": 1},
                    ),
                    dmc.TextInput(
                        id={"type": "alias-edit-value", "section": section_key, "index": index},
                        label="Value" if index == 0 else None,
                        value=entry.get("match_value") or "",
                        placeholder="match value",
                        size="xs",
                        style={"minWidth": "160px", "flex": 2},
                    ),
                    dmc.Select(
                        id={"type": "alias-edit-source", "section": section_key, "index": index},
                        label="Source" if index == 0 else None,
                        data=source_options,
                        value=entry.get("data_source") or data_sources[0],
                        size="xs",
                        style={"minWidth": "140px", "flex": 1},
                    ),
                    dmc.Switch(
                        id={"type": "alias-edit-enabled", "section": section_key, "index": index},
                        label="On",
                        checked=bool(entry.get("enabled", True)),
                        size="xs",
                    ),
                    dmc.ActionIcon(
                        DashIconify(icon="tabler:trash", width=16),
                        id={"type": "alias-edit-remove", "section": section_key, "index": index},
                        color="red",
                        variant="light",
                        size="sm",
                    ),
                ],
            ),
        ],
    )


def render_section_rows(section_key: str, data_sources: tuple[str, ...], entries: list[dict]) -> list:
    return [
        _render_mapping_entry(section_key, data_sources, entry, idx)
        for idx, entry in enumerate(entries)
    ]


def section_refresh_outputs(editor_state: dict | None) -> tuple[list, list]:
    sections = (editor_state or {}).get("sections") or {}
    rows_out: list = []
    counts_out: list = []
    for column_key, _label, data_sources in UI_COLUMNS:
        entries = sections.get(column_key) or []
        rows_out.append(render_section_rows(column_key, data_sources, entries))
        counts_out.append(str(_filled_mapping_count(entries)))
    return rows_out, counts_out


def build_editor_shell(editor_state: dict | None, *, open_sections: list[str] | None = None) -> html.Div:
    if not editor_state:
        return html.Div(
            children=dmc.Alert(
                color="blue",
                title="No customer selected",
                children="Click Edit mappings on a customer row to configure source rules.",
            )
        )

    sections = editor_state.get("sections") or {}
    initial_rows, initial_counts = section_refresh_outputs(editor_state)
    accordion_value = list(open_sections) if open_sections else [UI_COLUMNS[0][0]]

    accordion_items = []
    for idx, (column_key, label, _data_sources) in enumerate(UI_COLUMNS):
        accordion_items.append(
            dmc.AccordionItem(
                value=column_key,
                children=[
                    dmc.AccordionControl(
                        dmc.Group(
                            gap="xs",
                            children=[
                                dmc.Text(label, fw=600, size="sm"),
                                dmc.Badge(
                                    id={"type": "alias-section-count", "section": column_key},
                                    children=initial_counts[idx],
                                    color="gray",
                                    size="sm",
                                ),
                            ],
                        )
                    ),
                    dmc.AccordionPanel(
                        dmc.Stack(
                            gap="xs",
                            children=[
                                html.Div(
                                    id={"type": "alias-section-rows", "section": column_key},
                                    style=_SECTION_ROW_STYLE,
                                    children=initial_rows[idx],
                                ),
                                dmc.Button(
                                    "Add mapping",
                                    id={"type": "alias-edit-add", "section": column_key},
                                    size="xs",
                                    variant="light",
                                    color="gray",
                                    mt="xs",
                                ),
                            ],
                        )
                    ),
                ],
            )
        )

    return html.Div(
        children=[
            dmc.Group(
                justify="flex-end",
                gap="xs",
                mb="sm",
                children=[
                    dmc.Button("Reset", id="alias-edit-reset", size="xs", variant="subtle", color="gray"),
                    dmc.Button("Save mappings", id="alias-edit-save", size="xs", color="indigo"),
                ],
            ),
            dmc.TextInput(
                id="alias-edit-notes",
                label="Notes",
                value=editor_state.get("notes") or "",
                size="xs",
                mb="md",
                placeholder="Optional operator notes",
            ),
            dmc.Accordion(
                id="alias-editor-accordion",
                multiple=True,
                value=accordion_value,
                children=accordion_items,
            ),
        ]
    )


def render_editor_panel(editor_state: dict | None) -> html.Div:
    """Backward-compatible alias for build_editor_shell."""
    return build_editor_shell(editor_state)


def _status_badge(status: str) -> dmc.Badge:
    return dmc.Badge(
        str(status or "empty"),
        color=_STATUS_COLORS.get(str(status or "").lower(), "gray"),
        variant="light",
        size="xs",
    )


def build_table_body_rows(rows: list[dict]) -> list[html.Tr]:
    body: list[html.Tr] = []
    for row in rows or []:
        account_id = str(row.get("crm_accountid") or "")
        body.append(
            html.Tr(
                style={"borderBottom": "1px solid #eef1f4"},
                children=[
                    html.Td(str(row.get("crm_account_name") or "-")),
                    html.Td(str(row.get("account_id_short") or "")),
                    html.Td(str(row.get("mapping_count") or 0)),
                    html.Td(str(row.get("coverage") or "")),
                    html.Td(_status_badge(str(row.get("status") or "empty"))),
                    html.Td(
                        dmc.Button(
                            "Edit mappings",
                            id={"type": "alias-edit-open", "account": account_id},
                            size="xs",
                            variant="light",
                            color="indigo",
                        )
                    ),
                ],
            )
        )
    if not body:
        body.append(
            html.Tr(
                children=html.Td(
                    dmc.Text("No customers match the current filter.", size="sm", c="dimmed"),
                    colSpan=6,
                    style={"padding": "16px"},
                )
            )
        )
    return body


def visible_table_rows(page_data: list[dict], query: str, page: int) -> tuple[list[dict], int]:
    all_rows = aliases_to_table_rows(page_data or [])
    filtered = filter_alias_table_rows(all_rows, query)
    pages = page_count_for_rows(len(filtered), TABLE_PAGE_SIZE)
    safe_page = min(max(int(page or 0), 0), pages - 1)
    return paginate_alias_table_rows(filtered, safe_page, TABLE_PAGE_SIZE), pages


def _th():
    return {
        "textAlign": "left",
        "padding": "12px 16px",
        "borderBottom": "1px solid #e9ecef",
        "color": "#2B3674",
        "fontSize": "11px",
        "textTransform": "uppercase",
    }


def build_layout(search: str | None = None) -> html.Div:
    _ = search
    aliases = api.get_crm_aliases()
    initial_rows, initial_pages = visible_table_rows(aliases, "", 0)
    all_count = len(aliases_to_table_rows(aliases))
    initial_label = (
        f"Showing 1-{len(initial_rows)} of {all_count}"
        if all_count
        else "No matches"
    )

    if not aliases:
        empty_block = dmc.Alert(
            color="yellow",
            title="No CRM project customers",
            children="Customer list comes from CRM PRJ-* sales orders. Verify customer-api connectivity.",
        )
    else:
        empty_block = dmc.Text(
            "Search by customer name, then click Edit mappings to open the slide-in editor.",
            size="sm",
            c="dimmed",
            mb="sm",
        )

    slide_panel = html.Div(
        id="alias-slide-panel",
        className="alias-slide-panel closed",
        style={"alignSelf": "stretch"},
        children=[
            dmc.Paper(
                p="lg",
                radius="md",
                withBorder=True,
                style={"minWidth": "480px", "maxHeight": "calc(100vh - 220px)", "overflowY": "auto"},
                children=[
                    dmc.Group(
                        justify="space-between",
                        align="center",
                        mb="md",
                        wrap="nowrap",
                        children=[
                            dmc.Stack(
                                gap=2,
                                style={"minWidth": 0},
                                children=[
                                    dmc.Text(
                                        id="alias-panel-title",
                                        children="Edit mappings",
                                        fw=700,
                                        c=ON_SURFACE,
                                        lineClamp=2,
                                    ),
                                    dmc.Text(
                                        id="alias-panel-subtitle",
                                        children="",
                                        size="xs",
                                        c="dimmed",
                                    ),
                                ],
                            ),
                            dmc.ActionIcon(
                                DashIconify(icon="solar:close-circle-bold", width=22),
                                id="alias-panel-close",
                                variant="subtle",
                                color="gray",
                                radius="xl",
                            ),
                        ],
                    ),
                    html.Div(id="alias-editor-panel", children=build_editor_shell(None)),
                ],
            ),
        ],
    )

    table_paper = dmc.Paper(
        p=0,
        radius="md",
        withBorder=True,
        style={"flex": "1", "minWidth": 0},
        children=[
            html.Div(
                style={"padding": "16px 20px", "borderBottom": "1px solid #eef1f4"},
                children=[
                    dmc.Group(
                        justify="space-between",
                        align="flex-end",
                        wrap="wrap",
                        gap="sm",
                        children=[
                            dmc.TextInput(
                                id="alias-table-search",
                                placeholder="Search customer name…",
                                leftSection=DashIconify(icon="solar:magnifer-linear", width=16, color="#A3AED0"),
                                size="sm",
                                style={"width": "min(320px, 100%)"},
                            ),
                            dmc.Text(
                                id="alias-table-count",
                                size="xs",
                                c="dimmed",
                                children=f"{len(aliases)} customer(s)",
                            ),
                        ],
                    ),
                ],
            ),
            html.Div(
                style={"overflowX": "auto"},
                children=[
                    html.Table(
                        style={"width": "100%", "borderCollapse": "collapse", "fontSize": "13px"},
                        children=[
                            html.Thead(
                                html.Tr(
                                    [
                                        html.Th("CRM Account", style=_th()),
                                        html.Th("Account ID", style=_th()),
                                        html.Th("Mappings", style=_th()),
                                        html.Th("Coverage", style=_th()),
                                        html.Th("Status", style=_th()),
                                        html.Th("Actions", style=_th()),
                                    ]
                                )
                            ),
                            html.Tbody(
                                id="alias-table-body",
                                children=build_table_body_rows(initial_rows),
                            ),
                        ],
                    ),
                ],
            ),
            dmc.Group(
                justify="space-between",
                p="sm",
                children=[
                    dmc.Text(id="alias-table-page-label", size="xs", c="dimmed", children=initial_label),
                    dmc.Pagination(
                        id="alias-table-pagination",
                        total=max(initial_pages, 1),
                        value=1,
                        size="sm",
                    ),
                ],
            ),
        ],
    )

    body_row = html.Div(
        style={"display": "flex", "gap": "24px", "alignItems": "flex-start", "width": "100%"},
        children=[slide_panel, table_paper],
    )

    return html.Div(
        style={"padding": "30px"},
        children=[
            dmc.Group(
                gap="sm",
                mb="lg",
                children=[
                    dmc.ThemeIcon(
                        size="xl",
                        variant="light",
                        color="teal",
                        radius="md",
                        children=DashIconify(icon="solar:link-circle-bold-duotone", width=28),
                    ),
                    dmc.Stack(
                        gap=0,
                        children=[
                            dmc.Text("Customer source mappings", fw=700, size="xl", c="#2B3674"),
                            dmc.Text(
                                "Browse CRM project customers and edit source mappings per account.",
                                size="sm",
                                c="#A3AED0",
                            ),
                        ],
                    ),
                    dmc.Button(
                        "Seed Boyner defaults",
                        id="alias-seed-boyner-btn",
                        color="teal",
                        variant="light",
                        ml="auto",
                    ),
                ],
            ),
            summary_strip(aliases),
            html.Div(id="alias-feedback", style={"marginBottom": "12px"}),
            empty_block,
            body_row,
            dcc.Store(id="alias-page-data", data=aliases),
            dcc.Store(id="alias-editor-state", data=None),
            dcc.Store(id="alias-panel-store", data={"open": False, "crm_accountid": None}),
            dcc.Store(id="alias-editor-open-sections", data=[UI_COLUMNS[0][0]]),
            dcc.Store(id="alias-table-page", data=0),
        ],
    )
