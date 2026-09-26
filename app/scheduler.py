import logging

from apscheduler.schedulers.background import BackgroundScheduler

from .config import load_config
from .fetch_jobs import run_fetch_cycle

logger = logging.getLogger(__name__)

_scheduler = None


def start_scheduler(app):
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    config = load_config()
    interval = config.get("fetch_interval_minutes", 60)
    if not interval:
        logger.info("fetch_interval_minutes ist 0 - eingebauter Scheduler bleibt aus (Cron nutzen).")
        return None

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        lambda: run_fetch_cycle(app),
        "interval",
        minutes=interval,
        id="job_fetch",
        next_run_time=None,  # erster Lauf erst nach einem Intervall, nicht sofort beim Start
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info("Scheduler gestartet: alle %s Minuten neue Jobs suchen.", interval)
    return scheduler
