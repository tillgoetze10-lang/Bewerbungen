import urllib.robotparser
from urllib.parse import urlparse

import requests

from .base import ScraperError

_robots_cache = {}

# Bewusst kurz und unabhaengig von http_timeout_seconds: robots.txt ist ein
# Vorab-Check, der schnell durchlaufen soll. WICHTIG: RobotFileParser.read()
# (aus der Python-Standardbibliothek) nutzt urllib OHNE Timeout - eine Seite,
# die beim robots.txt-Abruf gar nicht oder sehr langsam antwortet, wuerde den
# kompletten Request sonst unbegrenzt haengen lassen (so als wuerde beim
# Klick auf "Jetzt nach neuen Jobs suchen" ueberhaupt nichts passieren).
# Deshalb holen wir robots.txt selbst per requests (mit Timeout) und fuettern
# den Text an RobotFileParser.parse() statt .read() zu benutzen.
_ROBOTS_TIMEOUT_SECONDS = 6


def _robots_allowed(url: str, user_agent: str) -> bool:
    """Prueft robots.txt der Zielseite, bevor automatisiert zugegriffen wird.
    Ergebnis wird pro Host gecacht, damit robots.txt nicht bei jedem Request
    neu geladen wird. Kann robots.txt selbst nicht geladen werden (nicht
    vorhanden, Timeout, Fehler), wird das NICHT als Verbot gewertet - viele
    Seiten haben schlicht keine robots.txt, und ein haengender Abruf darf
    die App nicht blockieren."""
    parsed = urlparse(url)
    host = f"{parsed.scheme}://{parsed.netloc}"
    if host not in _robots_cache:
        rp = urllib.robotparser.RobotFileParser()
        try:
            resp = requests.get(
                f"{host}/robots.txt",
                headers={"User-Agent": user_agent},
                timeout=_ROBOTS_TIMEOUT_SECONDS,
            )
            if resp.status_code >= 400:
                rp = None
            else:
                rp.parse(resp.text.splitlines())
        except requests.RequestException:
            rp = None  # robots.txt nicht erreichbar/Timeout -> nicht blockieren
        _robots_cache[host] = rp

    rp = _robots_cache[host]
    if rp is None:
        return True
    return rp.can_fetch(user_agent, url)


def get(url: str, config: dict, params: dict = None, respect_robots: bool = True) -> str:
    """respect_robots=False ist nur fuer den Einzel-Import per Link (quick_add.py)
    gedacht: dort ruft der Nutzer explizit genau eine Seite ab, die er sich selbst
    ausgesucht hat - das ist kein automatisiertes Crawling, an das sich robots.txt
    richtet. Alle Massenabfragen (Suchergebnisseiten, Firmen-Karriereseiten)
    respektieren robots.txt immer."""
    user_agent = config.get("user_agent", "Mozilla/5.0")
    headers = {"User-Agent": user_agent}
    timeout = config.get("http_timeout_seconds", 15)

    check_url = url
    if params:
        check_url = requests.Request("GET", url, params=params).prepare().url

    if respect_robots and not _robots_allowed(check_url, user_agent):
        raise ScraperError(
            f"robots.txt von {urlparse(url).netloc} untersagt automatisierten Zugriff auf diese "
            "Seite fuer unseren User-Agent - wird uebersprungen. Bitte den Job stattdessen per "
            "'Schnell hinzufuegen (Link)' eintragen."
        )

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
