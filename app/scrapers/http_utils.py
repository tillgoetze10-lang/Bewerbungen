import requests

from .base import ScraperError


def get(url: str, config: dict, params: dict = None) -> str:
    headers = {"User-Agent": config.get("user_agent", "Mozilla/5.0")}
    timeout = config.get("http_timeout_seconds", 15)
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=timeout)
    except requests.RequestException as exc:
        raise ScraperError(f"Netzwerkfehler bei {url}: {exc}") from exc
    if resp.status_code == 403 or resp.status_code == 429:
        raise ScraperError(
            f"{url} hat mit HTTP {resp.status_code} geantwortet - vermutlich Bot-Schutz. "
            "Diese Quelle laesst sich moeglicherweise nicht automatisiert abfragen; "
            "bitte den Job stattdessen per 'Schnell hinzufuegen (Link)' im Web-UI eintragen."
        )
    if resp.status_code >= 400:
        raise ScraperError(f"{url} antwortete mit HTTP {resp.status_code}")
    return resp.text
