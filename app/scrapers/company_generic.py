"""Generischer Scraper fuer selbst hinterlegte Firmen-Karriereseiten.

Firmen-Karriereseiten laufen auf sehr unterschiedlichen Systemen (Personio,
SmartRecruiters, Workday, Greenhouse, eigene CMS...). Es gibt daher keinen
Ansatz, der ueberall gleich gut funktioniert. Diese Implementierung probiert
zwei Strategien der Reihe nach:

1. schema.org/JobPosting JSON-LD (viele ATS-Systeme liefern das fuer SEO aus)
2. Fallback: alle Links auf der Seite einsammeln, deren sichtbarer Text nach
   einem der hinterlegten Berufsbezeichnungen klingt (app/matching.py)

Das deckt nicht jede Karriereseite ab - aber lieber eine solide Basis, die
bei manchen Firmen sofort funktioniert und sich pro Firma leicht per Hand
nachschaerfen laesst (z.B. eigene *.py-Datei mit spezifischen Selektoren,
falls eine bestimmte Firma wichtig ist und der generische Ansatz versagt).
"""

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..matching import score_title
from .base import JobListing, ScraperError
from .http_utils import get
from .jsonld import extract_jobpostings


def search_company(company_name: str, career_url: str, config: dict):
    html = get(career_url, config)
    source_name = f"firma:{company_name}"

    listings = extract_jobpostings(html, source=source_name, fallback_url=career_url)
    if not listings:
        listings = _parse_generic_links(html, career_url, source_name)

    if not listings:
        raise ScraperError(
            f"{company_name}: keine Jobs auf der Seite gefunden (weder JSON-LD noch "
            "passende Link-Texte). Seitenstruktur vermutlich zu speziell fuer den "
            "generischen Scraper - ggf. manuell pruefen oder eigenes Scraper-Modul schreiben."
        )

    # Nur Treffer behalten, die ueberhaupt zu einer der hinterlegten
    # Berufsbezeichnungen passen - sonst wuerde jede Firmenseite ihre
    # komplette (oft branchenfremde) Stellenliste ins Board kippen.
    relevant = [l for l in listings if score_title(l.title, l.description)[0] > 0]
    return relevant


def _parse_generic_links(html: str, base_url: str, source_name: str):
    soup = BeautifulSoup(html, "html.parser")
    listings = []
    seen = set()
    for link in soup.find_all("a", href=True):
        title = link.get_text(strip=True)
        href = link["href"]
        if not title or len(title) < 4:
            continue
        # Grobe Heuristik: nur Links, die selbst nach einer Stellenanzeige
        # aussehen (matching.py entscheidet inhaltlich, hier nur Rauschen raus).
        if score_title(title, "")[0] == 0:
            continue
        full_url = urljoin(base_url, href)
        if full_url in seen:
            continue
        seen.add(full_url)
        listings.append(JobListing(title=title, url=full_url, source=source_name))
    return listings
