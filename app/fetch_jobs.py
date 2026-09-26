"""Durchsucht alle aktivierten Quellen (Jobportale + hinterlegte Firmen-Karriereseiten)
fuer alle konfigurierten Suchprofile und legt neue, passende Jobs im Status
'neu' an (bereits bekannte URLs werden uebersprungen). Jeder neue Job wird
sofort automatisch bewertet (siehe app/matching.py).

Jeder Quellen-Versuch wird zusaetzlich als ScraperRun protokolliert (siehe
app/models.py) - das treibt die Status-Seite (/status), damit du nicht
selbst Terminal-Logs oder Flash-Meldungen lesen musst, um zu sehen, ob
eine Quelle gerade funktioniert.

Aufruf manuell:      python -m app.fetch_jobs
Aufruf automatisch:  siehe app/scheduler.py (laeuft im Hintergrund der Web-App)
Aufruf per Klick:    Button "Jetzt nach neuen Jobs suchen" im Web-UI
"""

import logging
import sys

from .config import load_config, source_enabled
from .extraction import EMPTY_RESULT, fetch_and_extract_details
from .matching import score_job, score_title
from .models import CompanySource, Job, ScraperRun, db, make_external_id
from .scrapers import REGISTRY
from .scrapers.base import ScraperError
from .scrapers.company_generic import search_company

logger = logging.getLogger(__name__)

RUNS_KEPT_PER_SOURCE = 20


def _store_listing(listing, config) -> bool:
    """Legt einen Job an, falls er neu und (mindestens etwas) passend ist.
    Gibt True zurueck, wenn ein neuer Job angelegt wurde."""
    if not listing.is_valid():
        return False

    title_score, _, _ = score_title(listing.title, listing.description)
    if title_score == 0:
        return False  # kein Bezug zu den hinterlegten Berufsbezeichnungen

    ext_id = make_external_id(listing.url)
    if Job.query.filter_by(external_id=ext_id).first():
        return False

    score, label, reason = score_job(listing.title, listing.description, listing.location)

    details = None
    if config.get("fetch_job_details", True):
        details = fetch_and_extract_details(listing.url, config)
    details = details or EMPTY_RESULT

    job = Job(
        external_id=ext_id,
        title=listing.title,
        company=listing.company,
        location=listing.location,
        url=listing.url,
        source=listing.source,
        salary=listing.salary,
        description=listing.description,
        posted_at=listing.posted_at,
        status="neu",
        match_score=score,
        match_label=label,
        match_reason=reason,
        contact_name=details["contact_name"],
        contact_email=details["contact_email"],
        contact_phone=details["contact_phone"],
        company_website=details["company_website"],
        requirements=details["requirements"],
        application_documents=details["application_documents"],
        extraction_confidence=details["confidence"],
        extraction_missing=",".join(details["missing_fields"]),
    )
    db.session.add(job)
    return True


def _record_run(source: str, ok: bool, message: str, new_jobs: int):
    db.session.add(ScraperRun(source=source, ok=ok, message=message[:2000], new_jobs=new_jobs))
    # Alte Eintraege derselben Quelle aufraeumen, damit die Tabelle nicht endlos waechst.
    old_ids = [
        r.id
        for r in ScraperRun.query.filter_by(source=source)
        .order_by(ScraperRun.ran_at.desc())
        .offset(RUNS_KEPT_PER_SOURCE)
        .all()
    ]
    if old_ids:
        ScraperRun.query.filter(ScraperRun.id.in_(old_ids)).delete(synchronize_session=False)


def run_fetch_cycle(app):
    """Fuehrt einen kompletten Scraper-Durchlauf aus. Muss im Flask app_context laufen."""
    config = load_config()
    profiles = config.get("search_profiles", [])

    new_jobs = 0
    errors = []

    with app.app_context():
        if not profiles:
            logger.warning("Keine search_profiles in config.yaml definiert - Jobportale werden uebersprungen.")
        else:
            for source_name, scraper in REGISTRY.items():
                if not source_enabled(config, source_name):
                    continue

                source_new_jobs = 0
                source_errors = []
                for profile in profiles:
                    try:
                        listings = scraper.search(profile, config)
                    except ScraperError as exc:
                        logger.warning("[%s] %s", source_name, exc)
                        source_errors.append(str(exc))
                        continue
                    except Exception as exc:  # ein kaputter Scraper darf den Lauf nicht stoppen
                        logger.exception("[%s] unerwarteter Fehler", source_name)
                        source_errors.append(f"unerwarteter Fehler ({exc})")
                        continue

                    for listing in listings:
                        if _store_listing(listing, config):
                            source_new_jobs += 1

                ok = not source_errors
                message = "; ".join(source_errors) if source_errors else f"{source_new_jobs} neue Job(s)."
                _record_run(source_name, ok, message, source_new_jobs)
                new_jobs += source_new_jobs
                errors.extend(f"{source_name}: {e}" for e in source_errors)

        for company in CompanySource.query.filter_by(active=True).all():
            source_key = f"firma:{company.name}"
            try:
                listings = search_company(company.name, company.career_url, config)
            except ScraperError as exc:
                logger.warning("[%s] %s", source_key, exc)
                errors.append(f"{company.name}: {exc}")
                company.last_result = f"Fehler: {exc}"[:290]
                _record_run(source_key, False, str(exc), 0)
                continue
            except Exception as exc:
                logger.exception("[%s] unerwarteter Fehler", source_key)
                errors.append(f"{company.name}: unerwarteter Fehler ({exc})")
                company.last_result = f"Unerwarteter Fehler: {exc}"[:290]
                _record_run(source_key, False, f"unerwarteter Fehler ({exc})", 0)
                continue

            found = 0
            for listing in listings:
                if _store_listing(listing, config):
                    found += 1
                    new_jobs += 1
            company.last_result = f"{len(listings)} passende Treffer, {found} davon neu."
            _record_run(source_key, True, company.last_result, found)

        db.session.commit()

    logger.info("Fetch-Lauf fertig: %s neue Jobs, %s Fehler", new_jobs, len(errors))
    return {"new_jobs": new_jobs, "errors": errors}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from . import create_app

    flask_app = create_app()
    result = run_fetch_cycle(flask_app)
    print(f"Neue Jobs: {result['new_jobs']}")
    if result["errors"]:
        print("Fehler/Warnungen:")
        for err in result["errors"]:
            print(f"  - {err}")
    sys.exit(0)
