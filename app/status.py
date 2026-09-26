"""Kleine gemeinsame Helfer rund um ScraperRun - genutzt von routes.py
(/status-Seiten) und vom globalen Warn-Banner in base.html (via
context_processor in app/__init__.py), damit beide dieselbe Definition
von 'kaputt' nutzen."""

from .models import ScraperRun


def latest_run_per_source():
    """Neuester ScraperRun je Quelle."""
    latest = {}
    for run in ScraperRun.query.order_by(ScraperRun.ran_at.desc()).all():
        if run.source not in latest:
            latest[run.source] = run
    return dict(sorted(latest.items()))


def broken_source_names():
    return [s for s, r in latest_run_per_source().items() if not r.ok]
