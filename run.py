import logging
import os
import threading
import webbrowser

from app import create_app
from app.scheduler import start_scheduler

logging.basicConfig(level=logging.INFO)

HOST = "127.0.0.1"
PORT = 5000

app = create_app()
start_scheduler(app)

# secret_key wird nur fuer flash()-Nachrichten benoetigt (kein Login-System).
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")


def _open_browser():
    webbrowser.open(f"http://{HOST}:{PORT}")


if __name__ == "__main__":
    # Browser automatisch oeffnen, sobald der Server steht - damit "starten"
    # wirklich nur "Doppelklick" bedeutet (siehe start.command).
    if not os.environ.get("NO_AUTO_BROWSER"):
        threading.Timer(1.2, _open_browser).start()

    app.run(host=HOST, port=PORT, debug=True, use_reloader=False)
