# Query Explorer: run registered queries, view output, edit SQL, add custom queries.

import dash
from dash import html, dcc, Input, Output, State, callback
import dash_mantine_components as dmc
from dash_iconify import DashIconify

from src.services.shared import service
from src.services import query_overrides as qo

dash.register_page(__name__, path="/query-explorer")

# Build options once at module load (refresh on add via callback)
def _query_options():
    return [{"label": k, "value": k} for k in qo.list_all_query_keys()]


def layout():
    return html.Div([
        # Header
        html.Div(
            className="nexus-glass",
            children=[
                html.Div([
                    DashIconify(icon="solar:code-square-bold-duotone", width=30, color="#4318FF"),
                    html.H1("Query Explorer", style={"margin": "0 0 0 10px", "color": "#2B3674", "fontSize": "1.8rem"}),
                ], style={"display": "flex", "alignItems": "center"}),
                html.P(
                    "Run queries, view outputs, and edit or add SQL without changing code.",
                    style={"margin": "5px 0 0 40px", "color": "#A3AED0"},
                ),
            ],
            style={
                "padding": "24px 32px",
                "marginBottom": "32px",
                "display": "flex",
                "flexDirection": "column",
                "justifyContent": "center",
            },
        ),

        html.Div(
            style={"padding": "0 32px"},
            children=[
                # Query selector and metadata
                dmc.Paper(
                    p="md",
                    radius="md",
                    withBorder=True,
                    shadow="sm",
                    mb="lg",
                    children=[
                        dmc.Text("Query", size="sm", fw=600, c="#2B3674", mb="xs"),
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
                        dmc.TabsList(
                            [
                                dmc.TabsTab("Run", value="run"),
                                dmc.TabsTab("Edit SQL", value="edit"),
                                dmc.TabsTab("Add new query", value="add"),
                            ]
                        ),
                        dmc.TabsPanel(
                            value="run",
                            children=[
                                dmc.Text("Parameters (for array_* use comma-separated values)", size="sm", c="#A3AED0", mb="xs"),
                                dmc.Group(
                                    [
                                        dmc.TextInput(
                                            id="params-input",
                                            placeholder="e.g. DC11 or DC11,DC12",
                                            style={"flex": 1},
                                        ),
                                        dmc.Button("Run", id="run-button", leftSection=DashIconify(icon="solar:play-circle-bold")),
                                    ]
                                ),
                                dmc.Space(h=12),
                                html.Div(id="run-output", children=dmc.Text("Select a query and click Run.", c="#A3AED0", size="sm")),
                            ],
                        ),
                        dmc.TabsPanel(
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
                                        dmc.Button("Save override", id="save-button", color="green", leftSection=DashIconify(icon="solar:diskette-bold")),
                                        dmc.Button("Reset to default", id="reset-button", variant="light", color="red", leftSection=DashIconify(icon="solar:restart-bold")),
                                    ]
                                ),
                                html.Div(id="save-status", children=[], style={"marginTop": "8px"}),
                            ],
                        ),
                        dmc.TabsPanel(
                            value="add",
                            children=[
                                dmc.Stack(
                                    [
                                        dmc.TextInput(id="new-query-key", placeholder="Query key (e.g. custom_my_query)", label="Key"),
                                        dmc.Textarea(id="new-query-sql", placeholder="SELECT ...", minRows=8, label="SQL"),
                                        dmc.Select(
                                            id="new-result-type",
                                            data=[{"label": "value", "value": "value"}, {"label": "row", "value": "row"}, {"label": "rows", "value": "rows"}],
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
                                        dmc.Button("Add query", id="add-button", color="indigo", leftSection=DashIconify(icon="solar:add-circle-bold")),
                                        html.Div(id="add-status", children=[], style={"marginTop": "8px"}),
                                    ],
                                    gap="md",
                                ),
                            ],
                        ),
                    ],
                    value="run",
                    id="query-explorer-tabs",
                ),
            ],
        ),
    ])


def _render_run_output(result: dict) -> html.Div:
    """Turn execute_registered_query result into UI."""
    if "error" in result:
        return dmc.Alert(result["error"], color="red", title="Error")
    rt = result.get("result_type", "value")
    if rt == "value":
        return dmc.Paper(
            p="md",
            withBorder=True,
            children=dmc.Text(str(result.get("value", "")), fw=600, size="lg"),
        )
    if rt == "row":
        cols = result.get("columns") or []
        row = result.get("data") or []
        return dmc.Paper(
            p="md",
            withBorder=True,
            children=html.Table(
                [
                    html.Thead(html.Tr([html.Th(c) for c in cols])),
                    html.Tbody(html.Tr([html.Td(row[i] if i < len(row) else "") for i in range(len(cols))])),
                ],
                style={"width": "100%", "borderCollapse": "collapse"},
            ),
        )
    # rows
    cols = result.get("columns") or []
    rows = result.get("data") or []
    return dmc.Paper(
        p="md",
        withBorder=True,
        children=html.Table(
            [html.Thead(html.Tr([html.Th(c) for c in cols]))]
            + [html.Tr([html.Td(r[i] if i < len(r) else "") for i in range(len(cols))]) for r in rows],
            style={"width": "100%", "borderCollapse": "collapse"},
        ),
    )


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
        dmc.Text(f"Source: {entry.get('source', '—')}", size="sm", c="#A3AED0"),
        dmc.Text(f"Result type: {entry.get('result_type', '—')}", size="sm", c="#A3AED0"),
        dmc.Text(f"Params style: {entry.get('params_style', '—')}", size="sm", c="#A3AED0"),
    ]
    sql = entry.get("sql") or ""
    return dmc.Stack(meta, gap=4), sql


@callback(
    Output("run-output", "children"),
    Input("run-button", "n_clicks"),
    State("query-select", "value"),
    State("params-input", "value"),
    prevent_initial_call=True,
)
def on_run(n_clicks, query_key, params_input):
    if not query_key:
        return dmc.Text("Select a query first.", c="#A3AED0", size="sm")
    result = service.execute_registered_query(query_key, params_input or "")
    return _render_run_output(result)


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
        qo.set_override(query_key, sql_value.strip(), result_type=entry.get("result_type"), params_style=entry.get("params_style"), source=entry.get("source", "custom"))
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
        qo.set_override(key.strip(), sql.strip(), result_type=result_type or "value", params_style=params_style or "wildcard", source="custom")
        return dmc.Alert("Query added. Select it from the dropdown to run or edit.", color="green"), _query_options()
    except Exception as e:
        return dmc.Alert(f"Add failed: {e}", color="red"), dash.no_update
