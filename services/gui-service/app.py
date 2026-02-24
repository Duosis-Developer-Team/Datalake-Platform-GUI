import dash
from dash import html, dcc
import dash_mantine_components as dmc

app = dash.Dash(__name__, use_pages=True)

app.layout = dmc.MantineProvider(
    children=[
        html.H1("Datalake-GUI"),
        dash.page_container
    ]
)

if __name__ == "__main__":
    app.run_server(host="0.0.0.0", port=8050, debug=True)
