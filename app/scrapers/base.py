from dataclasses import dataclass


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
    ref: str = ""  # quellen-interne ID (z.B. Referenznummer der Arbeitsagentur)

    def is_valid(self) -> bool:
        return bool(self.title and self.url and self.url.lower().startswith(("http://", "https://")))


class ScraperError(Exception):
    """Eine Quelle konnte nicht abgefragt werden.

    kind:
      "blocked" - die Seite laesst automatische Abfragen nicht zu (Bot-Schutz,
                  robots.txt, JavaScript-only). Kein Bug; umgehen waere weder
                  sauber noch rechtlich sinnvoll -> Link-Import nutzen.
      "error"   - echter Fehler (Netzwerk, Layout geaendert, Bug) -> Claude fixen lassen.
      "config"  - Einstellung fehlt (z.B. API-Key).
    """

    def __init__(self, message: str, kind: str = "error"):
        super().__init__(message)
        self.kind = kind
