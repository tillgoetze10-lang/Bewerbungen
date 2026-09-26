from . import adzuna, arbeitsagentur, crewunited, google_jobs, indeed, jooble, stepstone

# Reihenfolge = Reihenfolge im Suchlauf. LinkedIn ist bewusst nicht dabei
# (Nutzungsbedingungen verbieten automatisierte Abfragen) - LinkedIn-Jobs
# per "Job hinzufügen -> Link" eintragen.
REGISTRY = {
    "arbeitsagentur": arbeitsagentur,
    "adzuna": adzuna,
    "jooble": jooble,
    "crewunited": crewunited,
    "google_jobs": google_jobs,
    "indeed": indeed,
    "stepstone": stepstone,
}

SOURCE_LABELS = {
    "arbeitsagentur": "Jobbörse der Arbeitsagentur",
    "adzuna": "Adzuna",
    "jooble": "Jooble",
    "crewunited": "Crew United",
    "google_jobs": "Google Jobs (über SerpApi)",
    "indeed": "Indeed",
    "stepstone": "StepStone",
    "link": "Link-Import",
    "linkedin": "LinkedIn (Link-Import)",
    "xing": "XING (Link-Import)",
    "manuell": "Manuell",
}

SOURCE_HINTS = {
    "arbeitsagentur": "Offizielle Schnittstelle der Bundesagentur für Arbeit. Kein Schlüssel nötig, zuverlässigste Quelle.",
    "adzuna": "Offizielle, kostenlose API. Bündelt Anzeigen vieler Jobbörsen und Firmenseiten. Braucht App ID und App Key.",
    "jooble": "Offizielle API, bündelt viele Jobbörsen. Schlüssel kostenlos auf Anfrage.",
    "crewunited": "Film- und TV-Branche. Wird einmal pro Suchlauf abgefragt.",
    "google_jobs": "Über den Dienst SerpApi, kostenpflichtig ab 100 Suchen pro Monat. Braucht einen SerpApi-Schlüssel.",
    "indeed": "Blockiert automatische Abfragen (HTTP 403). Jobs besser per Link-Import eintragen.",
    "stepstone": "Blockiert automatische Abfragen (Zeitüberschreitung). Jobs besser per Link-Import eintragen.",
}


def source_label(key: str) -> str:
    if key.startswith("firma:"):
        return f"Firma: {key[len('firma:'):]}"
    return SOURCE_LABELS.get(key, key)
