"""Liest aus einer Stellenanzeige: Kurzbeschreibung/Aufgaben, Voraussetzungen,
geforderte Bewerbungsunterlagen, Ansprechpartner (Name/E-Mail/Telefon) und
die normale Firmen-Website.

Heuristik, kein Verstehen - deshalb meldet extract_details() immer mit,
was NICHT gefunden wurde (missing_fields + confidence). Das UI zeigt das
als "bitte pruefen" an, alle Felder bleiben von Hand korrigierbar.
"""

import html as html_lib
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from .scrapers.jsonld import extract_raw_jobposting_node, html_to_text, jobposting_to_listing

FIELDS = [
    "tasks", "requirements", "application_documents",
    "contact_name", "contact_email", "contact_phone", "company_website",
]
# Telefon fehlt bewusst: steht selten in Anzeigen, soll nicht als "Problem" auftauchen.
REPORTED_FIELDS = ["tasks", "requirements", "application_documents", "contact_name", "contact_email", "company_website"]

FIELD_LABELS = {
    "tasks": "Aufgaben",
    "requirements": "Voraussetzungen",
    "application_documents": "Bewerbungsunterlagen",
    "contact_name": "Ansprechpartner",
    "contact_email": "E-Mail",
    "contact_phone": "Telefon",
    "company_website": "Firmen-Website",
}

CONFIDENCE_LABELS = {
    "vollstaendig": "Vollständig ausgelesen",
    "teilweise": "Teilweise ausgelesen – Lücken bitte prüfen",
    "unsicher": "Nichts Verwertbares gefunden – bitte aus der Anzeige ergänzen",
}

PLATFORM_DOMAINS = [
    "stepstone", "indeed", "linkedin", "xing", "arbeitsagentur", "crew-united", "glassdoor", "kununu",
    "monster", "google", "facebook", "instagram", "twitter", "x.com", "youtube", "tiktok", "vimeo",
    "jooble", "ziprecruiter", "meinestadt", "jobware", "stellenanzeigen", "sentry", "wixpress",
    "example.", "schema.org", "w3.org", "cloudflare", "gstatic", "doubleclick",
]
# Freemailer: als Kontakt-Adresse ok (kleine Produktionsfirmen!), sagt aber
# nichts ueber die Firmen-Website.
FREEMAIL_DOMAINS = [
    "gmx.", "web.de", "gmail.", "googlemail.", "t-online.", "outlook.", "hotmail.", "yahoo.",
    "icloud.", "freenet.", "posteo.", "mailbox.org", "aol.",
]
NOISE_DOMAINS = PLATFORM_DOMAINS + FREEMAIL_DOMAINS
# Bewerbermanagement-Systeme: Karriereseite liegt dort, Firmen-Website ist das nicht.
ATS_DOMAINS = [
    "personio", "softgarden", "smartrecruiters", "greenhouse", "lever.co", "workday", "recruitee",
    "join.com", "onlyfy", "rexx", "dvinci", "d.vinci", "umantis", "successfactors", "bamboohr",
    "workable", "jobs.ch", "concludis", "perbility", "haufe",
]

NAME_STOPWORDS = {
    "bei", "fragen", "sie", "ihre", "ihr", "wir", "bitte", "impressum", "datenschutz", "team", "personal",
    "personalabteilung", "recruiting", "human", "resources", "bewerbung", "jetzt", "hier", "unser",
    "unsere", "kontakt", "karriere", "standort", "telefon", "mail", "e-mail", "adresse", "gmbh", "und",
    "oder", "der", "die", "das", "zur", "zum", "für", "mit", "abteilung", "nutzen", "anfahrt", "formular",
    "service", "support", "hotline", "zentrale", "office", "jobs", "stellenangebote", "cookie", "cookies",
    "einstellungen", "newsletter", "presse", "agb", "haben", "gerne", "freuen", "uns", "melde", "dich",
}

_LABEL = (
    r"(?i:(?:ihr(?:e)?|dein(?:e)?|euer|eure|your)\s+)?"
    r"(?i:ansprechpartner(?:in|innen)?|ansprechperson|kontaktperson|kontakt|contact\s+person|contact)"
)
_NAME_WORD = r"[A-ZÄÖÜ][a-zäöüß]+(?:-[A-ZÄÖÜ][a-zäöüß]+)?"
CONTACT_NAME_RE = re.compile(
    _LABEL + r"[\s:\-–]+(?:(?i:herr|frau|mr\.?|ms\.?|mrs\.?)\s+)?(?:(?:Dr\.|Prof\.)\s+)*"
    r"(" + _NAME_WORD + r"(?:\s+(?:von\s+|van\s+|de\s+|zu\s+)?" + _NAME_WORD + r"){1,2})"
)
SALUTATION_NAME_RE = re.compile(
    r"(?i:herr|frau)\s+(?:(?:Dr\.|Prof\.)\s+)*(" + _NAME_WORD + r"(?:\s+" + _NAME_WORD + r")?)"
)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-zA-Z]{2,}")
PHONE_LABELED_RE = re.compile(r"(?i:tel(?:efon|\.)?|phone|fon|mobil|handy)\s*[.:]?\s*(\+?\(?\d[\d\s/\-().]{5,}\d)")
PHONE_INTL_RE = re.compile(r"(\+49[\s/\-]?(?:\(0\))?\s?\d[\d\s/\-]{5,}\d)")

TASK_HEADINGS = [
    "deine aufgaben", "ihre aufgaben", "aufgaben", "das erwartet dich", "was dich erwartet",
    "was sie erwartet", "das erwartet sie", "dein job", "deine rolle", "ihre rolle", "tätigkeiten",
    "das machst du", "was du machst", "your tasks", "responsibilities", "your role", "what you will do",
    "aufgabengebiet", "deine mission",
]
REQUIREMENT_HEADINGS = [
    "dein profil", "ihr profil", "profil", "das bringst du mit", "was du mitbringst", "das bringen sie mit",
    "was sie mitbringen", "anforderungen", "voraussetzungen", "wir erwarten", "das solltest du mitbringen",
    "was wir uns wünschen", "was wir uns wuenschen", "das wünschen wir uns", "your profile",
    "requirements", "qualifications", "what you bring", "qualifikationen", "du bringst mit",
]
APPLICATION_HEADINGS = [
    "bewerbung", "deine bewerbung", "ihre bewerbung", "so bewirbst du dich", "bewerbungsunterlagen",
    "interesse geweckt", "haben wir dein interesse", "haben wir ihr interesse", "how to apply", "bewirb dich",
]
OTHER_HEADINGS = [
    "wir bieten", "das bieten wir", "unser angebot", "benefits", "was wir bieten", "über uns",
    "wer wir sind", "kontakt", "we offer", "about us", "deine vorteile", "ihre vorteile", "gehalt",
    "arbeitszeit", "das erwartet dich bei uns", "unsere benefits", "warum wir",
]
ALL_HEADINGS = TASK_HEADINGS + REQUIREMENT_HEADINGS + APPLICATION_HEADINGS + OTHER_HEADINGS
HEADING_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6", "strong", "b", "p", "span", "div", "dt", "label", "th"]

APPLICATION_CONTEXT_RE = re.compile(
    r"bewerb|unterlagen|zusenden|zuschicken|schick|sende|send|submit|apply|application|"
    r"mitschicken|einreichen|anhängen|hochladen|upload|beifügen|beilegen", re.IGNORECASE
)
APPLICATION_DOC_PATTERNS = {
    "Anschreiben": [r"anschreiben", r"cover letter", r"motivationsschreiben"],
    "Lebenslauf": [r"lebenslauf", r"\bcv\b", r"curriculum vitae", r"\bvita\b", r"\bresume\b"],
    "Zeugnisse / Nachweise": [r"zeugnis", r"zertifikat", r"nachweis"],
    "Showreel / Arbeitsproben": [
        r"showreel", r"demo[\s-]?reel", r"\breel\b", r"arbeitsprobe", r"\bportfolio\b",
        r"arbeitsbeispiel", r"referenzprojekt", r"link zu (?:deinen|ihren) arbeiten",
    ],
    "Gehaltsvorstellung": [r"gehaltsvorstellung", r"gehaltswunsch", r"salary expectation"],
    "Frühester Eintrittstermin": [r"eintrittstermin", r"frühestmöglich", r"verfügbarkeit", r"start date", r"earliest start"],
}


def _norm(text: str) -> str:
    return " ".join((text or "").split()).lower().strip(" :!?.–-•*")


def _matches_heading(label: str, headings) -> bool:
    for h in headings:
        if label == h:
            return True
        if " " in h and h in label and len(label) <= len(h) + 20:
            return True
        # Einzelwoerter nur am Anfang: "Profil & Skills" ja, "Unternehmensprofil" nein.
        if " " not in h and label.startswith(h + " ") and len(label) <= len(h) + 20:
            return True
    return False


def _clean_soup(html: str) -> BeautifulSoup:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "template", "iframe", "form", "button"]):
        tag.decompose()
    return soup


def _main_text(soup: BeautifulSoup) -> str:
    """Seitentext ohne Navigation/Footer - dort stehen Impressums-Mails und
    Menuepunkte, keine Ansprechpartner der Stelle. Faellt auf den ganzen Text
    zurueck, falls danach kaum etwas uebrig bleibt."""
    full = soup.get_text("\n", strip=True)
    trimmed = BeautifulSoup(str(soup), "html.parser")
    for tag in trimmed(["nav", "footer", "header", "aside"]):
        tag.decompose()
    text = trimmed.get_text("\n", strip=True)
    return text if len(text) > 200 or len(text) > 0.4 * len(full) else full


def _section_from_dom(soup, headings) -> str:
    for el in soup.find_all(HEADING_TAGS):
        label = _norm(el.get_text(" ", strip=True))
        if not label or len(label) > 70 or not _matches_heading(label, headings):
            continue
        own = {id(x) for x in el.descendants}
        items = []
        for nxt in el.next_elements:
            if id(nxt) in own or not isinstance(nxt, Tag):
                continue
            if nxt.name in ("h1", "h2", "h3", "h4", "h5", "h6") and items:
                break
            if nxt.name in HEADING_TAGS:
                text = _norm(nxt.get_text(" ", strip=True))
                if text and len(text) <= 70 and _matches_heading(text, ALL_HEADINGS) and not _matches_heading(text, headings):
                    break
            if nxt.name == "li":
                item = " ".join(nxt.get_text(" ", strip=True).split())
                if item and item not in items:
                    items.append(item)
                if len(items) >= 15:
                    break
        if items:
            return "\n".join(f"• {i}" for i in items)[:2500]
    return ""


def _section_from_text(text: str, headings) -> str:
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for i, line in enumerate(lines):
        if len(line) > 70 or not _matches_heading(_norm(line), headings):
            continue
        out = []
        for following in lines[i + 1: i + 30]:
            if len(following) <= 70 and _matches_heading(_norm(following), ALL_HEADINGS):
                break
            out.append(following)
            if sum(len(x) for x in out) > 1800:
                break
        if out:
            return "\n".join(out)[:2500]
    return ""


def _section(soup, text, headings) -> str:
    return _section_from_dom(soup, headings) or _section_from_text(text, headings)


def _is_noise_domain(host: str) -> bool:
    host = (host or "").lower()
    return any(d in host for d in NOISE_DOMAINS)


def _is_ats_domain(host: str) -> bool:
    host = (host or "").lower()
    return any(d in host for d in ATS_DOMAINS)


def _root_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""


def _find_contact_name(text: str) -> str:
    for regex in (CONTACT_NAME_RE, SALUTATION_NAME_RE):
        for match in regex.finditer(text):
            name = match.group(1).strip()
            if not any(word.lower() in NAME_STOPWORDS for word in re.split(r"[\s-]+", name)):
                return name
    return ""


def _find_email(text: str, contact_name: str) -> str:
    text = re.sub(r"\s*[\(\[\{]\s*(?:at|ät)\s*[\)\]\}]\s*", "@", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*[\(\[\{]\s*(?:dot|punkt)\s*[\)\]\}]\s*", ".", text, flags=re.IGNORECASE)
    candidates = []
    for email in dict.fromkeys(EMAIL_RE.findall(text)):
        local, _, domain = email.lower().partition("@")
        if any(d in domain for d in PLATFORM_DOMAINS) or local.startswith(("noreply", "no-reply", "datenschutz", "privacy", "dsb", "webmaster", "abuse")):
            continue
        score = 0
        if re.search(r"bewerb|job|karriere|career|recruit|personal|\bhr\b|talent|people", local):
            score += 3
        last_name = contact_name.split()[-1].lower() if contact_name else ""
        if last_name and last_name in local:
            score += 4
        if local in ("info", "kontakt", "contact", "office", "mail", "hallo", "hello"):
            score -= 1
        candidates.append((score, email))
    candidates.sort(key=lambda c: -c[0])
    return candidates[0][1] if candidates else ""


def _find_phone(text: str) -> str:
    for regex in (PHONE_LABELED_RE, PHONE_INTL_RE):
        for match in regex.finditer(text):
            number = " ".join(match.group(1).split())
            digits = re.sub(r"\D", "", number)
            if 7 <= len(digits) <= 15:
                return number
    return ""


def _find_company_website(soup, node, email: str, page_url: str, company_page: bool) -> str:
    if node:
        org = node.get("hiringOrganization")
        if isinstance(org, dict):
            candidates = org.get("sameAs") or []
            if isinstance(candidates, str):
                candidates = [candidates]
            candidates = list(candidates) + [org.get("url") or ""]
            for url in candidates:
                if isinstance(url, str) and url.startswith(("http://", "https://")):
                    host = urlparse(url).netloc
                    if not _is_noise_domain(host) and not _is_ats_domain(host):
                        return _root_url(url)

    for link in soup.find_all("a", href=True):
        label = _norm(link.get_text(" ", strip=True))
        href = link["href"].strip()
        if not href.startswith(("http://", "https://")):
            continue
        if any(k in label for k in ("website", "webseite", "homepage", "zur firma", "zum unternehmen")) or label.startswith("www."):
            host = urlparse(href).netloc
            if not _is_noise_domain(host) and not _is_ats_domain(host):
                return _root_url(href)

    if company_page and page_url:
        host = urlparse(page_url).netloc
        if host and not _is_noise_domain(host) and not _is_ats_domain(host):
            return _root_url(page_url)

    if email:
        domain = email.split("@", 1)[1].lower()
        if not _is_noise_domain(domain) and not _is_ats_domain(domain):
            return f"https://{domain}"
    return ""


def _application_documents(soup, text: str) -> str:
    scan = []
    section = _section(soup, text, APPLICATION_HEADINGS)
    if section:
        scan.append(section)
    for sentence in re.split(r"(?<=[.!?])\s+|\n", text):
        if APPLICATION_CONTEXT_RE.search(sentence):
            scan.append(sentence)
    haystack = "\n".join(scan).lower()
    hits = [label for label, patterns in APPLICATION_DOC_PATTERNS.items()
            if any(re.search(p, haystack) for p in patterns)]
    return ", ".join(hits)


def empty_result() -> dict:
    result = {field: "" for field in FIELDS}
    result.update({
        "found_fields": [], "missing_fields": list(REPORTED_FIELDS), "confidence": "unsicher",
        "listing": {}, "page_text": "",
    })
    return result


def extract_details(html: str, page_url: str = "", company_page: bool = False) -> dict:
    soup = _clean_soup(html)
    text = _main_text(soup)
    result = empty_result()

    node = extract_raw_jobposting_node(html)
    if node:
        listing = jobposting_to_listing(node, source="", fallback_url=page_url)
        result["listing"] = {
            k: getattr(listing, k) for k in ("title", "company", "location", "salary", "description", "posted_at")
            if getattr(listing, k)
        }
        for key in ("responsibilities",):
            if node.get(key):
                result["tasks"] = html_to_text(node[key])[:2500]
        parts = [html_to_text(node.get(k)) for k in ("qualifications", "experienceRequirements", "educationRequirements", "skills")
                 if node.get(k) and not isinstance(node.get(k), dict)]
        if parts:
            result["requirements"] = "\n".join(p for p in parts if p)[:2500]
        # JSON-LD-Beschreibung: bei JavaScript-Seiten oft der einzige Volltext.
        desc_html = node.get("description")
        if desc_html:
            desc_soup = _clean_soup(html_lib.unescape(str(desc_html)))
            desc_text = desc_soup.get_text("\n", strip=True)
            result["tasks"] = result["tasks"] or _section(desc_soup, desc_text, TASK_HEADINGS)
            result["requirements"] = result["requirements"] or _section(desc_soup, desc_text, REQUIREMENT_HEADINGS)
            if desc_text[:200] not in text:
                text = f"{text}\n{desc_text}"

    result["tasks"] = result["tasks"] or _section(soup, text, TASK_HEADINGS)
    result["requirements"] = result["requirements"] or _section(soup, text, REQUIREMENT_HEADINGS)
    result["application_documents"] = _application_documents(soup, text)
    result["contact_name"] = _find_contact_name(text)
    result["contact_email"] = _find_email(text, result["contact_name"])
    result["contact_phone"] = _find_phone(text)
    result["company_website"] = _find_company_website(soup, node, result["contact_email"], page_url, company_page)

    result["page_text"] = text[:6000]
    result["found_fields"] = [f for f in REPORTED_FIELDS if result[f]]
    result["missing_fields"] = [f for f in REPORTED_FIELDS if not result[f]]
    core = sum(1 for f in ("tasks", "requirements", "application_documents", "company_website") if result[f])
    core += 1 if (result["contact_name"] or result["contact_email"]) else 0
    result["confidence"] = "vollstaendig" if core >= 4 else ("teilweise" if core >= 1 else "unsicher")
    return result
