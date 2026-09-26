"""Indeed-Scraper.

Indeed hat 2021 seine offene Publisher-API eingestellt. Diese Implementierung
nutzt daher die oeffentliche Suchergebnisseite und liest die eingebetteten
schema.org/JobPosting-Daten aus (siehe scrapers/jsonld.py). Indeed setzt
teils Bot-Schutz ein - schlaegt der Abruf fehl (siehe http_utils.ScraperError),
wird das in fetch_jobs.py geloggt und die Quelle fuer diesen Lauf uebersprungen.
"""

from urllib.parse import urlencode

from .base import ScraperError
from .http_utils import get
from .jsonld import extract_jobpostings

SEARCH_URL = "https://de.indeed.com/jobs"


def search(profile: dict, config: dict):
    params = {"q": profile.get("keywords", ""), "l": profile.get("location", "")}
    url = f"{SEARCH_URL}?{urlencode(params)}"
    html = get(url, config)
    listings = extract_jobpostings(html, source="indeed", fallback_url=url)
    if not listings:
        raise ScraperError(
            "Indeed hat keine strukturierten Job-Daten geliefert (Seitenlayout geaendert "
            "oder Bot-Schutz). Bitte einzelne interessante Jobs ueber 'Schnell hinzufuegen (Link)' eintragen."
        )
    return listings
