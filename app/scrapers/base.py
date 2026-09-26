from dataclasses import dataclass, field


@dataclass
class JobListing:
    """Normalisierte Job-Daten, die jeder Scraper liefern muss."""

    title: str
    url: str
    source: str
    company: str = ""
    location: str = ""
    salary: str = ""
    description: str = ""
    posted_at: str = ""

    def is_valid(self) -> bool:
        return bool(self.title and self.url)


class ScraperError(Exception):
    """Wird geworfen, wenn eine Quelle nicht abgefragt werden konnte (Block, Timeout, ...).

    fetch_jobs.py faengt das ab, loggt eine Warnung und macht mit den anderen
    Quellen weiter, statt den ganzen Lauf abzubrechen.
    """
