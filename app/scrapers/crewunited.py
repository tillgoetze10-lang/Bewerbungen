"""Crew United Jobbörse (Film-/TV-Branche, DACH).

WICHTIG: Diese Umgebung hatte beim Bauen dieses Tools keinen Internetzugriff
auf crew-united.com (Netzwerk-Policy dieser Sandbox), die HTML-Selektoren
unten sind daher ein plausibler Best-Effort-Ansatz, aber ungetestet. Bitte
nach dem ersten Lauf pruefen: kommen sinnvolle Ergebnisse? Wenn nicht, im
Browser F12 -> die Job-Liste auf https://www.crewunited.com/de/jobs
anschauen und die CSS-Selektoren unten entsprechend anpassen.

Es wird zuerst versucht, schema.org/JobPosting JSON-LD zu lesen (falls
Crew United das ausliefert); falls nicht, faellt der Code auf eine simple
Link-Heuristik zurueck.
"""

from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup

from .base import JobListing, ScraperError
from .http_utils import get
from .jsonld import extract_jobpostings

BASE_URL = "https://www.crewunited.com"
SEARCH_URL = f"{BASE_URL}/de/jobs"


def search(profile: dict, config: dict):
    params = {"q": profile.get("keywords", "")}
    url = f"{SEARCH_URL}?{urlencode(params)}" if params.get("q") else SEARCH_URL
    html = get(url, config)

    listings = extract_jobpostings(html, source="crewunited", fallback_url=url)
    if listings:
        return listings

    listings = _parse_listing_page(html, url)
    if not listings:
        raise ScraperError(
            "Crew United: keine Jobs gefunden. Die Seite liefert vermutlich weder JSON-LD "
            "noch passt die Fallback-Heuristik mehr zur aktuellen Seitenstruktur - "
            "bitte app/scrapers/crewunited.py anpassen (siehe Kommentar oben) oder Jobs "
            "manuell per 'Schnell hinzufuegen (Link)' eintragen."
        )
    return listings


def _parse_listing_page(html: str, page_url: str):
    soup = BeautifulSoup(html, "html.parser")
    listings = []
    for link in soup.select("a[href*='/jobs/']"):
        href = link.get("href", "")
        title = link.get_text(strip=True)
        if not title or "/jobs/" not in href:
            continue
        full_url = urljoin(BASE_URL, href)
        listings.append(
            JobListing(title=title, url=full_url, source="crewunited")
        )
    # Dedupe by url, keep order
    seen = set()
    unique = []
    for listing in listings:
        if listing.url in seen:
            continue
        seen.add(listing.url)
        unique.append(listing)
    return unique
