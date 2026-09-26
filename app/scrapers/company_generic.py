"""Generischer Scraper fuer hinterlegte Firmen-Karriereseiten.

Strategien der Reihe nach:
1. schema.org/JobPosting JSON-LD (viele Bewerbermanagement-Systeme liefern das)
2. Links, die nach einer einzelnen Stellenanzeige aussehen: URL enthaelt
   job/karriere/stellen/... ODER der Linktext traegt "(m/w/d)" o.ae.
   Damit landen Navigationspunkte wie "Postproduktion" oder "Kamera" einer
   Produktionsfirma NICHT als vermeintliche Jobs im Board.
Die inhaltliche Filterung (passt der Beruf?) macht app/matching.py.
"""

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..matching import score_title
from .base import JobListing, ScraperError
from .http_utils import get
from .jsonld import extract_jobpostings

JOB_URL_HINTS = ("job", "karriere", "career", "stellen", "vacanc", "position", "ausschreibung", "offene-stellen", "jobs")
GENDER_MARKER_RE = re.compile(r"\((?:m|w|d|f|x|div|all genders?)(?:\s*/\s*(?:m|w|d|f|x|div))+\)|\bm/w/d\b|\bw/m/d\b|\bm/f/d\b", re.IGNORECASE)


def search_company(company_name: str, career_url: str, config: dict):
    html = get(career_url, config)
    source_name = f"firma:{company_name}"

    listings = extract_jobpostings(html, source=source_name, fallback_url=career_url)
    if not listings:
        listings = _parse_job_links(html, career_url, source_name)

    for listing in listings:
        if not listing.company:
            listing.company = company_name

    relevant = [l for l in listings if score_title(l.title, l.description)[0] > 0]
    if not listings:
        raise ScraperError(
            f"{company_name}: Karriereseite geladen, aber keine Stellenanzeigen erkannt "
            "(evtl. per JavaScript geladen oder ungewöhnliches Layout)."
        )
    return relevant


def _looks_like_job_link(title: str, url: str, career_url: str) -> bool:
    if GENDER_MARKER_RE.search(title):
        return True
    path = urlparse(url).path.lower()
    career_path = urlparse(career_url).path.rstrip("/").lower()
    if path.rstrip("/") == career_path:
        return False
    return any(hint in path for hint in JOB_URL_HINTS) and len(path.rstrip("/")) > len(career_path)


def _parse_job_links(html: str, base_url: str, source_name: str):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    listings, seen = [], set()
    for link in soup.find_all("a", href=True):
        href = link["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        title = " ".join(link.get_text(" ", strip=True).split())
        if len(title) < 6 or len(title) > 200:
            continue
        full_url = urljoin(base_url, href).split("#")[0]
        if not full_url.startswith(("http://", "https://")) or full_url in seen:
            continue
        if not _looks_like_job_link(title, full_url, base_url):
            continue
        seen.add(full_url)
        listings.append(JobListing(title=title, url=full_url, source=source_name))
    return listings
