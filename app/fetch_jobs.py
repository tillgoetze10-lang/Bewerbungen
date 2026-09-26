"""Durchsucht alle aktivierten Quellen fuer alle konfigurierten Suchprofile
und legt neue Jobs im Status 'neu' an (bereits bekannte URLs werden uebersprungen).

Aufruf manuell:      python -m app.fetch_jobs
Aufruf automatisch:  siehe app/scheduler.py (laeuft im Hintergrund der Web-App)
"""

import logging
import sys

from .config import load_config, source_enabled
from .models import Job, db, make_external_id
from .scrapers import REGISTRY
from .scrapers.base import ScraperError

logger = logging.getLogger(__name__)


def run_fetch_cycle(app):
    """Fuehrt einen kompletten Scraper-Durchlauf aus. Muss im Flask app_context laufen."""
    config = load_config()
    profiles = config.get("search_profiles", [])
    if not profiles:
        logger.warning("Keine search_profiles in config.yaml definiert - nichts zu tun.")
        return {"new_jobs": 0, "errors": []}

    new_jobs = 0
    errors = []

    with app.app_context():
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
                except Exception as exc:  # defensiv: ein kaputter Scraper darf den Lauf nicht stoppen
                    logger.exception("[%s] unerwarteter Fehler", source_name)
                    errors.append(f"{source_name}: unerwarteter Fehler ({exc})")
                    continue

                for listing in listings:
                    if not listing.is_valid():
                        continue
                    ext_id = make_external_id(listing.url)
                    if Job.query.filter_by(external_id=ext_id).first():
                        continue
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
                    )
                    db.session.add(job)
                    new_jobs += 1
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
