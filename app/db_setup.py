"""Datenbank-Setup beim Start: Tabellen anlegen, fehlende Spalten nachruesten,
Standardwerte seeden und bestehende Jobs neu bewerten.

db.create_all() legt nur fehlende TABELLEN an - neue Spalten in bestehenden
Tabellen (z.B. nach einem Update) wuerden sonst fehlen und jede Seite mit
"no such column" abstuerzen lassen. ensure_columns() ergaenzt sie per
ALTER TABLE, damit ein Update nie die vorhandenen Daten kostet.
"""

import logging

from sqlalchemy import inspect, text

from .config import load_config
from .models import AppSetting, CoverLetterTemplate, Job, SearchProfile, SourceSetting, db

logger = logging.getLogger(__name__)

# Startausstattung an Suchprofilen, passend zum Profil (Video/Film, Ziel Koeln,
# Frankfurt nur mit Set-Bezug, Kurzeinsaetze bundesweit). Im UI aenderbar.
DEFAULT_SEARCH_PROFILES = [
    ("Videograf", "Köln", 25),
    ("Video Editor", "Köln", 25),
    ("Cutter", "Köln", 25),
    ("Mediengestalter Bild und Ton", "Köln", 25),
    ("Video Producer", "Köln", 25),
    ("Motion Designer", "Köln", 25),
    ("Kameraassistent", "Köln", 25),
    ("Aufnahmeleitung", "Köln", 25),
    ("Produktionsassistenz Film", "Köln", 25),
    ("Aufnahmeleitung", "Frankfurt am Main", 25),
    ("Kameraassistent", "Frankfurt am Main", 25),
    ("Setrunner", "", 0),
]

# Indeed/StepStone sind aus: sie blockieren automatische Abfragen nachweislich
# (403 bzw. Zeitueberschreitung). Adzuna/Jooble/Google laufen erst, wenn im
# UI ein Schluessel hinterlegt ist.
DEFAULT_SOURCES = {
    "arbeitsagentur": True,
    "adzuna": True,
    "jooble": True,
    "crewunited": True,
    "google_jobs": True,
    "indeed": False,
    "stepstone": False,
}


def _default_literal(column):
    default = column.default
    if default is None or not getattr(default, "is_scalar", False):
        return None
    value = default.arg
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return None


def ensure_columns():
    engine = db.engine
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in db.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {col["name"] for col in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                col_type = column.type.compile(dialect=engine.dialect)
                ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'
                literal = _default_literal(column)
                if literal is not None:
                    ddl += f" DEFAULT {literal}"
                conn.execute(text(ddl))
                logger.info("DB-Update: Spalte %s.%s ergaenzt", table.name, column.name)
    for table in db.metadata.sorted_tables:
        for index in table.indexes:
            index.create(bind=engine, checkfirst=True)


def seed_defaults():
    if CoverLetterTemplate.query.count() == 0:
        from .letters import DEFAULT_TEMPLATE, DEFAULT_TEMPLATE_NAME

        db.session.add(CoverLetterTemplate(name=DEFAULT_TEMPLATE_NAME, body=DEFAULT_TEMPLATE))

    known = {s.name for s in SourceSetting.query.all()}
    for name, enabled in DEFAULT_SOURCES.items():
        if name not in known:
            db.session.add(SourceSetting(name=name, enabled=enabled))

    # Einen evtl. in config.yaml eingetragenen SerpApi-Key einmalig uebernehmen.
    serpapi_key = load_config().get("serpapi_key")
    if serpapi_key and not db.session.get(AppSetting, "serpapi_key"):
        db.session.add(AppSetting(key="serpapi_key", value=serpapi_key))

    if SearchProfile.query.count() == 0:
        seen = set()
        config_profiles = [
            (p.get("keywords", ""), p.get("location", ""), p.get("radius_km", 25))
            for p in (load_config().get("search_profiles") or [])
            if isinstance(p, dict)
        ]
        for keywords, location, radius in DEFAULT_SEARCH_PROFILES + config_profiles:
            key = (keywords.strip().lower(), (location or "").strip().lower())
            if not keywords.strip() or key in seen:
                continue
            seen.add(key)
            db.session.add(SearchProfile(keywords=keywords.strip(), location=(location or "").strip(), radius_km=radius or 0))
    db.session.commit()


def rescore_jobs():
    """Bewertung aller Jobs mit der aktuellen Logik neu berechnen - damit
    Verbesserungen an app/matching.py auch fuer schon gespeicherte Jobs gelten.
    Aendert nur die Bewertungsfelder, nie Status, Notizen oder Anschreiben."""
    from .matching import score_job

    changed = 0
    for job in Job.query.all():
        score, label, reason = score_job(job.title or "", job.description or "", job.location or "")
        if (job.match_score, job.match_label, job.match_reason) != (score, label, reason):
            job.match_score, job.match_label, job.match_reason = score, label, reason
            changed += 1
    if changed:
        db.session.commit()
        logger.info("%s Job(s) mit aktueller Logik neu bewertet.", changed)


def setup_database():
    db.create_all()
    ensure_columns()
    seed_defaults()
    rescore_jobs()
