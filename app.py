import logging
import dash
from dash import Dash, html, dcc, _dash_renderer
import dash_mantine_components as dmc
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

from src.components.sidebar import create_sidebar_nav
from src.services.shared import service
from src.services.scheduler_service import start_scheduler
from src.utils.time_range import default_time_range, preset_to_range

_dash_renderer._set_react_version("18.2.0")

stylesheets = [
    "https://unpkg.com/@mantine/core@7.10.0/styles.css",
    "https://unpkg.com/@mantine/dates@7.10.0/styles.css",
    "https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&display=swap",
]

app = Dash(
    __name__,
    use_pages=False,
    external_stylesheets=stylesheets,
    suppress_callback_exceptions=True,
    title="Bulutistan Dashboard",
)
server = app.server

# Import pages once at startup (routing is manual via render_main_content)
from src.pages import home, datacenters, dc_view, customer_view, query_explorer

# --- Build static sidebar with controls always in layout ---
_default_tr = default_time_range()
_customers = service.get_customer_list()
_default_customer = _customers[0] if _customers else "Boyner"
_customer_options = [{"value": c, "label": c} for c in _customers] if _customers else [{"value": "Boyner", "label": "Boyner"}]

_sidebar = html.Div(
    style={
        "width": "260px",
        "position": "fixed",
        "top": "16px",
        "left": "16px",
        "height": "calc(100vh - 32px)",
        "zIndex": 999,
        "padding": "24px",
        "backgroundColor": "#FFFFFF",
        "overflowY": "auto",
        "overflowX": "hidden",
        "borderRadius": "16px",
        "boxShadow": "0 10px 30px rgba(0, 0, 0, 0.08), 0 4px 12px rgba(0, 0, 0, 0.04)",
        "display": "flex",
        "flexDirection": "column",
    },
    children=[
        # Brand + nav links — only this part is updated by callback
        html.Div(id="sidebar-nav"),

        # Time range controls — static, always in DOM
        dmc.Stack(
            [
                dmc.Divider(mt="xl", style={"marginBottom": "4px"}),
                dmc.Text(
                    "REPORT PERIOD",
                    size="xs",
                    fw=600,
                    c="dimmed",
                    style={"letterSpacing": "0.06em"},
                ),
                dmc.SegmentedControl(
                    id="time-range-preset",
                    value=_default_tr.get("preset", "7d"),
                    data=[
                        {"label": "1D", "value": "1d"},
                        {"label": "7D", "value": "7d"},
                        {"label": "30D", "value": "30d"},
                        {"label": "Cstm", "value": "custom"},
                    ],
                    size="sm",
                    fullWidth=True,
                ),
                html.Div(
                    id="time-range-custom-container",
                    children=[
                        dcc.DatePickerRange(
                            id="time-range-picker",
                            start_date=_default_tr["start"],
                            end_date=_default_tr["end"],
                            display_format="DD/MM/YY",
                            start_date_placeholder_text="Start",
                            end_date_placeholder_text="End",
                            calendar_orientation="vertical",
                            style={
                                "width": "100%",
                                "fontSize": "12px",
                                "borderRadius": "8px",
                            },
                        ),
                    ],
                    style={"position": "relative"},
                ),
            ],
            gap="xs",
            px="md",
            mt="auto",
        ),

        # Customer select — static, always in DOM; visibility toggled by callback
        html.Div(
            id="customer-section",
            children=[
                dmc.Text("Customer", size="xs", fw=600, c="#A3AED0", style={"marginBottom": "6px"}),
                dmc.Select(
                    id="customer-select",
                    data=_customer_options,
                    value=_default_customer,
                    radius="md",
                    variant="default",
                    size="sm",
                    style={"width": "100%"},
                ),
            ],
            style={
                "marginTop": "16px",
                "paddingTop": "12px",
                "borderTop": "1px solid #E9ECEF",
                "display": "none",
            },
        ),
    ],
)

app.layout = dmc.MantineProvider(
    theme={
        "fontFamily": "'DM Sans', sans-serif",
        "headings": {"fontFamily": "'DM Sans', sans-serif"},
        "primaryColor": "indigo",
    },
    children=[
        dcc.Location(id="url", refresh=False),
        dcc.Store(id="app-time-range", data=_default_tr),
        html.Div(
            [
                _sidebar,
                html.Div(
                    html.Div(id="main-content", children=[]),
                    style={
                        "marginLeft": "292px",
                        "padding": "30px",
                        "minHeight": "100vh",
                        "width": "calc(100% - 292px)",
                        "backgroundColor": "#F4F7FE",
                    },
                ),
            ],
            style={"display": "flex", "backgroundColor": "#F4F7FE", "minHeight": "100vh"},
        ),
    ],
)


# --- Callbacks ---

# 1. Sidebar nav links (brand + active highlighting)
@app.callback(
    dash.Output("sidebar-nav", "children"),
    dash.Input("url", "pathname"),
)
def update_sidebar_nav(pathname):
    return create_sidebar_nav(pathname or "/")


# 2. Show/hide customer section based on page
@app.callback(
    dash.Output("customer-section", "style"),
    dash.Input("url", "pathname"),
)
def toggle_customer_section(pathname):
    base = {"marginTop": "16px", "paddingTop": "12px", "borderTop": "1px solid #E9ECEF"}
    if (pathname or "/") == "/customer-view":
        return {**base, "display": "block"}
    return {**base, "display": "none"}


# 3. Time range store from preset or date picker (no cycle — no reverse sync)
@app.callback(
    dash.Output("app-time-range", "data"),
    dash.Input("time-range-preset", "value"),
    dash.Input("time-range-picker", "start_date"),
    dash.Input("time-range-picker", "end_date"),
    dash.State("app-time-range", "data"),
)
def update_time_range_store(preset, start_date, end_date, current):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    tid = ctx.triggered[0]["prop_id"]
    if "time-range-preset" in tid and preset != "custom":
        return preset_to_range(preset)
    if "time-range-picker" in tid and (start_date or end_date):
        return {
            "start": start_date or (current or {}).get("start"),
            "end": end_date or (current or {}).get("end"),
            "preset": "custom",
        }
    return dash.no_update


# 4. Main content: dispatch by pathname + time range + customer
@app.callback(
    dash.Output("main-content", "children"),
    dash.Input("url", "pathname"),
    dash.Input("app-time-range", "data"),
    dash.Input("customer-select", "value"),
)
def render_main_content(pathname, time_range, selected_customer):
    pathname = pathname or "/"
    tr = time_range or default_time_range()
    if pathname in ("/", ""):
        return home.build_overview(tr)
    if pathname == "/datacenters":
        return datacenters.build_datacenters(tr)
    if pathname and pathname.startswith("/datacenter/"):
        dc_id = pathname.replace("/datacenter/", "").strip("/")
        return dc_view.build_dc_view(dc_id, tr)
    if pathname == "/customer-view":
        return customer_view.build_customer_layout(tr, selected_customer)
    if pathname == "/query-explorer":
        return query_explorer.layout()
    return home.build_overview(tr)


# 5. Start background cache scheduler
_scheduler = start_scheduler(service)

if __name__ == "__main__":
    app.run(debug=True, port=8050, use_reloader=False)
