"""Query Explorer — catalog, run SQL, overrides, DataTable results, and exports."""

from __future__ import annotations

import dash
import pandas as pd
from dash import html, dcc, dash_table, Input, Output, State, callback, callback_context, ALL

import dash_mantine_components as dmc
from dash_iconify import DashIconify

from src.services import api_client as api
from src.services import query_overrides as qo
from src.queries.registry import QUERY_USAGE
from src.utils.export_helpers import (
    build_report_info_df,
    csv_bytes_with_report_header,
    dash_send_csv_bytes,
    dash_send_excel_workbook,
    dataframes_to_excel_with_meta,
)
from src.utils.ui_tokens import PRIMARY, PRIMARY_END, gradient_button_style

_EM_DASH = "\u2014"


def _query_options():
    return [{"label": k, "value": k} for k in qo.list_all_query_keys()]


def _result_to_dataframe(result: dict | None) -> pd.DataFrame:
    if not result:
        return pd.DataFrame([{"info": "No result"}])
    if "error" in result:
        return pd.DataFrame([{"error": result["error"]}])
    rt = result.get("result_type", "value")
    if rt == "value":
        return pd.DataFrame([{"value": result.get("value")}])
    cols = result.get("columns") or []
    if rt == "row":
        row = result.get("data") or []
        return pd.DataFrame([{cols[i]: row[i] if i < len(row) else "" for i in range(len(cols))}])
    rows = result.get("data") or []
    out = []
    for r in rows:
        out.append({cols[i]: r[i] if i < len(r) else "" for i in range(len(cols))})
    return pd.DataFrame(out)


def _render_run_output(result: dict):
    if "error" in result:
        return dmc.Alert(result["error"], color="red", title="Error")
    rt = result.get("result_type", "value")
    if rt == "value":
        return dmc.Paper(
            p="md",
            withBorder=True,
            children=dmc.Text(str(result.get("value", "")), fw=600, size="lg"),
        )
    cols = result.get("columns") or []
    if rt == "row":
        row = result.get("data") or []
        data = [{cols[i]: row[i] if i < len(row) else None for i in range(len(cols))}]
    else:
        rows = result.get("data") or []
        data = []
        for r in rows:
            data.append({cols[i]: r[i] if i < len(r) else None for i in range(len(cols))})
    if not cols:
        return dmc.Text("No columns returned.", c="dimmed", size="sm")
    n = len(data)
    cols_dt = [{"name": c, "id": c} for c in cols]
    return dmc.Stack(
        gap="sm",
        children=[
            dmc.Text(f"Rows: {n}", size="sm", c="#A3AED0"),
            dash_table.DataTable(
                data=data,
                columns=cols_dt,
                page_size=15,
                filter_action="native",
                sort_action="native",
                style_table={"overflowX": "auto"},
                style_cell={
                    "fontFamily": "DM Sans, sans-serif",
                    "fontSize": "12px",
                    "textAlign": "left",
                    "padding": "8px",
                },
                style_header={
                    "fontWeight": "600",
                    "backgroundColor": "#f8f9fa",
                    "color": "#2B3674",
                },
            ),
        ],
    )


def layout(visible_sections=None):
    vs = visible_sections

    def qv(code: str) -> bool:
        return vs is None or code in vs

    run_panel = dmc.TabsPanel(
        value="run",
        children=[
            dmc.Text(
                "Parameters (for array_* use comma-separated values)",
                size="sm",
                c="#A3AED0",
                mb="xs",
            ),
            dmc.Group(
                [
                    dmc.TextInput(
                        id="params-input",
                        placeholder="e.g. DC11 or DC11,DC12",
                        style={"flex": 1},
                    ),
                    dmc.Button(
                        "Run",
                        id="run-button",
                        leftSection=DashIconify(icon="solar:play-circle-bold"),
                        style={
                            **gradient_button_style(),
                            "boxShadow": "0 8px 20px rgba(85, 44, 248, 0.25)",
                        },
                    ),
                ]
            ),
            dmc.Space(h=12),
            (
                dmc.Group(
                    gap="xs",
                    mb="sm",
                    children=[
                        dmc.Text("Export result", size="xs", c="dimmed", fw=600),
                        dmc.Button("CSV", id="qe-export-csv", size="xs", variant="light", color="indigo"),
                        dmc.Button("Excel", id="qe-export-xlsx", size="xs", variant="light", color="indigo"),
                        dmc.Button("PDF", id="qe-export-pdf", size="xs", variant="light", color="indigo"),
                    ],
                )
                if qv("action:qe:export")
                else html.Div()
            ),
            html.Div(
                id="run-output",
                children=dmc.Text("Select a query and click Run.", c="#A3AED0", size="sm"),
            ),
        ],
    )

    edit_panel = dmc.TabsPanel(
        value="edit",
        children=[
            dmc.Textarea(
                id="sql-editor",
                placeholder="SQL will appear when you select a query",
                minRows=12,
                mb="md",
            ),
            dmc.Group(
                [
                    dmc.Button(
                        "Save override",
                        id="save-button",
                        color="green",
                        leftSection=DashIconify(icon="solar:diskette-bold"),
                    ),
                    dmc.Button(
                        "Reset to default",
                        id="reset-button",
                        variant="light",
                        color="red",
                        leftSection=DashIconify(icon="solar:restart-bold"),
                    ),
                ]
            ),
            html.Div(id="save-status", children=[], style={"marginTop": "8px"}),
        ],
    )

    add_panel = dmc.TabsPanel(
        value="add",
        children=[
            dmc.Stack(
                [
                    dmc.TextInput(
                        id="new-query-key",
                        placeholder="Query key (e.g. custom_my_query)",
                        label="Key",
                    ),
                    dmc.Textarea(id="new-query-sql", placeholder="SELECT ...", minRows=8, label="SQL"),
                    dmc.Select(
                        id="new-result-type",
                        data=[
                            {"label": "value", "value": "value"},
                            {"label": "row", "value": "row"},
                            {"label": "rows", "value": "rows"},
                        ],
                        value="value",
                        label="Result type",
                    ),
                    dmc.Select(
                        id="new-params-style",
                        data=[
                            {"label": "wildcard", "value": "wildcard"},
                            {"label": "exact", "value": "exact"},
                            {"label": "array_wildcard", "value": "array_wildcard"},
                            {"label": "array_exact", "value": "array_exact"},
                        ],
                        value="wildcard",
                        label="Params style",
                    ),
                    dmc.Button(
                        "Add query",
                        id="add-button",
                        color="indigo",
                        leftSection=DashIconify(icon="solar:add-circle-bold"),
                    ),
                    html.Div(id="add-status", children=[], style={"marginTop": "8px"}),
                ],
                gap="md",
            ),
        ],
    )

    tabs_labels = [dmc.TabsTab("Run", value="run")]
    tab_panels: list = [run_panel]
    if qv("sec:qe:edit_sql"):
        tabs_labels.append(dmc.TabsTab("Edit SQL", value="edit"))
        tab_panels.append(edit_panel)
    if qv("sec:qe:add_query"):
        tabs_labels.append(dmc.TabsTab("Add new query", value="add"))
        tab_panels.append(add_panel)

    catalog_paper = dmc.Paper(
        p="lg",
        radius="lg",
        withBorder=True,
        shadow="sm",
        style={
            "width": "320px",
            "flexShrink": 0,
            "border": "1px solid rgba(85, 44, 248, 0.12)",
            "background": "#ffffff",
        },
        children=[
            dmc.Text("Query catalog", size="sm", fw=800, c="#2B3674", mb="xs", tt="uppercase", style={"letterSpacing": "0.04em"}),
            dmc.TextInput(
                id="query-catalog-search",
                placeholder="Search keys…",
                size="sm",
                mb="sm",
                radius="md",
            ),
            html.Div(id="query-catalog-list", children=dmc.Text("Loading…", size="sm", c="dimmed")),
        ],
    )

    hero = dmc.Paper(
        px="xl",
        py="lg",
        radius="lg",
        mb="lg",
        style={
            "marginLeft": "32px",
            "marginRight": "32px",
            "background": f"linear-gradient(135deg, #f6f2ff 0%, #ede8ff 55%, #ffffff 100%)",
            "border": "1px solid rgba(85, 44, 248, 0.12)",
        },
        children=[
            dmc.Group(
                align="flex-start",
                children=[
                    dmc.ThemeIcon(
                        DashIconify(icon="solar:code-square-bold-duotone", width=26, color="#fff"),
                        size="xl",
                        radius="md",
                        variant="filled",
                        color="indigo",
                        style={
                            "background": f"linear-gradient(135deg, {PRIMARY} 0%, {PRIMARY_END} 100%)",
                            "border": "none",
                        },
                    ),
                    dmc.Stack(
                        gap=6,
                        children=[
                            html.H1(
                                "Query Explorer",
                                style={"margin": 0, "color": "#2B3674", "fontSize": "1.75rem", "fontWeight": 900},
                            ),
                            dmc.Text(
                                "Run queries, inspect usage, and manage SQL overrides without redeploying.",
                                size="sm",
                                c="#6c757d",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )

    return html.Div([
        hero,

        dcc.Store(id="qe-result-store", data=None),
        dcc.Download(id="qe-export-download"),

        html.Div(
            style={
                "display": "flex",
                "gap": "24px",
                "alignItems": "flex-start",
                "padding": "0 32px 48px 32px",
                "flexWrap": "wrap",
            },
            children=[
                catalog_paper,
                # Right: detail + tabs
                html.Div(style={"flex": "1", "minWidth": "280px"}, children=[
                    dmc.Paper(
                        p="lg",
                        radius="lg",
                        withBorder=True,
                        shadow="sm",
                        mb="lg",
                        style={"border": "1px solid rgba(85, 44, 248, 0.1)"},
                        children=[
                            dmc.Text("Selected query", size="sm", fw=700, c="#2B3674", mb="xs"),
                            dmc.Select(
                                id="query-select",
                                data=_query_options(),
                                placeholder="Select a query",
                                clearable=False,
                                searchable=True,
                                mb="md",
                            ),
                            html.Div(id="query-metadata", children=[]),
                        ],
                    ),

                    dmc.Tabs(
                        [
                            dmc.TabsList(tabs_labels),
                            *tab_panels,
                        ],
                        value="run",
                        id="query-explorer-tabs",
                        color="indigo",
                        variant="outline",
                        radius="md",
                    ),
                ]),
            ],
        ),
    ])


@callback(
    Output("query-catalog-list", "children"),
    Input("query-catalog-search", "value"),
    Input("query-select", "options"),
)
def build_query_catalog(search, options):
    opts = options if options else _query_options()
    keys = [o["value"] for o in opts]
    q = (search or "").strip().lower()
    if q:
        keys = [k for k in keys if q in k.lower()]
    keys = sorted(keys)
    if not keys:
        return dmc.Text("No queries match.", size="sm", c="dimmed")
    return dmc.ScrollArea(
        h=480,
        offsetScrollbars=True,
        children=dmc.Stack(
            gap=6,
            children=[
                dmc.Button(
                    k,
                    variant="light",
                    size="xs",
                    justify="flex-start",
                    styles={"root": {"width": "100%", "height": "auto"}},
                    id={"type": "qe-cat", "key": k},
                    n_clicks=0,
                )
                for k in keys
            ],
        ),
    )


@callback(
    Output("query-select", "value"),
    Input({"type": "qe-cat", "key": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def catalog_pick(_n_clicks):
    if not callback_context.triggered:
        return dash.no_update
    tid = callback_context.triggered_id
    if not isinstance(tid, dict) or tid.get("type") != "qe-cat":
        return dash.no_update
    if not callback_context.triggered[0].get("value"):
        return dash.no_update
    return tid["key"]


@callback(
    Output("query-metadata", "children"),
    Output("sql-editor", "value"),
    Input("query-select", "value"),
)
def on_query_select(query_key):
    if not query_key:
        return [], ""
    entry = qo.get_merged_entry(query_key)
    if not entry:
        return [dmc.Text("Unknown query.", c="red", size="sm")], ""
    meta = [
        dmc.Text(f"Source table: {entry.get('source', _EM_DASH)}", size="sm", c="#A3AED0"),
        dmc.Text(f"Result type: {entry.get('result_type', _EM_DASH)}", size="sm", c="#A3AED0"),
        dmc.Text(f"Params style: {entry.get('params_style', _EM_DASH)}", size="sm", c="#A3AED0"),
    ]
    usage = QUERY_USAGE.get(query_key) or {}
    pages = usage.get("pages") or []
    methods = usage.get("methods") or []
    api_ep = usage.get("api_endpoint") or ""
    src_tbl = usage.get("source_table") or ""
    if pages or methods or api_ep:
        meta.append(dmc.Divider(my="sm"))
        meta.append(dmc.Text("Where this query is used", size="sm", fw=700, c="#2B3674"))
        for p in pages:
            meta.append(dmc.Text(f"  • {p}", size="xs", c="#A3AED0"))
        for m in methods:
            meta.append(dmc.Text(f"  • {m}", size="xs", c="#A3AED0"))
        if src_tbl and src_tbl != entry.get("source"):
            meta.append(dmc.Text(f"Registry source: {src_tbl}", size="xs", c="#A3AED0"))
        if api_ep:
            meta.append(
                dmc.Text(
                    f"API / routing: {api_ep}",
                    size="xs",
                    c="#4318FF",
                    style={"wordBreak": "break-word"},
                )
            )
    sql = entry.get("sql") or ""
    return dmc.Stack(meta, gap=4), sql


@callback(
    Output("run-output", "children"),
    Output("qe-result-store", "data"),
    Input("run-button", "n_clicks"),
    State("query-select", "value"),
    State("params-input", "value"),
    prevent_initial_call=True,
)
def on_run(n_clicks, query_key, params_input):
    if not query_key:
        return dmc.Text("Select a query first.", c="#A3AED0", size="sm"), None
    result = api.execute_registered_query(query_key, params_input or "")
    return _render_run_output(result), result


@callback(
    Output("qe-export-download", "data"),
    Input("qe-export-csv", "n_clicks"),
    Input("qe-export-xlsx", "n_clicks"),
    State("qe-result-store", "data"),
    State("query-select", "value"),
    State("app-time-range", "data"),
    prevent_initial_call=True,
)
def export_query_result(nc, nx, result, query_key, time_range):
    ctx = callback_context
    if not ctx.triggered:
        return dash.no_update
    tid = ctx.triggered[0]["prop_id"].split(".")[0]
    fmt_map = {
        "qe-export-csv": "csv",
        "qe-export-xlsx": "xlsx",
    }
    fmt = fmt_map.get(tid)
    if not fmt:
        return dash.no_update
    df = _result_to_dataframe(result)
    base = (query_key or "query_result").replace(" ", "_")
    extra = {"selected_query": query_key or ""}
    sheets = {"Query_Result": df}
    if fmt == "xlsx":
        content = dataframes_to_excel_with_meta(sheets, time_range, "Query_Explorer", extra)
        return dash_send_excel_workbook(content, base)
    report_info = build_report_info_df(time_range, "Query_Explorer", extra)
    return dash_send_csv_bytes(
        csv_bytes_with_report_header(report_info, [("Query_Result", df)]),
        base,
    )


@callback(
    Output("save-status", "children"),
    Input("save-button", "n_clicks"),
    State("query-select", "value"),
    State("sql-editor", "value"),
    prevent_initial_call=True,
)
def on_save(n_clicks, query_key, sql_value):
    if not query_key:
        return dmc.Alert("Select a query first.", color="orange")
    if not (sql_value or "").strip():
        return dmc.Alert("SQL is empty.", color="orange")
    entry = qo.get_merged_entry(query_key)
    if not entry:
        return dmc.Alert("Unknown query.", color="red")
    try:
        qo.set_override(
            query_key,
            sql_value.strip(),
            result_type=entry.get("result_type"),
            params_style=entry.get("params_style"),
            source=entry.get("source", "custom"),
        )
        return dmc.Alert("Override saved. The app will use this SQL.", color="green")
    except Exception as e:
        return dmc.Alert(f"Save failed: {e}", color="red")


@callback(
    Output("save-status", "children", allow_duplicate=True),
    Output("query-select", "options", allow_duplicate=True),
    Input("reset-button", "n_clicks"),
    State("query-select", "value"),
    prevent_initial_call=True,
)
def on_reset(n_clicks, query_key):
    if not query_key:
        return dmc.Alert("Select a query first.", color="orange"), dash.no_update
    if qo.remove_override(query_key):
        return dmc.Alert("Override removed. Using default SQL from registry.", color="green"), _query_options()
    return dmc.Alert("No override to reset.", color="blue"), dash.no_update


@callback(
    Output("add-status", "children"),
    Output("query-select", "options"),
    Input("add-button", "n_clicks"),
    State("new-query-key", "value"),
    State("new-query-sql", "value"),
    State("new-result-type", "value"),
    State("new-params-style", "value"),
    prevent_initial_call=True,
)
def on_add(n_clicks, key, sql, result_type, params_style):
    if not (key or "").strip():
        return dmc.Alert("Enter a query key.", color="orange"), dash.no_update
    if not (sql or "").strip():
        return dmc.Alert("Enter SQL.", color="orange"), dash.no_update
    from src.queries.registry import QUERY_REGISTRY

    if key.strip() in QUERY_REGISTRY:
        return dmc.Alert("This key already exists in the registry. Use Edit to override.", color="orange"), dash.no_update
    try:
        qo.set_override(
            key.strip(),
            sql.strip(),
            result_type=result_type or "value",
            params_style=params_style or "wildcard",
            source="custom",
        )
        return dmc.Alert("Query added. Select it from the catalog or dropdown to run or edit.", color="green"), _query_options()
    except Exception as e:
        return dmc.Alert(f"Add failed: {e}", color="red"), dash.no_update
