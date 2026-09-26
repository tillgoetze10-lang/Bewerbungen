"""Indeed (de.indeed.com) - Best Effort.

Indeed hat keine offene API mehr und setzt meist Bot-Schutz ein. Wird die
Anfrage blockiert, ist das kein Bug (Status "blockiert"), sondern die
Entscheidung der Seite - dann Jobs per Link-Import eintragen. robots.txt
wird respektiert, Schutzmechanismen werden nicht umgangen.

Liefert Indeed HTML aus, werden zuerst schema.org-Daten gelesen, dann die
Trefferliste, die Indeed als JSON in die Seite einbettet.
"""

import json
import re
from urllib.parse import urlencode

from .base import JobListing, ScraperError
from .http_utils import get
from .jsonld import extract_jobpostings, html_to_text

PER_PROFILE = True

SEARCH_URL = "https://de.indeed.com/jobs"
VIEW_URL = "https://de.indeed.com/viewjob?jk={jk}"
_MOSAIC_RE = re.compile(
    r'window\.mosaic\.providerData\["mosaic-provider-jobcards"\]\s*=\s*(\{.*?\});\s*\n', re.DOTALL
)


def search(profile: dict, config: dict):
    params = {"q": profile.get("keywords", ""), "l": profile.get("location", "")}
    if profile.get("location") and profile.get("radius_km"):
        params["radius"] = profile["radius_km"]
    url = f"{SEARCH_URL}?{urlencode(params)}"
    html = get(url, config)

    listings = extract_jobpostings(html, source="indeed", fallback_url=url) or _parse_mosaic(html)
    if not listings:
        raise ScraperError(
            "Indeed lieferte eine Seite ohne auslesbare Treffer (meist Bot-Prüfung oder JavaScript-Seite).",
            kind="blocked",
        )
    return listings


def _parse_mosaic(html: str):
    match = _MOSAIC_RE.search(html)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
        results = data["metaData"]["mosaicProviderJobCardsModel"]["results"]
    except (ValueError, KeyError, TypeError):
        return []
    listings = []
    for item in results:
        jk = item.get("jobkey")
        if not jk:
            continue
        salary = (item.get("salarySnippet") or {}).get("text", "") if isinstance(item.get("salarySnippet"), dict) else ""
        listings.append(
            JobListing(
                title=item.get("title") or item.get("displayTitle") or "",
                url=VIEW_URL.format(jk=jk),
                source="indeed",
                company=item.get("company", "") or "",
                location=item.get("formattedLocation", "") or "",
                salary=salary or "",
                description=html_to_text(item.get("snippet", "")),
                posted_at=str(item.get("pubDate", "") or ""),
            )
        )
    return [l for l in listings if l.is_valid()]
