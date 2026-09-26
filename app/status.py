"""Quellen-Status fuer Status-Seite und Warn-Banner.

Nur aktuell aktive Quellen zaehlen - eine geloeschte Firma oder eine
abgeschaltete Quelle darf nicht ewig als "kaputt" im Banner stehen.
Nur kind == "error" loest den roten Banner aus: "blockiert" (Bot-Schutz)
ist kein Bug und kann nicht behoben werden, "config" braucht nur eine
Einstellung.
"""

from .models import CompanySource, ScraperRun, SourceSetting


def active_source_keys():
    keys = {s.name for s in SourceSetting.query.filter_by(enabled=True).all()}
    keys |= {c.source_key for c in CompanySource.query.filter_by(active=True).all()}
    return keys


def run_kind(run) -> str:
    kind = run.kind or ("ok" if run.ok else "error")
    return "error" if kind == "network" else kind


def latest_run_per_source(only_active=True):
    active = active_source_keys() if only_active else None
    latest = {}
    for run in ScraperRun.query.order_by(ScraperRun.ran_at.desc()).all():
        if run.source in latest or (active is not None and run.source not in active):
            continue
        latest[run.source] = run
    return dict(sorted(latest.items()))


def broken_source_names():
    return [s for s, r in latest_run_per_source().items() if run_kind(r) == "error"]
