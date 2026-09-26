"""Adzuna - Jobsuchmaschine mit offizieller, kostenloser API (Deutschland: "de").

Adzuna sammelt Anzeigen aus tausenden Quellen (Jobboersen, Firmenseiten)
und bietet sie ueber eine echte API an - legal und ohne Bot-Schutz.
Schluessel gibt es sofort und kostenlos auf https://developer.adzuna.com
(App ID + App Key), einzutragen unter "Einstellungen".
"""

from .base import JobListing, ScraperError
from .http_utils import get_json
from .jsonld import html_to_text

PER_PROFILE = True
REQUIRED_SETTINGS = ["adzuna_app_id", "adzuna_app_key"]

SEARCH_URL = "https://api.adzuna.com/v1/api/jobs/de/search/1"


def search(profile: dict, config: dict):
    app_id, app_key = config.get("adzuna_app_id"), config.get("adzuna_app_key")
    if not (app_id and app_key):
        raise ScraperError("Adzuna: App ID/App Key fehlen (Einstellungen).", kind="config")

    params = {
        "app_id": app_id,
        "app_key": app_key,
        "what": profile.get("keywords", ""),
        "results_per_page": 50,
        "max_days_old": 30,
        "content-type": "application/json",
    }
    if profile.get("location"):
        params["where"] = profile["location"]
        params["distance"] = profile.get("radius_km") or 25

    data = get_json(SEARCH_URL, config, params=params)
    if not isinstance(data, dict) or "results" not in data:
        raise ScraperError("Adzuna: unerwartetes Antwortformat.")

    listings = []
    for item in data.get("results", []):
        salary = ""
        if item.get("salary_min") or item.get("salary_max"):
            low, high = item.get("salary_min"), item.get("salary_max")
            salary = f"{int(low)}" if low and low == high else f"{int(low or 0)}–{int(high or 0)}"
            salary += " € / Jahr"
        listings.append(
            JobListing(
                title=html_to_text(item.get("title", "")),
                url=item.get("redirect_url", ""),
                source="adzuna",
                company=(item.get("company") or {}).get("display_name", ""),
                location=(item.get("location") or {}).get("display_name", ""),
                salary=salary,
                description=html_to_text(item.get("description", "")),
                posted_at=item.get("created", ""),
                ref=str(item.get("id", "")),
            )
        )
    return [l for l in listings if l.is_valid()]
