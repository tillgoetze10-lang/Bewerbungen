import logging
import os

from app import create_app
from app.scheduler import start_scheduler

logging.basicConfig(level=logging.INFO)

app = create_app()
start_scheduler(app)

# secret_key wird nur fuer flash()-Nachrichten benoetigt (kein Login-System).
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)
