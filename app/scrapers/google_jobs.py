"""Google Jobs (Google for Jobs) hat keine offizielle kostenlose Public API.

Statt Google direkt zu scrapen (fragil, ToS-Risiko), nutzt dieses Modul
optional SerpApi (https://serpapi.com/google-jobs-api) - einen Drittanbieter,
der Google-Jobs-Ergebnisse ueber eine offizielle, TOS-konforme API liefert.
Ohne serpapi_key in config.yaml wird diese Quelle einfach uebersprungen.
"""

from .base import JobListing, ScraperError
from .http_utils import get
import json

SERPAPI_URL = "https://serpapi.com/search.json"


def search(profile: dict, config: dict):
    api_key = config.get("serpapi_key")
    if not api_key:
        raise ScraperError(
            "google_jobs ist aktiviert, aber kein serpapi_key in config.yaml gesetzt - "
            "Quelle wird uebersprungen. Siehe https://serpapi.com/google-jobs-api"
        )
    params = {
        "engine": "google_jobs",
        "q": f"{profile.get('keywords', '')} {profile.get('location', '')}".strip(),
        "api_key": api_key,
        "hl": "de",
    }
    raw = get(SERPAPI_URL, config, params=params)
    data = json.loads(raw)
    listings = []
    for job in data.get("jobs_results", []):
        listings.append(
            JobListing(
                title=job.get("title", ""),
                url=(job.get("share_link") or job.get("apply_options", [{}])[0].get("link", "")),
                source="google_jobs",
                company=job.get("company_name", ""),
                location=job.get("location", ""),
                description=(job.get("description", "") or "")[:5000],
                posted_at=job.get("detected_extensions", {}).get("posted_at", ""),
            )
        )
    return [listing for listing in listings if listing.is_valid()]
