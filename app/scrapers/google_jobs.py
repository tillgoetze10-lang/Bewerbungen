"""Google Jobs ueber SerpApi (https://serpapi.com/google-jobs-api).

Google selbst hat keine oeffentliche Jobs-API und direktes Scraping waere
fragil und ToS-widrig. SerpApi ist ein Drittanbieter mit offizieller API
(eigener Key noetig, kostenlos nur mit kleinem Kontingent). Ohne
serpapi_key in config.yaml bleibt die Quelle aus.
"""

from .base import JobListing, ScraperError
from .http_utils import get_json

PER_PROFILE = True
REQUIRED_SETTINGS = ["serpapi_key"]

SERPAPI_URL = "https://serpapi.com/search.json"


def search(profile: dict, config: dict):
    api_key = config.get("serpapi_key")
    if not api_key:
        raise ScraperError("Google Jobs: SerpApi-Schlüssel fehlt (Einstellungen).", kind="config")

    query = f"{profile.get('keywords', '')} {profile.get('location', '')}".strip()
    data = get_json(SERPAPI_URL, config, params={"engine": "google_jobs", "q": query, "api_key": api_key, "hl": "de", "gl": "de"})
    if isinstance(data, dict) and data.get("error"):
        if "hasn't returned any results" in str(data["error"]):
            return []
        raise ScraperError(f"SerpApi: {data['error']}", kind="config")

    listings = []
    for job in data.get("jobs_results", []):
        apply_options = job.get("apply_options") or [{}]
        url = job.get("share_link") or apply_options[0].get("link", "")
        listings.append(
            JobListing(
                title=job.get("title", ""),
                url=url,
                source="google_jobs",
                company=job.get("company_name", ""),
                location=job.get("location", ""),
                description=(job.get("description", "") or "")[:6000],
                posted_at=(job.get("detected_extensions") or {}).get("posted_at", ""),
            )
        )
    return [l for l in listings if l.is_valid()]
