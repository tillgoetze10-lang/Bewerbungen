"""Crew United Jobbörse (Film-/TV-Branche, DACH).

Vorher lief dieser Scraper gegen die falsche Domain (crewunited.com statt
crew-united.com) und konnte deshalb nie etwas finden.

Crew United ist branchenspezifisch - die Jobliste wird daher einmal pro
Suchlauf geladen (nicht pro Suchprofil), gefiltert wird danach ueber die
Berufsbewertung (app/matching.py). Die HTML-Struktur konnte beim Bauen
nicht live geprueft werden (Sandbox ohne Zugriff); die Status-Seite meldet,
ob hier etwas ankommt.
"""

from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .base import JobListing, ScraperError
from .http_utils import get
from .jsonld import extract_jobpostings

PER_PROFILE = False

BASE_URL = "https://www.crew-united.com"
LIST_URLS = [f"{BASE_URL}/de/jobs/", f"{BASE_URL}/de/Jobs/"]


def search(profile: dict, config: dict):
    html, used_url, last_error = None, None, None
    for url in LIST_URLS:
        try:
            html = get(url, config)
            used_url = url
            break
        except ScraperError as exc:
            last_error = exc
            if exc.kind == "blocked":
                raise
    if html is None:
        raise last_error

    listings = extract_jobpostings(html, source="crewunited", fallback_url=used_url)
    if listings:
        return listings

    listings = _parse_listing_page(html, used_url)
    if not listings:
        raise ScraperError(
            "Crew United: Seite geladen, aber keine Stellen-Links erkannt - vermutlich hat sich "
            "das Seitenlayout geändert oder die Liste wird per JavaScript geladen."
        )
    return listings


def _parse_listing_page(html: str, page_url: str):
    soup = BeautifulSoup(html, "html.parser")
    list_path = urlparse(page_url).path.rstrip("/").lower()
    seen, listings = set(), []
    for link in soup.select("a[href]"):
        href = link.get("href", "")
        full_url = urljoin(BASE_URL, href).split("#")[0]
        path = urlparse(full_url).path.rstrip("/").lower()
        # Nur Unterseiten der Jobliste (einzelne Anzeigen), nicht die Liste selbst,
        # Filter-/Seitenlinks oder Navigation.
        if "/jobs/" not in path + "/" or path == list_path or "?" in href:
            continue
        if urlparse(full_url).netloc and "crew-united.com" not in urlparse(full_url).netloc:
            continue
        title = " ".join(link.get_text(" ", strip=True).split())
        if len(title) < 6 or full_url in seen:
            continue
        seen.add(full_url)
        listings.append(JobListing(title=title[:300], url=full_url, source="crewunited", company="", location=""))
    return listings
