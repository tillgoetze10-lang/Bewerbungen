"""Einzel-Import per Link - fuer jede Quelle nutzbar (auch LinkedIn), weil
genau eine Seite abgerufen wird, die der Nutzer selbst ausgewaehlt hat.
Details (Aufgaben, Kontakt, ...) werden aus derselben Seite gelesen."""

from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..extraction import extract_details
from .base import JobListing, ScraperError
from .http_utils import get
from .jsonld import extract_jobpostings

SOURCE_BY_DOMAIN = {
    "linkedin": "linkedin",
    "indeed": "indeed",
    "stepstone": "stepstone",
    "crew-united": "crewunited",
    "arbeitsagentur": "arbeitsagentur",
    "xing": "xing",
}


def guess_source(url: str) -> str:
    host = urlparse(url).netloc.lower()
    for key, source in SOURCE_BY_DOMAIN.items():
        if key in host:
            return source
    return "link"


def fetch_from_url(url: str, config: dict):
    """Gibt (JobListing, details) zurueck."""
    if not url.lower().startswith(("http://", "https://")):
        raise ScraperError("Bitte einen vollständigen Link angeben (beginnt mit https://).", kind="config")

    source = guess_source(url)
    html = get(url, config, respect_robots=False)
    details = extract_details(html, page_url=url)

    listings = extract_jobpostings(html, source=source, fallback_url=url)
    if listings:
        listing = listings[0]
        listing.url = url
        return listing, details

    soup = BeautifulSoup(html, "html.parser")

    def meta(name):
        tag = soup.find("meta", property=name) or soup.find("meta", attrs={"name": name})
        return tag.get("content", "").strip() if tag else ""

    title = meta("og:title") or (soup.title.string.strip() if soup.title and soup.title.string else "")
    if not title:
        raise ScraperError("Aus dem Link ließ sich kein Titel lesen – bitte den Job unten manuell anlegen.")

    listing = JobListing(
        title=title[:300],
        url=url,
        source=source,
        company=meta("og:site_name") if source == "link" else "",
        description=meta("og:description") or meta("description"),
    )
    return listing, details
