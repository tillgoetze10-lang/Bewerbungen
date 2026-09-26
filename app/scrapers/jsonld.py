"""Gemeinsame Hilfsfunktion: schema.org JobPosting aus JSON-LD extrahieren.

Viele Jobbörsen (u.a. Indeed, StepStone) betten strukturierte Daten nach
schema.org/JobPosting als <script type="application/ld+json"> ein, damit
Google-for-Jobs die Anzeige indexieren kann. Das ist der robusteste Weg,
Titel/Firma/Ort/Gehalt aus einer Job-Detailseite zu ziehen, weil er nicht
von wechselndem CSS/HTML abhaengt - vorausgesetzt die Seite liefert das
JSON-LD ueberhaupt aus (manche Seiten mit Bot-Schutz liefern schon die
Rohdaten nicht aus, siehe README).
"""

import json

from bs4 import BeautifulSoup

from .base import JobListing


def _flatten(node):
    if isinstance(node, list):
        for item in node:
            yield from _flatten(item)
    else:
        yield node


def extract_jobpostings(html: str, source: str, fallback_url: str = ""):
    """Gibt eine Liste von JobListing zurueck, die in der Seite als
    JobPosting-JSON-LD gefunden wurden. Leere Liste, wenn nichts gefunden wurde."""
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for tag in soup.find_all("script", type="application/ld+json"):
        raw = tag.string or tag.get_text()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        for node in _flatten(data):
            if not isinstance(node, dict):
                continue
            if node.get("@type") not in ("JobPosting", ["JobPosting"]):
                continue
            listing = _jobposting_to_listing(node, source, fallback_url)
            if listing and listing.is_valid():
                results.append(listing)
    return results


def _jobposting_to_listing(node: dict, source: str, fallback_url: str) -> JobListing:
    title = node.get("title") or ""
    url = node.get("url") or fallback_url

    org = node.get("hiringOrganization") or {}
    company = org.get("name", "") if isinstance(org, dict) else str(org)

    location = ""
    job_location = node.get("jobLocation")
    if isinstance(job_location, list) and job_location:
        job_location = job_location[0]
    if isinstance(job_location, dict):
        address = job_location.get("address", {})
        if isinstance(address, dict):
            parts = [address.get("addressLocality", ""), address.get("addressRegion", "")]
            location = ", ".join(p for p in parts if p)

    salary = ""
    base_salary = node.get("baseSalary")
    if isinstance(base_salary, dict):
        value = base_salary.get("value", {})
        if isinstance(value, dict):
            min_v, max_v, unit = value.get("minValue"), value.get("maxValue"), value.get("unitText", "")
            currency = base_salary.get("currency", "")
            if min_v or max_v:
                salary = f"{min_v or ''}-{max_v or ''} {currency} / {unit}".strip()

    description = node.get("description", "") or ""
    description = BeautifulSoup(description, "html.parser").get_text(" ", strip=True)[:5000]

    return JobListing(
        title=title,
        url=url,
        source=source,
        company=company,
        location=location,
        salary=salary,
        description=description,
        posted_at=node.get("datePosted", ""),
    )
