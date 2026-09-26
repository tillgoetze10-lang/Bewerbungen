"""Startet Suchlaeufe im Hintergrund, damit der Button sofort reagiert und
nie zwei Laeufe gleichzeitig laufen (Button + Scheduler koennten sich sonst
ueberschneiden und doppelte Eintraege/Datenbank-Sperren verursachen)."""

import logging
import threading
from datetime import datetime

from .config import load_config
from .fetch_jobs import run_fetch_cycle
from .notify import notify_new_top_jobs

logger = logging.getLogger(__name__)

_lock = threading.Lock()
state = {
    "running": False,
    "step": "",
    "started_at": None,
    "finished_at": None,
    "new_jobs": 0,
    "summary": "",
    "run_id": 0,
}


def _progress(step: str):
    state["step"] = step


def _execute(app):
    try:
        result = run_fetch_cycle(app, progress=_progress)
        state["new_jobs"] = result["new_jobs"]
        if load_config().get("notify_new_top", True):
            notify_new_top_jobs(result.get("new_top", []))
        errors = sum(1 for _, kind, _ in result["problems"] if kind == "error")
        if result.get("offline"):
            summary = "Keine Internetverbindung – die Suche wird beim nächsten Mal automatisch nachgeholt."
        elif result["new_jobs"]:
            summary = f"{result['new_jobs']} neue(r) Job(s) gefunden."
        else:
            summary = "Suchlauf fertig – keine neuen passenden Jobs."
        if errors:
            summary += f" {errors} Quelle(n) mit Fehler, siehe Status."
        state["summary"] = summary
    except Exception as exc:
        logger.exception("Suchlauf abgebrochen")
        state["summary"] = f"Suchlauf abgebrochen: {type(exc).__name__}: {exc}"
    finally:
        state.update(running=False, step="", finished_at=datetime.now())
        _lock.release()


def start_async(app) -> bool:
    """True = Lauf gestartet, False = es laeuft bereits einer."""
    if not _lock.acquire(blocking=False):
        return False
    state.update(running=True, step="Starte …", started_at=datetime.now(), new_jobs=0, summary="",
                 run_id=state["run_id"] + 1)
    threading.Thread(target=_execute, args=(app,), daemon=True, name="job-fetch").start()
    return True


def snapshot() -> dict:
    data = dict(state)
    for key in ("started_at", "finished_at"):
        data[key] = data[key].strftime("%H:%M") if data[key] else None
    return data
