import logging
import dash
from dash import Dash, html, dcc, page_container, _dash_renderer
import dash_mantine_components as dmc
from dotenv import load_dotenv

# 0. Load .env before any service import so DB credentials are available
load_dotenv()

# Configure logging so scheduler and DB service INFO messages appear in the terminal
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

from src.components.sidebar import create_sidebar
from src.services.shared import service
from src.services.scheduler_service import start_scheduler

# 1. React 18 requirement for DMC
_dash_renderer._set_react_version("18.2.0")

# 2. STİL DOSYALARI (DMC 0.14 için ZORUNLU)
# Eski sürümde 'withNormalizeCSS' vardı, şimdi bu linkleri ekliyoruz.
stylesheets = [
    "https://unpkg.com/@mantine/core@7.10.0/styles.css",
    "https://unpkg.com/@mantine/dates@7.10.0/styles.css",
    "https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&display=swap" # Senin fontun
]

app = Dash(
    __name__, 
    use_pages=True, 
    pages_folder="src/pages", # <-- Klasör hatasını çözen satır
    external_stylesheets=stylesheets, # <-- Stil hatasını çözen satır
    suppress_callback_exceptions=True,
    title="Bulutistan Dashboard"
)
server = app.server

# 3. Global Layout
app.layout = dmc.MantineProvider(
    # HATA ÇIKARAN 'withNormalizeCSS' ve 'withGlobalStyles' SİLİNDİ.
    theme={
        "fontFamily": "'DM Sans', sans-serif",
        "headings": {
            "fontFamily": "'DM Sans', sans-serif"
        },
        "primaryColor": "indigo",
    },
    children=[
        dcc.Location(id="url", refresh=False),
        html.Div(
            [
                # Sol Sidebar Konteyneri
                html.Div(
                    id="sidebar-container",
                    style={
                        "width": "260px",
                        "position": "fixed",
                        "top": 0,
                        "left": 0,
                        "height": "100vh",
                        "zIndex": 999
                    }
                ),
                
                # Sağ İçerik Alanı
                html.Div(
                    page_container,
                    style={
                        "marginLeft": "260px",
                        "padding": "30px",
                        "minHeight": "100vh",
                        "width": "calc(100% - 260px)",
                        "backgroundColor": "#F4F7FE"
                    }
                )
            ],
            style={"display": "flex", "backgroundColor": "#F4F7FE", "minHeight": "100vh"}
        )
    ]
)

# Sidebar Callback'i
@app.callback(
    dash.Output("sidebar-container", "children"),
    dash.Input("url", "pathname")
)
def update_sidebar(pathname):
    return create_sidebar(pathname or "/")

# 4. Start background cache scheduler (warm cache now + refresh every 15 min)
# Runs outside __main__ guard so it also starts under Gunicorn / production.
_scheduler = start_scheduler(service)

if __name__ == "__main__":
    # use_reloader=False: single process so Ctrl+C fully stops the app.
    # With reloader (default when debug=True), a child process keeps listening on 8050
    # and the UI stays reachable after Ctrl+C.
    app.run(debug=True, port=8050, use_reloader=False)