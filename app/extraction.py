"""Extrahiert Ansprechpartner, Firmen-Website, Voraussetzungen und geforderte
Bewerbungsunterlagen aus einer Job-Detailseite.

Das ist bewusst kein "Vertrau mir"-Feature: Stellenanzeigen sind extrem
unterschiedlich formatiert, ein Text-Heuristik-Ansatz wird nie 100% treffen.
Deshalb liefert extract_details() zu jedem Job auch mit, welche Felder
gefunden wurden und welche nicht (found_fields/missing_fields) sowie eine
confidence-Einstufung - das Board zeigt das sichtbar an ("bitte pruefen"),
und alle Felder bleiben im UI von Hand korrigierbar. Das ist die Art von
"Selbstueberwachung", die hier ehrlich umsetzbar ist: nicht "die KI ist
sich sicher", sondern "die KI sagt dir, was sie NICHT sicher weiss".
"""

import re

from bs4 import BeautifulSoup

from .scrapers.base import ScraperError
from .scrapers.http_utils import get
from .scrapers.jsonld import extract_raw_jobposting_node

FIELDS = ["contact_name", "contact_email", "contact_phone", "company_website", "requirements", "application_documents"]

FIELD_LABELS = {
    "contact_name": "Ansprechpartner",
    "contact_email": "E-Mail",
    "contact_phone": "Telefon",
    "company_website": "Firmen-Website",
    "requirements": "Voraussetzungen",
    "application_documents": "Bewerbungsunterlagen",
}

CONFIDENCE_LABELS = {
    "vollstaendig": "Vollständig extrahiert",
    "teilweise": "Teilweise extrahiert - bitte prüfen",
    "unsicher": "Automatisch nicht auffindbar - bitte manuell ausfüllen/prüfen",
}

CONTACT_NAME_RE = re.compile(
    r"(?:(?:ihr[e]?|dein[e]?|euer)?\s*ansprechpartner(?:in)?|kontakt(?:person)?)[:\s]+"
    r"([A-ZÄÖÜ][a-zäöüß\-]+(?:\s+[A-ZÄÖÜ][a-zäöüß\-]+){1,3})",
    re.IGNORECASE,
)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(\+49[\s/\-]?\d[\d\s/\-]{6,}\d|0\d{2,5}[\s/\-]?\d{3,}[\d\s/\-]*\d)")

REQUIREMENT_HEADINGS = [
    "dein profil", "ihr profil", "das bringst du mit", "was du mitbringst",
    "anforderungen", "voraussetzungen", "wir erwarten", "das solltest du mitbringen",
    "your profile", "requirements", "qualifications", "was wir uns wuenschen",
    "was wir uns wünschen",
]

APPLICATION_DOC_KEYWORDS = {
    "Anschreiben": ["anschreiben", "cover letter", "motivationsschreiben"],
    "Lebenslauf": ["lebenslauf", "curriculum vitae", " cv "],
    "Zeugnisse": ["zeugnis", "zeugnisse", "arbeitszeugnis", "schulzeugnis"],
    "Arbeitsproben / Portfolio": ["arbeitsprobe", "portfolio", "showreel", "reel", "demo tape"],
    "Gehaltsvorstellung": ["gehaltsvorstellung", "gehaltswunsch", "salary expectation"],
    "Frühester Eintrittstermin": ["eintrittstermin", "frühestmöglich", "verfügbar ab", "start date", "earliest start"],
}


def _looks_like_heading(line: str) -> bool:
    if len(line) > 70 or not line:
        return False
    if line.endswith((".", "!", "?", ",")):
        return False
    return line.istitle() or line.isupper() or line.endswith(":")


def _extract_section(text: str, headings) -> str:
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    lower_lines = [l.lower() for l in lines]
    for i, line in enumerate(lower_lines):
        if len(line) < 80 and any(h in line for h in headings):
            collected = []
            for l in lines[i + 1: i + 1 + 30]:
                if len(collected) >= 2 and _looks_like_heading(l):
                    break
                collected.append(l)
            block = " ".join(collected).strip()
            if block:
                return block[:1800]
    return ""


def _requirements_from_jsonld(node: dict) -> str:
    parts = []
    for key in ("qualifications", "experienceRequirements", "educationRequirements", "skills", "responsibilities"):
        val = node.get(key)
        if isinstance(val, dict):
            val = val.get("value") or val.get("name") or ""
        if val:
            parts.append(BeautifulSoup(str(val), "html.parser").get_text(" ", strip=True))
    return " ".join(parts)[:2500]


def _company_website_from_jsonld(node: dict) -> str:
    org = node.get("hiringOrganization")
    if not isinstance(org, dict):
        return ""
    same_as = org.get("sameAs")
    if isinstance(same_as, list) and same_as:
        same_as = same_as[0]
    return same_as or org.get("url") or ""


def extract_details(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    lower = text.lower()

    result = {field: "" for field in FIELDS}

    node = extract_raw_jobposting_node(html)
    if node:
        result["company_website"] = _company_website_from_jsonld(node)
        result["requirements"] = _requirements_from_jsonld(node)

    name_match = CONTACT_NAME_RE.search(text)
    if name_match:
        result["contact_name"] = name_match.group(1).strip()

    emails = EMAIL_RE.findall(text)
    if emails:
        result["contact_email"] = emails[0]

    phones = PHONE_RE.findall(text)
    if phones:
        result["contact_phone"] = phones[0].strip()

    if not result["requirements"]:
        result["requirements"] = _extract_section(text, REQUIREMENT_HEADINGS)

    doc_hits = [label for label, keywords in APPLICATION_DOC_KEYWORDS.items() if any(kw in lower for kw in keywords)]
    result["application_documents"] = ", ".join(doc_hits)

    found = [f for f in FIELDS if result[f]]
    missing = [f for f in FIELDS if not result[f]]

    if len(found) >= 4:
        confidence = "vollstaendig"
    elif found:
        confidence = "teilweise"
    else:
        confidence = "unsicher"

    result["found_fields"] = found
    result["missing_fields"] = missing
    result["confidence"] = confidence
    return result


def fetch_and_extract_details(url: str, config: dict):
    """Ruft die Job-Detailseite ab (respektiert robots.txt) und extrahiert
    Details daraus. Gibt None zurueck, wenn der Abruf fehlschlaegt - der Job
    wird dann trotzdem angelegt, nur ohne Zusatzdaten (Confidence 'unsicher')."""
    try:
        html = get(url, config)
    except ScraperError:
        return None
    try:
        return extract_details(html)
    except Exception:
        return None


EMPTY_RESULT = {**{f: "" for f in FIELDS}, "found_fields": [], "missing_fields": FIELDS, "confidence": "unsicher"}
