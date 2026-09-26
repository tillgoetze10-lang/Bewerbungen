"""Anschreiben-Vorlagen mit Platzhaltern.

In der Vorlage schreibst du z.B. {anrede} oder {firma}; beim Einfuegen in
eine Bewerbung werden die Werte des Jobs eingesetzt. Unbekannte Platzhalter
bleiben einfach stehen, damit nichts still verschwindet.
"""

import re
from datetime import date

PLACEHOLDERS = [
    ("{anrede}", "„Sehr geehrte Frau Schmidt,“ – oder „Sehr geehrte Damen und Herren,“"),
    ("{anrede_du}", "„Hallo Anna,“ – oder „Hallo zusammen,“ (in der Branche oft üblich)"),
    ("{firma}", "Name der Firma"),
    ("{stelle}", "Titel der Stelle"),
    ("{ort}", "Einsatzort"),
    ("{ansprechpartner}", "Name des Ansprechpartners"),
    ("{quelle}", "Wo du die Stelle gefunden hast"),
    ("{datum}", "Heutiges Datum"),
]

DEFAULT_TEMPLATE_NAME = "Standard"
DEFAULT_TEMPLATE = """{datum}

Bewerbung als {stelle}

{anrede}

mit großem Interesse habe ich Ihre Ausschreibung {quelle} gelesen. ...

[Warum {firma}? Was reizt dich an der Stelle?]

[Deine passende Erfahrung: Kamera, Schnitt, Set ...]

Über eine Einladung zu einem persönlichen Gespräch freue ich mich sehr.

Mit freundlichen Grüßen
"""

_SOURCE_PHRASES = {
    "arbeitsagentur": "in der Jobbörse der Bundesagentur für Arbeit",
    "adzuna": "online",
    "jooble": "online",
    "crewunited": "auf Crew United",
    "google_jobs": "online",
    "indeed": "auf Indeed",
    "stepstone": "auf StepStone",
    "linkedin": "auf LinkedIn",
    "xing": "auf XING",
    "dwdl": "auf DWDL.jobs",
}


def _source_phrase(source: str) -> str:
    if source.startswith("firma:"):
        return "auf Ihrer Karriereseite"
    return _SOURCE_PHRASES.get(source, "")


def _clean_title(title: str) -> str:
    # "(m/w/d)", "(all genders)" usw. gehoeren nicht ins Anschreiben
    return re.sub(r"\s*\((?:[mwdfx]\s*/\s*)+[mwdfx]\)|\s*\(all genders?\)", "", title or "", flags=re.IGNORECASE).strip()


def anrede(job) -> str:
    name = (job.contact_name or "").strip()
    last_name = name.split()[-1] if name else ""
    if last_name and job.contact_salutation == "Frau":
        return f"Sehr geehrte Frau {last_name},"
    if last_name and job.contact_salutation == "Herr":
        return f"Sehr geehrter Herr {last_name},"
    if name:
        return f"Guten Tag {name},"
    return "Sehr geehrte Damen und Herren,"


def anrede_du(job) -> str:
    name = (job.contact_name or "").strip()
    return f"Hallo {name.split()[0]}," if name else "Hallo zusammen,"


def fill_template(body: str, job, today=None) -> str:
    today = today or date.today()
    values = {
        "{anrede}": anrede(job),
        "{anrede_du}": anrede_du(job),
        "{firma}": job.company or "Ihr Unternehmen",
        "{stelle}": _clean_title(job.title),
        "{ort}": (job.location or "").split(",")[0].strip() or "[Ort]",
        "{ansprechpartner}": job.contact_name or "",
        "{quelle}": _source_phrase(job.source or ""),
        "{datum}": today.strftime("%d.%m.%Y"),
    }
    text = body or ""
    if not values["{quelle}"]:
        text = text.replace(" {quelle}", "")
    for key, value in values.items():
        text = text.replace(key, value)
    return text
