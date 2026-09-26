"""Bewertet gefundene Jobs automatisch nach Berufsbild + Standort-Strategie.

Das Ergebnis ist eine Einschaetzung, KEIN automatischer Filter, der etwas
loescht - der Mensch entscheidet im Board weiter selbst. Ziel ist nur,
offensichtlich unpassende Treffer (falscher Beruf) beim Crawlen von
Firmen-Karriereseiten gar nicht erst reinzuholen, und alles andere schon
mit einer Ersteinschaetzung + Begruendung zu versehen.

Anpassen: die Berufsbezeichnungen unten sind bewusst zentral an einer
Stelle gesammelt, damit du sie leicht erweitern kannst, ohne Code an
mehreren Stellen zu suchen.
"""

# Departments/Berufsfelder rund um Film-/Videoproduktion, die zum Profil passen.
# Reihenfolge/Gruppierung nur zur besseren Lesbarkeit der Begruendungstexte.
JOB_TITLE_TAXONOMY = {
    "Produktion & Aufnahmeleitung": [
        "runner", "setrunner", "set-runner", "set-pa", "set pa", "production assistant",
        "blocker", "set-aufnahmeleitung", "set-aufnahmeleiter", "aufnahmeleitung",
        "aufnahmeleiter", "location scout", "location manager", "motivaufnahmeleiter",
        "produktionsleitung", "production manager", "produktionsassistenz",
        "produktionsassistent",
    ],
    "Kamera & Videografie": [
        "videograf", "videografin", "videographer", "video producer", "content creator",
        "filmmaker", "kameramann", "kamerafrau", "director of photography", "dop",
        "bildgestalter", "kameraoperator", "camera operator", "1st ac", "first assistant camera",
        "focus puller", "2nd ac", "second assistant camera", "clapper loader", "dit",
        "digital imaging technician", "kameraassistent", "kameraassistentin",
    ],
    "Postproduktion & Schnitt": [
        "editor", "video editor", "videoeditor", "video-editor", "cutter", "filmeditor",
        "montage-master", "schnittassistent", "assistant editor", "colorist", "color grader",
        "vfx compositor", "vfx artist", "sound designer", "motion sound editor",
        "mediengestalter bild und ton", "mediengestalter", "postproduktion", "post-production",
    ],
    "Licht & Grip": [
        "gaffer", "oberbeleuchter", "best boy", "beleuchter", "electrician",
        "genny operator", "key grip", "grip",
    ],
    "Motion Design & Sonstiges": [
        "motion designer", "motion design", "animator", "av-techniker", "medientechniker",
    ],
    "Agentur: Video-Allrounder": [
        "video producer", "creative producer", "social media video specialist",
        "social media video creator", "social-media-video", "videograf", "filmmaker",
    ],
    "Agentur: Organisation & Kundenkontakt": [
        "junior producer", "produktionsassistent", "production assistant",
        "projektmanager video", "account manager", "production coordinator",
        "praktikant video", "praktikant kreation", "praktikum video", "praktikum kreation",
    ],
    "Agentur: Postproduktion & Design": [
        "postproduction generalist", "post-production generalist", "studio-operator",
        "studio operator",
    ],
    "Kreative Leitung & Konzeption": [
        "konzepter", "copywriter", "art director", "creative director",
    ],
}

ALL_TERMS = [(term, dept) for dept, terms in JOB_TITLE_TAXONOMY.items() for term in terms]

# Zielstrategie Standort (siehe README fuer die Begruendung):
# - Koeln: geplanter Zielort, immer voll interessant, unabhaengig vom Level.
# - Frankfurt: nur interessant, wenn erkennbar Richtung Filmset/Produktion.
# - alles andere: nur interessant, wenn klar zeitlich begrenzt (Set-Einsatz,
#   keine dauerhafte Umzugs-Erwartung).
TARGET_CITY_TERMS = ["köln", "koeln", "cologne"]
CONDITIONAL_CITY_TERMS = ["frankfurt"]

FILM_SET_SIGNALS = [
    "set", "dreh", "drehort", "drehtag", "on location", "vor ort", "produktionsfirma",
    "filmproduktion", "postproduktion", "post-production", "aufnahmeleitung", "location",
    "filmset", "produktion",
]
TEMP_SIGNALS = [
    "befristet", "projektbasis", "drehtage", "tagessatz", "tagesgage", "kurzfristig",
    "freelance", "freiberuflich", "auf zeit", "temporaer", "temporär", "projekteinsatz",
    "produktionsdauer",
]


def _find_matches(text: str):
    text = text.lower()
    return [(term, dept) for term, dept in ALL_TERMS if term in text]


def score_title(title: str, description: str):
    """Score 0.0-1.0 + Liste betroffener Departments + Begruendung."""
    title_matches = _find_matches(title or "")
    if title_matches:
        depts = sorted({dept for _, dept in title_matches})
        return 1.0, depts, f"Berufsbezeichnung passt zu: {', '.join(depts)}."

    desc_matches = _find_matches(description or "")
    if desc_matches:
        depts = sorted({dept for _, dept in desc_matches})
        return 0.5, depts, f"Titel selbst unklar, aber Beschreibung nennt: {', '.join(depts)}."

    return 0.0, [], "Kein Bezug zu den hinterlegten Berufsbezeichnungen (Video/Film) gefunden."


def score_location(location: str, title: str, description: str):
    """Score 0.0-1.0 + Begruendungstext, nach der persoenlichen Standort-Strategie."""
    loc = (location or "").lower()
    combined = f"{title or ''} {description or ''}".lower()

    if any(term in loc for term in TARGET_CITY_TERMS):
        return 1.0, "Standort Köln passt (geplanter Zielort)."

    if any(term in loc for term in CONDITIONAL_CITY_TERMS):
        if any(sig in combined for sig in FILM_SET_SIGNALS):
            return 0.8, "Frankfurt, aber mit erkennbarem Set-/Produktionsbezug - bringt näher ans Ziel Filmset."
        return 0.2, "Frankfurt ohne erkennbaren Set-/Produktionsbezug - laut Zielsetzung eher uninteressant."

    if not loc:
        return 0.4, "Standort unbekannt - bitte manuell prüfen."

    if any(sig in combined for sig in TEMP_SIGNALS):
        return 0.6, f"Standort {location}, aber offenbar zeitlich begrenzter Set-Einsatz - dafür laut Präferenz ok (kein Umzug nötig)."

    return 0.1, f"Standort {location} passt nicht ins Zielraster (nicht Köln/Frankfurt, kein erkennbarer Kurzeinsatz/Set-Bezug)."


def score_job(title: str, description: str, location: str):
    """Gesamtbewertung eines Jobs. Gibt (score, label, reason) zurueck.

    score: 0.0-1.0
    label: 'top' | 'pruefen' | 'unpassend'
    reason: kurzer Text fuers UI, erklaert die Einschaetzung
    """
    title_score, depts, title_reason = score_title(title, description)
    location_score, location_reason = score_location(location, title, description)

    score = round(0.6 * title_score + 0.4 * location_score, 2)

    if score >= 0.75:
        label = "top"
    elif score >= 0.45:
        label = "pruefen"
    else:
        label = "unpassend"

    reason = f"{title_reason} {location_reason}"
    return score, label, reason


LABEL_TEXT = {
    "top": "Top-Treffer",
    "pruefen": "Prüfen",
    "unpassend": "Eher unpassend",
}
