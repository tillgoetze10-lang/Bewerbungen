"""Jobbörse der Bundesagentur für Arbeit (größte Stellendatenbank Deutschlands).

Nutzt die öffentliche JSON-Schnittstelle, die auch die offizielle
Jobsuche-App verwendet (dokumentiert von bund.dev:
https://github.com/bundesAPI/jobsuche-api). Das ist eine API, kein
Scraping - kein Bot-Schutz, kein HTML-Raten. Viele Anzeigen, die auch auf
StepStone/Indeed stehen, landen ebenfalls hier.

Hinweis: Die Schnittstelle ist öffentlich, aber nicht offiziell
dokumentiert/garantiert. Ändert die BA sie, meldet die Status-Seite einen
Fehler - dann bitte an Claude weitergeben.
"""

import base64

from .base import JobListing, ScraperError
from .http_utils import get_json

PER_PROFILE = True

BASE = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
SEARCH_PATHS = ["/pc/v4/app/jobs", "/pc/v6/jobs"]
DETAIL_PATH = "/pc/v4/jobdetails/{ref}"
HEADERS = {"X-API-Key": "jobboerse-jobsuche"}
PUBLIC_DETAIL_URL = "https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}"


def search(profile: dict, config: dict):
    params = {
        "was": profile.get("keywords", ""),
        "size": 50,
        "page": 1,
        "veroeffentlichtseit": 30,
        "pav": "false",
    }
    if profile.get("location"):
        params["wo"] = profile["location"]
        params["umkreis"] = profile.get("radius_km") or 25

    data, last_error = None, None
    for path in SEARCH_PATHS:
        try:
            data = get_json(BASE + path, config, params=params, headers=HEADERS)
            break
        except ScraperError as exc:
            last_error = exc
            if "HTTP 404" not in str(exc) and "HTTP 410" not in str(exc):
                raise
    if data is None:
        raise last_error

    if not isinstance(data, dict):
        raise ScraperError("Arbeitsagentur: unerwartetes Antwortformat (kein JSON-Objekt).")

    offers = data.get("stellenangebote") or []
    listings = []
    for offer in offers:
        refnr = offer.get("refnr") or ""
        place = offer.get("arbeitsort") or {}
        location = ", ".join(p for p in [place.get("ort", ""), place.get("region", "")] if p)
        external = offer.get("externeUrl") or ""
        url = external if external.startswith(("http://", "https://")) else PUBLIC_DETAIL_URL.format(refnr=refnr)
        listings.append(
            JobListing(
                title=(offer.get("titel") or offer.get("beruf") or "").strip(),
                url=url,
                source="arbeitsagentur",
                company=offer.get("arbeitgeber", "") or "",
                location=location,
                posted_at=offer.get("aktuelleVeroeffentlichungsdatum", "") or "",
                description=offer.get("beruf", "") or "",
                ref=refnr,
            )
        )
    return [l for l in listings if l.is_valid()]


def detail_html(listing: JobListing, config: dict) -> str:
    """Stellenbeschreibung per Detail-API holen und als einfaches HTML
    zurueckgeben, damit app/extraction.py sie wie jede andere Seite liest.
    (Die Web-Detailseite der BA wird per JavaScript gerendert und liefert
    beim direkten Abruf keinen Inhalt.)"""
    if not listing.ref:
        return ""
    encoded = base64.b64encode(listing.ref.encode("utf-8")).decode("ascii")
    data = get_json(BASE + DETAIL_PATH.format(ref=encoded), config, headers=HEADERS)
    if not isinstance(data, dict):
        return ""

    description = data.get("stellenangebotsBeschreibung") or data.get("stellenbeschreibung") or ""
    parts = [f"<h1>{data.get('stellenangebotsTitel') or listing.title}</h1>"]
    parts.append("<div>" + description.replace("\n", "<br>") + "</div>")

    # Website/Kontakt-URLs, falls die API sie mitliefert (Feldnamen variieren).
    for key, value in data.items():
        if isinstance(value, str) and value.startswith(("http://", "https://")) and "url" in key.lower():
            parts.append(f'<p>Website: <a href="{value}">{value}</a></p>')
    return "\n".join(parts)
