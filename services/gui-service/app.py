import os

import dash

from layout import create_layout

app = dash.Dash(
    __name__,
    use_pages=True,
    title="Datalake Platform",
    suppress_callback_exceptions=True,
)
app.layout = create_layout()
server = app.server  # gunicorn için

if __name__ == "__main__":
    debug = os.getenv("DASH_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=8050, debug=debug)
