import json
import logging
import os
import socket
import sys
import threading
import urllib.request
import webbrowser

HOST = "127.0.0.1"
# Nicht 5000: den belegt auf dem Mac oft der AirPlay-Empfaenger.
DEFAULT_PORT = int(os.environ.get("PORT", "8765"))


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex((HOST, port)) != 0


def _our_app_runs_on(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}/fetch-status", timeout=2) as resp:
            return "running" in json.loads(resp.read().decode("utf-8"))
    except Exception:
        return False


def _pick_port():
    for port in range(DEFAULT_PORT, DEFAULT_PORT + 10):
        if _port_free(port):
            return port, False
        if _our_app_runs_on(port):
            return port, True
    raise SystemExit(f"Kein freier Port zwischen {DEFAULT_PORT} und {DEFAULT_PORT + 9} gefunden.")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    port, already_running = _pick_port()
    url = f"http://{HOST}:{port}"
    if already_running:
        print(f"Das Bewerbungs-Board läuft schon – öffne {url}")
        webbrowser.open(url)
        return

    from app import create_app
    from app.scheduler import start_scheduler

    app = create_app()
    start_scheduler(app)

    print(f"\n  Bewerbungs-Board läuft auf {url}\n  Zum Beenden dieses Fenster schließen oder Strg+C drücken.\n")
    if not os.environ.get("NO_AUTO_BROWSER"):
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    debug = os.environ.get("FLASK_DEBUG") == "1"
    app.run(host=HOST, port=port, debug=debug, use_reloader=False, threaded=True)


if __name__ == "__main__":
    sys.exit(main())
