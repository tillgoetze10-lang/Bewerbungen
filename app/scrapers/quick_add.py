"""Einzel-Import per Link: fuer JEDE Quelle (auch LinkedIn) nutzbar, weil hier
genau eine Seite abgerufen wird, die der Nutzer selbst ausgewaehlt hat -
kein automatisiertes Massen-Crawling. Liest zuerst JSON-LD JobPosting,
faellt sonst auf Open-Graph-Metatags zurueck.
"""

from bs4 import BeautifulSoup

from .base import JobListing, ScraperError
from .http_utils import get
from .jsonld import extract_jobpostings


def fetch_from_url(url: str, config: dict) -> JobListing:
    # respect_robots=False: das ist ein einzelner, vom Nutzer ausgeloester Abruf
    # genau einer selbst ausgewaehlten Seite (siehe http_utils.get), kein Crawling.
    html = get(url, config, respect_robots=False)

    listings = extract_jobpostings(html, source=_guess_source(url), fallback_url=url)
    if listings:
        return listings[0]

    soup = BeautifulSoup(html, "html.parser")

    def meta(name):
        tag = soup.find("meta", property=name) or soup.find("meta", attrs={"name": name})
        return tag.get("content", "").strip() if tag else ""

    title = meta("og:title") or (soup.title.string.strip() if soup.title and soup.title.string else "")
    description = meta("og:description")

    if not title:
        raise ScraperError(
            f"Konnte keinen Titel aus {url} lesen. Bitte Titel/Firma manuell im Formular ergaenzen."
        )

    return JobListing(
        title=title,
        url=url,
        source=_guess_source(url),
        description=description,
    )


def _guess_source(url: str) -> str:
    lowered = url.lower()
    for key in ("linkedin", "indeed", "stepstone", "crewunited", "crew-united"):
        if key in lowered:
            return "crewunited" if "crew" in key else key
    return "manuell"
