"""StepStone-Scraper ueber eingebettete schema.org/JobPosting-Daten.

Hinweis: StepStone setzt haeufig aktiven Bot-Schutz (z.B. Cloudflare) ein.
Dieser Scraper ist bewusst defensiv gebaut (ScraperError statt Crash), damit
ein Block hier nicht den ganzen Fetch-Lauf abbricht. Funktioniert der Abruf
nicht, bitte einzelne Jobs per 'Schnell hinzufuegen (Link)' eintragen.
"""

from urllib.parse import quote

from .base import ScraperError
from .http_utils import get
from .jsonld import extract_jobpostings

SEARCH_URL_TMPL = "https://www.stepstone.de/jobs/{keywords}/in-{location}"


def search(profile: dict, config: dict):
    keywords = quote(profile.get("keywords", "").strip().replace(" ", "-"))
    location = quote(profile.get("location", "").strip().replace(" ", "-")) or "deutschland"
    url = SEARCH_URL_TMPL.format(keywords=keywords or "jobs", location=location)
    html = get(url, config)
    listings = extract_jobpostings(html, source="stepstone", fallback_url=url)
    if not listings:
        raise ScraperError(
            "StepStone hat keine strukturierten Job-Daten geliefert (Seitenlayout geaendert "
            "oder Bot-Schutz). Bitte einzelne interessante Jobs ueber 'Schnell hinzufuegen (Link)' eintragen."
        )
    return listings
