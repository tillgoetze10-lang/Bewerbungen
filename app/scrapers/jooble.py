"""Jooble - Jobsuchmaschine mit offizieller REST-API (kostenloser Schluessel
auf Anfrage ueber https://jooble.org/api/about). Schluessel unter
"Einstellungen" eintragen."""

from .base import JobListing, ScraperError
from .http_utils import post_json
from .jsonld import html_to_text

PER_PROFILE = True
REQUIRED_SETTINGS = ["jooble_key"]

API_URL = "https://jooble.org/api/{key}"
ALLOWED_RADIUS = [0, 4, 8, 16, 26, 40, 80]


def search(profile: dict, config: dict):
    key = config.get("jooble_key")
    if not key:
        raise ScraperError("Jooble: API-Schlüssel fehlt (Einstellungen).", kind="config")

    payload = {"keywords": profile.get("keywords", ""), "location": profile.get("location", ""), "page": "1"}
    if profile.get("location"):
        radius = profile.get("radius_km") or 25
        payload["radius"] = str(min(ALLOWED_RADIUS, key=lambda r: abs(r - radius)))

    data = post_json(API_URL.format(key=key), config, payload)
    if not isinstance(data, dict) or "jobs" not in data:
        raise ScraperError("Jooble: unerwartetes Antwortformat.")

    listings = [
        JobListing(
            title=html_to_text(job.get("title", "")),
            url=job.get("link", ""),
            source="jooble",
            company=job.get("company", "") or "",
            location=job.get("location", "") or "",
            salary=job.get("salary", "") or "",
            description=html_to_text(job.get("snippet", "")),
            posted_at=job.get("updated", "") or "",
            ref=str(job.get("id", "")),
        )
        for job in data.get("jobs", [])
    ]
    return [l for l in listings if l.is_valid()]
