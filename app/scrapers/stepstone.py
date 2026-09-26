"""StepStone - Best Effort ueber eingebettete schema.org/JobPosting-Daten.

StepStone setzt haeufig Bot-Schutz ein. Blockiert die Seite, ist das kein
Bug (Status "blockiert") - dann Jobs per Link-Import eintragen.
"""

from urllib.parse import quote

from .base import ScraperError
from .http_utils import get
from .jsonld import extract_jobpostings

PER_PROFILE = True

SEARCH_URL_TMPL = "https://www.stepstone.de/jobs/{keywords}/in-{location}"
SEARCH_URL_NO_LOCATION = "https://www.stepstone.de/jobs/{keywords}"


def _slug(value: str) -> str:
    return quote(value.strip().replace(" ", "-"))


def search(profile: dict, config: dict):
    keywords = _slug(profile.get("keywords", "")) or "jobs"
    location = profile.get("location", "").strip()
    if location:
        url = SEARCH_URL_TMPL.format(keywords=keywords, location=_slug(location))
        if profile.get("radius_km"):
            url += f"?radius={int(profile['radius_km'])}"
    else:
        url = SEARCH_URL_NO_LOCATION.format(keywords=keywords)

    html = get(url, config)
    listings = extract_jobpostings(html, source="stepstone", fallback_url=url)
    if not listings:
        raise ScraperError(
            "StepStone lieferte eine Seite ohne auslesbare Treffer (meist Bot-Prüfung oder JavaScript-Seite).",
            kind="blocked",
        )
    return listings
