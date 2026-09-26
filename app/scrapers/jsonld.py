"""schema.org/JobPosting aus JSON-LD lesen.

Viele Jobseiten betten JobPosting-Daten fuer Google-for-Jobs ein. Das ist
robuster als HTML-Selektoren, weil es nicht vom Seitenlayout abhaengt.
"""

import html as html_lib
import json
import warnings

from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning

from .base import JobListing

warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)


def _is_jobposting(node) -> bool:
    if not isinstance(node, dict):
        return False
    types = node.get("@type")
    if isinstance(types, str):
        types = [types]
    return isinstance(types, list) and "JobPosting" in types


def _walk(node):
    """Alle Knoten inkl. Listen und "@graph"-Container (Yoast & Co.)."""
    if isinstance(node, list):
        for item in node:
            yield from _walk(item)
    elif isinstance(node, dict):
        yield node
        if "@graph" in node:
            yield from _walk(node["@graph"])


def _jsonld_nodes(page_html: str):
    soup = BeautifulSoup(page_html, "html.parser")
    for tag in soup.find_all("script", type="application/ld+json"):
        raw = tag.string or tag.get_text()
        if not raw:
            continue
        try:
            data = json.loads(raw.strip())
        except (json.JSONDecodeError, TypeError):
            continue
        yield from _walk(data)


def html_to_text(value) -> str:
    if not value:
        return ""
    text = html_lib.unescape(str(value))
    if "<" not in text:
        return " ".join(text.split())
    return BeautifulSoup(text, "html.parser").get_text(" ", strip=True)


def extract_raw_jobposting_node(page_html: str):
    for node in _jsonld_nodes(page_html):
        if _is_jobposting(node):
            return node
    return None


def extract_jobpostings(page_html: str, source: str, fallback_url: str = ""):
    results = []
    for node in _jsonld_nodes(page_html):
        if not _is_jobposting(node):
            continue
        listing = jobposting_to_listing(node, source, fallback_url)
        if listing.is_valid():
            results.append(listing)
    return results


def _location_of(node: dict) -> str:
    job_location = node.get("jobLocation")
    if isinstance(job_location, list) and job_location:
        job_location = job_location[0]
    if isinstance(job_location, dict):
        address = job_location.get("address", {})
        if isinstance(address, dict):
            parts = [address.get("addressLocality", ""), address.get("addressRegion", "")]
            return ", ".join(p for p in parts if isinstance(p, str) and p)
        if isinstance(address, str):
            return address
    if str(node.get("jobLocationType", "")).upper() == "TELECOMMUTE":
        return "Remote"
    return ""


def _salary_of(node: dict) -> str:
    base_salary = node.get("baseSalary")
    if not isinstance(base_salary, dict):
        return ""
    value = base_salary.get("value", {})
    currency = base_salary.get("currency", "")
    if isinstance(value, dict):
        min_v, max_v, unit = value.get("minValue"), value.get("maxValue"), value.get("unitText", "")
        if value.get("value") and not (min_v or max_v):
            min_v = max_v = value.get("value")
        if min_v or max_v:
            span = f"{min_v}" if min_v == max_v else f"{min_v or '?'}–{max_v or '?'}"
            return f"{span} {currency} / {unit}".strip(" /")
    elif isinstance(value, (int, float)):
        return f"{value} {currency}".strip()
    return ""


def jobposting_to_listing(node: dict, source: str, fallback_url: str = "") -> JobListing:
    url = node.get("url") if isinstance(node.get("url"), str) else ""
    if not url.lower().startswith(("http://", "https://")):
        url = fallback_url

    org = node.get("hiringOrganization") or {}
    company = org.get("name", "") if isinstance(org, dict) else str(org)

    return JobListing(
        title=html_to_text(node.get("title") or "")[:300],
        url=url,
        source=source,
        company=(company or "")[:200],
        location=_location_of(node)[:200],
        salary=_salary_of(node),
        description=html_to_text(node.get("description") or "")[:6000],
        posted_at=str(node.get("datePosted", ""))[:50],
    )
