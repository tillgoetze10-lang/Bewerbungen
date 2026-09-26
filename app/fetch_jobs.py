"""Durchsucht alle aktivierten Quellen (Jobportale + hinterlegte Firmen-Karriereseiten)
fuer alle konfigurierten Suchprofile und legt neue, passende Jobs im Status
'neu' an (bereits bekannte URLs werden uebersprungen). Jeder neue Job wird
sofort automatisch bewertet (siehe app/matching.py).

Aufruf manuell:      python -m app.fetch_jobs
Aufruf automatisch:  siehe app/scheduler.py (laeuft im Hintergrund der Web-App)
Aufruf per Klick:    Button "Jetzt nach neuen Jobs suchen" im Web-UI
"""

import logging
import sys

from .config import load_config, source_enabled
from .matching import score_job, score_title
from .models import CompanySource, Job, db, make_external_id
from .scrapers import REGISTRY
from .scrapers.base import ScraperError
from .scrapers.company_generic import search_company

logger = logging.getLogger(__name__)


def _store_listing(listing) -> bool:
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
    )
    db.session.add(job)
    return True


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
                for profile in profiles:
                    try:
                        listings = scraper.search(profile, config)
                    except ScraperError as exc:
                        logger.warning("[%s] %s", source_name, exc)
                        errors.append(f"{source_name}: {exc}")
                        continue
                    except Exception as exc:  # ein kaputter Scraper darf den Lauf nicht stoppen
                        logger.exception("[%s] unerwarteter Fehler", source_name)
                        errors.append(f"{source_name}: unerwarteter Fehler ({exc})")
                        continue

                    for listing in listings:
                        if _store_listing(listing):
                            new_jobs += 1

        for company in CompanySource.query.filter_by(active=True).all():
            try:
                listings = search_company(company.name, company.career_url, config)
            except ScraperError as exc:
                logger.warning("[firma:%s] %s", company.name, exc)
                errors.append(f"{company.name}: {exc}")
                company.last_result = f"Fehler: {exc}"[:290]
                continue
            except Exception as exc:
                logger.exception("[firma:%s] unerwarteter Fehler", company.name)
                errors.append(f"{company.name}: unerwarteter Fehler ({exc})")
                company.last_result = f"Unerwarteter Fehler: {exc}"[:290]
                continue

            found = 0
            for listing in listings:
                if _store_listing(listing):
                    found += 1
                    new_jobs += 1
            company.last_result = f"{len(listings)} passende Treffer, {found} davon neu."

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
