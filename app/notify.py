"""Mac-Mitteilung (rechts oben) bei neuen Top-Treffern - auch wenn der
Browser gerade nicht offen ist. Auf anderen Systemen passiert einfach nichts."""

import json
import logging
import platform
import subprocess

logger = logging.getLogger(__name__)


def notify(title: str, message: str) -> bool:
    if platform.system() != "Darwin":
        return False
    script = f"display notification {json.dumps(message)} with title {json.dumps(title)} sound name \"Glass\""
    try:
        subprocess.run(["osascript", "-e", script], timeout=5, capture_output=True, check=False)
        return True
    except Exception:
        logger.info("Mac-Mitteilung konnte nicht angezeigt werden", exc_info=True)
        return False


def notify_new_top_jobs(titles) -> bool:
    if not titles:
        return False
    if len(titles) == 1:
        return notify("Neuer Top-Treffer", titles[0])
    preview = ", ".join(titles[:2]) + (f" und {len(titles) - 2} weitere" if len(titles) > 2 else "")
    return notify(f"{len(titles)} neue Top-Treffer", preview)
