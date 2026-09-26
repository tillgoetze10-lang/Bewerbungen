"""LinkedIn wird hier bewusst NICHT automatisiert durchsucht.

Gruende:
1. LinkedIns Nutzungsbedingungen untersagen explizit automatisiertes
   Scraping/Crawling der Plattform.
2. LinkedIn setzt aktiven, aggressiven Bot-Schutz ein und geht rechtlich
   gegen automatisierte Zugriffe vor (siehe z.B. hiQ Labs vs. LinkedIn).

search() existiert nur, damit dieses Modul zur gleichen Schnittstelle wie
die anderen Scraper passt - es wirft aber immer ScraperError und wird von
fetch_jobs.py uebersprungen, selbst wenn 'linkedin.enabled: true' gesetzt ist.

Empfohlener Weg fuer LinkedIn-Jobs: den Link einer Anzeige, die du dir selbst
im Browser angeschaut hast, ueber 'Schnell hinzufuegen (Link)' im Web-UI
eintragen (app/scrapers/quick_add.py) - das ist ein einzelner, von dir
ausgeloester Abruf genau einer Seite, kein automatisiertes Massen-Crawling.
"""

from .base import ScraperError


def search(profile: dict, config: dict):
    raise ScraperError(
        "LinkedIn wird aus rechtlichen Gruenden nicht automatisch durchsucht. "
        "Bitte einzelne Jobs per 'Schnell hinzufuegen (Link)' eintragen."
    )
