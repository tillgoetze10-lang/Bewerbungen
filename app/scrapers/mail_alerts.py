"""Job-Alarme aus dem eigenen E-Mail-Postfach.

LinkedIn, Indeed, StepStone, XING & Co. verbieten automatische Abfragen ihrer
Seiten - verschicken aber selbst Job-Alarme per Mail. Diese Mails liest die
App (nur lesend: kein "gelesen"-Markieren, nichts wird geloescht oder
gesendet) und uebernimmt die Stellen-Links. Die Detailseiten dieser Portale
werden NICHT automatisch abgerufen; Titel/Firma/Ort kommen aus der Mail.

Zugang: IMAP mit App-Passwort (bei iCloud/Gmail Pflicht, nicht das normale
Passwort). Daten liegen nur lokal in data/app.db.
"""

import email
import html as html_lib
import imaplib
import re
from datetime import date, timedelta
from email import policy
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup

from .base import JobListing, ScraperError

PER_PROFILE = False
REQUIRED_SETTINGS = ["mail_address", "mail_password"]

PROVIDERS = {
    "icloud": ("iCloud", "imap.mail.me.com", "https://support.apple.com/de-de/102654"),
    "gmail": ("Gmail", "imap.gmail.com", "https://support.google.com/accounts/answer/185833?hl=de"),
    "gmx": ("GMX", "imap.gmx.net", "https://hilfe.gmx.net/pop-imap/imap/imap-serverdaten.html"),
    "webde": ("WEB.DE", "imap.web.de", "https://hilfe.web.de/pop-imap/imap/imap-serverdaten.html"),
    "outlook": ("Outlook / Hotmail", "outlook.office365.com", "https://support.microsoft.com/de-de/account-billing"),
    "tonline": ("T-Online", "secureimap.t-online.de", "https://www.telekom.de/hilfe/festnetz-internet-tv/e-mail"),
}

# Absender, deren Mails nach Stellen-Links durchsucht werden.
SENDERS = ["linkedin.com", "indeed.com", "stepstone.de", "xing.com", "arbeitsagentur.de",
           "crew-united.com", "dwdl.de", "adzuna", "jooble"]
LOOKBACK_DAYS = 14
MAX_MAILS = 200

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# (Quelle, Muster, Normalform) - Tracking-Parameter fliegen raus, damit
# dieselbe Stelle aus zwei Mails nur einmal im Board landet.
LINK_PATTERNS = [
    ("linkedin", re.compile(r"linkedin\.com/(?:comm/)?jobs/view/(?:[^/?#\s]*?-)?(\d{6,})", re.I),
     lambda m: f"https://www.linkedin.com/jobs/view/{m.group(1)}/"),
    ("stepstone", re.compile(r"stepstone\.de/(stellenangebote--[^?#\s\"']+?-(\d{5,})-inline\.html)", re.I),
     lambda m: f"https://www.stepstone.de/{m.group(1)}"),
    ("xing", re.compile(r"xing\.com/jobs/([a-z0-9\-]+-\d{5,})", re.I),
     lambda m: f"https://www.xing.com/jobs/{m.group(1)}"),
    ("arbeitsagentur", re.compile(r"arbeitsagentur\.de/jobsuche/jobdetail/([\w\-]+)", re.I),
     lambda m: f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{m.group(1)}"),
    ("crewunited", re.compile(r"(crew-united\.com/[a-z]{2}/jobs/[^?#\s\"']+)", re.I),
     lambda m: f"https://www.{m.group(1)}"),
    ("dwdl", re.compile(r"(dwdl\.de/jobboerse/\d+_[^?#\s\"']+\.html)", re.I),
     lambda m: f"https://www.{m.group(1)}"),
]
_INDEED_JK = re.compile(r"^[0-9a-f]{16}$", re.I)

GENERIC_LINK_TEXTS = {
    "ansehen", "anzeigen", "jetzt bewerben", "bewerben", "view job", "view", "apply", "apply now",
    "mehr erfahren", "details", "zum job", "job ansehen", "stelle ansehen", "hier", "mehr", "see job",
    "jetzt ansehen", "easy apply", "einfach bewerben", "schnell bewerben",
}


def _candidate_urls(href: str):
    """Link selbst + evtl. in Tracking-Redirects versteckte Ziel-URLs."""
    yield href
    decoded = unquote(href)
    if decoded != href:
        yield decoded
    try:
        for values in parse_qs(urlparse(href).query).values():
            for value in values:
                if "http" in value or "%2F" in value:
                    yield unquote(value)
    except ValueError:
        pass


def canonical_job_url(href: str):
    """(quelle, normierte URL) oder None, wenn der Link keine Stellenanzeige ist."""
    for url in _candidate_urls(href or ""):
        for source, pattern, build in LINK_PATTERNS:
            match = pattern.search(url)
            if match:
                return source, build(match)
        parsed = urlparse(url)
        if "indeed." in parsed.netloc:
            jk = (parse_qs(parsed.query).get("jk") or [""])[0]
            if _INDEED_JK.match(jk):
                return "indeed", f"https://de.indeed.com/viewjob?jk={jk}"
    return None


def _lines(text: str):
    return [l.strip() for l in (text or "").split("\n") if l.strip()]


def _is_generic(text: str) -> bool:
    return (not text or len(text) < 5 or text.lower().startswith(("http://", "https://", "www."))
            or text.lower().strip(" ›>→»:.") in GENERIC_LINK_TEXTS)


def listings_from_html(html: str):
    """Stellen aus einer Job-Alarm-Mail (HTML) lesen."""
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["style", "script"]):
        tag.decompose()
    found = {}
    for link in soup.find_all("a", href=True):
        hit = canonical_job_url(link["href"])
        if not hit:
            continue
        source, url = hit
        anchor = " ".join(link.get_text(" ", strip=True).split())
        container = link.find_parent(["td", "li", "div", "tr"]) or link
        context_lines = _lines(container.get_text("\n", strip=True))[:8]

        title = anchor if not _is_generic(anchor) else next((l for l in context_lines if not _is_generic(l)), "")
        entry = found.setdefault(url, {"source": source, "title": "", "context": []})
        if title and (not entry["title"] or (len(title) > len(entry["title"]) and len(title) <= 150)):
            entry["title"] = title[:300]
        if len(context_lines) > len(entry["context"]):
            entry["context"] = context_lines

    listings = []
    for url, entry in found.items():
        if not entry["title"]:
            continue
        # Typischer Aufbau: Titel / Firma / Ort in den Zeilen direkt danach.
        rest = [l for l in entry["context"] if l != entry["title"] and not _is_generic(l) and len(l) <= 80]
        company = rest[0] if rest else ""
        location = rest[1] if len(rest) > 1 else ""
        listings.append(JobListing(
            title=entry["title"], url=url, source=entry["source"], company=company[:200], location=location[:200],
            description=" · ".join(entry["context"])[:1000],
        ))
    return listings


def _message_html(raw: bytes) -> str:
    message = email.message_from_bytes(raw, policy=policy.default)
    body = message.get_body(preferencelist=("html", "plain"))
    if body is None:
        return ""
    content = body.get_content()
    if body.get_content_type() == "text/plain":
        return _plain_to_html(content)
    return content


def _plain_to_html(text: str) -> str:
    """Klartext-Mail: jede URL zusammen mit der Zeile davor (meist der
    Stellentitel) in einen Block packen, damit derselbe Parser greift."""
    blocks, previous = [], []
    for line in (l.strip() for l in text.splitlines()):
        if not line:
            continue
        urls = re.findall(r"https?://\S+", line)
        if urls:
            label = html_lib.escape(previous[-1]) if previous else ""
            for url in urls:
                blocks.append(f'<div>{label}<br><a href="{html_lib.escape(url)}">{html_lib.escape(url)}</a></div>')
            previous = []
        else:
            previous.append(line)
    return "\n".join(blocks)


def _connect(config):
    provider = config.get("mail_provider") or "icloud"
    host = config.get("mail_imap_host") or PROVIDERS.get(provider, PROVIDERS["icloud"])[1]
    try:
        client = imaplib.IMAP4_SSL(host, 993, timeout=int(config.get("http_timeout_seconds", 15)) + 10)
    except OSError as exc:
        raise ScraperError(f"Mail-Server {host} nicht erreichbar ({type(exc).__name__}).", kind="network") from exc
    try:
        client.login(config["mail_address"], config["mail_password"])
    except imaplib.IMAP4.error as exc:
        raise ScraperError(
            "Anmeldung am Postfach fehlgeschlagen – bitte ein App-Passwort verwenden (nicht das normale Passwort).",
            kind="config",
        ) from exc
    return client


def fetch_alert_messages(config, days=LOOKBACK_DAYS):
    """Rohdaten der passenden Mails der letzten Tage (nur lesend)."""
    client = _connect(config)
    try:
        status, _ = client.select("INBOX", readonly=True)
        if status != "OK":
            raise ScraperError("Posteingang ließ sich nicht öffnen.")
        since_day = date.today() - timedelta(days=days)
        since = f"{since_day.day:02d}-{_MONTHS[since_day.month - 1]}-{since_day.year}"
        ids = []
        for sender in SENDERS:
            status, data = client.search(None, "SINCE", since, "FROM", f'"{sender}"')
            if status == "OK" and data and data[0]:
                ids.extend(data[0].split())
        ids = list(dict.fromkeys(ids))[-MAX_MAILS:]
        messages = []
        for msg_id in ids:
            status, data = client.fetch(msg_id, "(BODY.PEEK[])")
            if status == "OK" and data and isinstance(data[0], tuple):
                messages.append(data[0][1])
        return messages
    finally:
        try:
            client.logout()
        except Exception:
            pass


def search(profile: dict, config: dict):
    listings = []
    for raw in fetch_alert_messages(config):
        try:
            listings.extend(listings_from_html(_message_html(raw)))
        except Exception:
            continue
    return listings


def test_connection(config) -> str:
    """Fuer den "Verbindung testen"-Knopf: kurze Klartext-Rueckmeldung."""
    messages = fetch_alert_messages(config)
    jobs = []
    for raw in messages:
        try:
            jobs.extend(listings_from_html(_message_html(raw)))
        except Exception:
            continue
    unique = {j.url for j in jobs}
    return (f"Verbindung klappt. {len(messages)} Job-Mail(s) der letzten {LOOKBACK_DAYS} Tage gefunden, "
            f"darin {len(unique)} Stellen-Link(s).")
