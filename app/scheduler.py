import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from .config import load_config
from .fetch_runner import start_async

logger = logging.getLogger(__name__)

_scheduler = None


def start_scheduler(app):
    """Kurz nach dem Start einmal suchen, danach alle N Minuten.

    Frueher stand hier next_run_time=None - das legt den Job bei APScheduler
    PAUSIERT an, die automatische Suche lief dadurch nie."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    config = load_config()
    interval = int(config.get("fetch_interval_minutes") or 0)
    scheduler = BackgroundScheduler(daemon=True)

    if config.get("fetch_on_startup", True):
        scheduler.add_job(lambda: start_async(app), "date", run_date=datetime.now() + timedelta(seconds=8), id="startup_fetch")
    if interval > 0:
        scheduler.add_job(lambda: start_async(app), "interval", minutes=interval, id="job_fetch")

    scheduler.start()
    _scheduler = scheduler
    logger.info("Automatische Suche: beim Start%s.", f" und alle {interval} Minuten" if interval else "")
    return scheduler
