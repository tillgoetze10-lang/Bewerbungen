import threading
import time
import urllib.robotparser
from urllib.parse import urlparse

import requests

from .base import ScraperError

# Zertifikate ueber den Zertifikatsspeicher des Betriebssystems pruefen (wie der
# Browser). Behebt "CERTIFICATE_VERIFY_FAILED ... unable to get local issuer
# certificate", das bei Python von python.org auf dem Mac haeufig auftritt.
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:  # Paket fehlt/alte Python-Version -> Standard-Zertifikate von requests
    pass

_robots_cache = {}
_last_request_at = {}
_lock = threading.Lock()

# RobotFileParser.read() nutzt urllib OHNE Timeout und kann eine haengende
# Seite unbegrenzt blockieren - daher holen wir robots.txt selbst per requests.
_ROBOTS_TIMEOUT_SECONDS = 6
# Hoeflichkeitspause pro Host: wir sind ein privater Nutzer, kein Crawler.
_MIN_SECONDS_BETWEEN_REQUESTS_PER_HOST = 1.0

BLOCKED_STATUS = {401, 403, 429, 999}


def _host_of(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _polite_wait(host: str):
    with _lock:
        last = _last_request_at.get(host, 0.0)
        wait = _MIN_SECONDS_BETWEEN_REQUESTS_PER_HOST - (time.monotonic() - last)
        _last_request_at[host] = time.monotonic() + max(wait, 0)
    if wait > 0:
        time.sleep(wait)


def _robots_allowed(url: str, user_agent: str) -> bool:
    """Prueft robots.txt (pro Host gecacht). Nicht ladbar/Timeout = nicht verboten."""
    host = _host_of(url)
    if host not in _robots_cache:
        rp = urllib.robotparser.RobotFileParser()
        try:
            resp = requests.get(f"{host}/robots.txt", headers={"User-Agent": user_agent}, timeout=_ROBOTS_TIMEOUT_SECONDS)
            if resp.status_code >= 400:
                rp = None
            else:
                rp.parse(resp.text.splitlines())
        except requests.RequestException:
            rp = None
        _robots_cache[host] = rp

    rp = _robots_cache[host]
    return True if rp is None else rp.can_fetch(user_agent, url)


def _short_reason(exc) -> str:
    text = str(exc)
    for marker in ("NameResolutionError", "Name or service not known", "nodename nor servname",
                   "Connection refused", "ProxyError", "Tunnel connection failed", "timed out",
                   "Network is unreachable", "CERTIFICATE_VERIFY_FAILED"):
        if marker in text:
            return marker
    return type(exc).__name__


def _decode(resp) -> str:
    # requests nimmt bei "text/html" ohne charset ISO-8859-1 an -> aus "Köln"
    # wird "KÃ¶ln" und kein Standort-Abgleich greift mehr. Deshalb: ohne
    # explizites charset zuerst UTF-8 versuchen.
    content_type = resp.headers.get("Content-Type", "").lower()
    if "charset" in content_type:
        return resp.text
    try:
        return resp.content.decode("utf-8")
    except UnicodeDecodeError:
        resp.encoding = resp.apparent_encoding
        return resp.text


def _request(url, config, params=None, headers=None, respect_robots=True):
    user_agent = config.get("user_agent", "Mozilla/5.0")
    all_headers = {"User-Agent": user_agent, "Accept-Language": "de-DE,de;q=0.9,en;q=0.6"}
    all_headers.update(headers or {})
    timeout = config.get("http_timeout_seconds", 15)

    check_url = requests.Request("GET", url, params=params).prepare().url if params else url
    if respect_robots and not _robots_allowed(check_url, user_agent):
        raise ScraperError(
            f"robots.txt von {urlparse(url).netloc} erlaubt keine automatischen Abfragen dieser Seite.",
            kind="blocked",
        )

    _polite_wait(_host_of(url))
    host = urlparse(url).netloc
    try:
        resp = requests.get(url, headers=all_headers, params=params, timeout=timeout)
    except requests.Timeout as exc:
        # Seiten mit Bot-Schutz lassen automatische Anfragen oft einfach haengen.
        raise ScraperError(f"{host} antwortet nicht auf automatische Anfragen (Zeitüberschreitung).", kind="blocked") from exc
    except requests.exceptions.SSLError as exc:
        raise ScraperError(f"Zertifikatsproblem bei {host} ({_short_reason(exc)}).") from exc
    except requests.ConnectionError as exc:
        raise ScraperError(f"Keine Verbindung zu {host} ({_short_reason(exc)}).", kind="network") from exc
    except requests.RequestException as exc:
        raise ScraperError(f"Netzwerkfehler bei {host} ({_short_reason(exc)}).") from exc

    if resp.status_code in BLOCKED_STATUS:
        raise ScraperError(
            f"{urlparse(url).netloc} blockiert automatische Abfragen (HTTP {resp.status_code}, Bot-Schutz).",
            kind="blocked",
        )
    if resp.status_code >= 400:
        raise ScraperError(f"{urlparse(url).netloc} antwortete mit HTTP {resp.status_code} ({url}).")
    return resp


def get(url: str, config: dict, params: dict = None, respect_robots: bool = True, headers: dict = None) -> str:
    """HTML/Text abrufen. respect_robots=False nur fuer Einzel-Abrufe, die der
    Nutzer selbst ausloest (Link-Import) und fuer offizielle APIs - alle
    automatischen Seitenabrufe respektieren robots.txt."""
    return _decode(_request(url, config, params=params, headers=headers, respect_robots=respect_robots))


def get_json(url: str, config: dict, params: dict = None, headers: dict = None):
    """JSON von einer API abrufen (APIs sind keine Crawl-Ziele -> kein robots.txt-Check)."""
    resp = _request(url, config, params=params, headers=headers, respect_robots=False)
    try:
        return resp.json()
    except ValueError as exc:
        raise ScraperError(f"{urlparse(url).netloc} lieferte kein gültiges JSON.") from exc


def post_json(url: str, config: dict, payload: dict, headers: dict = None):
    """JSON an eine API senden und JSON zurueck bekommen (z.B. Jooble)."""
    all_headers = {"User-Agent": config.get("user_agent", "Mozilla/5.0"), "Content-Type": "application/json"}
    all_headers.update(headers or {})
    timeout = config.get("http_timeout_seconds", 15)
    _polite_wait(_host_of(url))
    try:
        resp = requests.post(url, json=payload, headers=all_headers, timeout=timeout)
    except requests.Timeout as exc:
        raise ScraperError(f"{urlparse(url).netloc} antwortet nicht (Zeitüberschreitung).", kind="blocked") from exc
    except requests.ConnectionError as exc:
        raise ScraperError(f"Keine Verbindung zu {urlparse(url).netloc} ({_short_reason(exc)}).", kind="network") from exc
    except requests.RequestException as exc:
        raise ScraperError(f"Netzwerkfehler bei {urlparse(url).netloc} ({_short_reason(exc)}).") from exc
    if resp.status_code in (401, 403):
        raise ScraperError(f"{urlparse(url).netloc} hat den API-Schlüssel abgelehnt (HTTP {resp.status_code}).", kind="config")
    if resp.status_code >= 400:
        raise ScraperError(f"{urlparse(url).netloc} antwortete mit HTTP {resp.status_code}.")
    try:
        return resp.json()
    except ValueError as exc:
        raise ScraperError(f"{urlparse(url).netloc} lieferte kein gültiges JSON.") from exc
