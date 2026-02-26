import os

import dash

from layout import create_layout
from shared.utils.logger import setup_logger

# Servis root logger — pages.* ve services.* alt logger'ları hiyerarşi üzerinden
# bu yapılandırmayı miras alır; modüllerdeki getLogger(__name__) değişmez.
logger = setup_logger("gui-service")

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
    logger.info("Dash app başlatılıyor — host=0.0.0.0 port=8050 debug=%s", debug)
    app.run(host="0.0.0.0", port=8050, debug=debug)

