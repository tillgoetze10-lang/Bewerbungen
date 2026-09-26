"""Bewertet Jobs nach Berufsbild + persoenlicher Standort-Strategie.

Nur eine Empfehlung - nichts wird automatisch geloescht. Jobs ganz ohne
Bezug zum Berufsbild werden beim Suchlauf gar nicht erst importiert.

Standort-Strategie (Vorgabe des Nutzers):
- Koeln (+ direktes Umland): Zielort, immer interessant.
- Frankfurt am Main: nur, wenn der Job naeher ans Filmset bringt
  (Set-Abteilungen oder Produktions-/Postproduktionsumfeld).
- Ueberall sonst: nur zeitlich begrenzte Einsaetze (z.B. 1-2 Wochen am Set),
  kein dauerhafter Umzug.

Begriffs-Flags:
  b = nur als eigenes Wort (verhindert "Kreditor" -> "Editor", "Kredit" -> "DIT")
  c = mehrdeutig, zaehlt nur mit Film/Video-Kontext ("Runner" im Restaurant,
      "Account Manager" im Vertrieb, "Produktionsleitung" in der Fabrik ...)
"""

import re
from collections import namedtuple

SET_DEPARTMENTS = {"Produktion & Aufnahmeleitung", "Kamera am Set", "Licht & Grip"}

JOB_TITLE_TAXONOMY = {
    "Produktion & Aufnahmeleitung": [
        "set runner", ("runner", "bc"), ("set pa", "b"), ("blocker", "bc"),
        "aufnahmeleit", "location scout", ("location manager", "c"),
        ("produktionsleit", "c"), ("production manager", "c"), ("produktionsassist", "c"),
        ("production assistant", "c"), ("produktionskoordinat", "c"), ("production coordinator", "c"),
        "regieassist", "script continuity", "continuity",
    ],
    "Kamera am Set": [
        "kameramann", "kamerafrau", "kameraleute", "director of photography", ("dop", "b"),
        "bildgestalt", "kamera operator", "camera operator", "kamera assist", "camera assistant",
        ("1st ac", "b"), ("2nd ac", "b"), "first assistant camera", "second assistant camera",
        "focus puller", "schärfenzieh", "clapper loader", ("dit", "b"),
        "digital imaging technician", "data wrangler", "steadicam",
    ],
    "Videografie & Content": [
        "videograf", "videograph", "video producer", "video content", ("content creator", "c"),
        "social media video", "filmmaker", "filmemacher",
    ],
    "Postproduktion & Schnitt": [
        "video editor", "film editor", ("editor", "bc"), ("cutter", "b"), "schnittassist",
        "assistant editor", "colorist", "colourist", "color grad", "colour grad", ("vfx", "b"),
        ("compositor", "c"), "sound designer", "sound editor", ("tonmeister", "c"), ("tontechnik", "c"),
        r"re:mediengestalter\S*(?:\s*\(\S+\))?\s*(?:für\s+|-\s*)?bild\s*(?:und|&|u\.)\s*ton",
        ("mediengestalter", "c"), "postprodu", "post produ",
    ],
    "Licht & Grip": [
        "gaffer", "oberbeleuchter", "best boy", "beleuchter", ("lichttechnik", "c"), ("electrician", "c"),
        "genny operator", "key grip", ("grip", "bc"), "kamerabühne",
    ],
    "Motion Design & Technik": [
        "motion design", ("animator", "c"), ("3d artist", "c"), ("av techniker", "b"), "medientechnik",
        ("veranstaltungstechnik", "c"), "studio operator", ("broadcast", "c"),
    ],
    "Agentur, Konzeption & Einstieg": [
        ("junior producer", "c"), ("creative producer", "c"), ("producer", "bc"),
        ("projektmanager", "c"), ("project manager", "c"), ("account manager", "c"),
        ("art director", "c"), ("creative director", "c"), ("copywriter", "c"), ("konzepter", "c"),
        ("praktik", "c"), ("volont", "c"), ("werkstudent", "c"),
    ],
}

# Film/Video-Kontext fuer mehrdeutige Begriffe. Im Titel reicht ein Treffer,
# in der Beschreibung braucht es mindestens zwei verschiedene - sonst wuerde
# schon "Kennenlernen per Video" einen Vertriebsjob zum Videojob machen.
# Bewusst eng gefasst: "Schnittstelle", "Dreher", "Videocall", "Serienfertigung"
# duerfen NICHT als Film-Kontext zaehlen.
CONTEXT_PATTERNS = [
    r"video(?![\s-]*(?:call|konferenz|interview|chat|telefonie|gespräch|meeting|ident))",
    r"\bfilm", r"film(?:e|en|s)?\b", r"bewegtbild", r"kamera", r"\bdreh(?:arbeiten|tag|tage|ort|orte|zeit|plan|buch|s)\b",
    r"(?:video|film)schnitt|\bschnitt(?:programm|platz|software)?\b", r"postprodu", r"post-produ",
    r"\btv\b", r"fernseh", r"broadcast", r"youtube", r"tiktok", r"\breels?\b", r"werbespot",
    r"(?:tv|fernseh|web)[\s-]?serie", r"\bkino", r"bild und ton", r"premiere pro", r"davinci",
    r"after effects", r"\bavid\b", r"final cut", r"\bam set\b", r"medienproduktion", r"motion design",
]

TARGET_LOCATIONS = [
    "köln", "koeln", "cologne", "hürth", "huerth", "frechen", "pulheim",
    "bergisch gladbach", "leverkusen", "brühl", "bruehl",
]
CONDITIONAL_LOCATIONS = ["frankfurt"]
NOT_CONDITIONAL = ["frankfurt (oder)", "frankfurt/oder", "frankfurt an der oder", "frankfurt(oder)"]
REMOTE_PATTERNS = [r"remote", r"home[\s-]?office", r"mobiles arbeiten", r"ortsunabhängig"]
UNSPECIFIC_LOCATIONS = {"deutschland", "germany", "bundesweit", "de", "deutschlandweit"}

FILM_SET_SIGNALS = [
    r"\bam set\b", r"\bon set\b", r"filmset", r"\bdreh(?:arbeiten|tag|tage|ort|orte|zeit|plan|s)?\b",
    r"spielfilm", r"kinofilm", r"(?:tv|fernseh|web)[\s-]?serie", r"fernsehproduktion", r"tv-produktion",
    r"filmproduktion", r"produktionsfirma", r"postprodu", r"post-produ", r"aufnahmeleit", r"on location",
    r"kamerabühne",
]
# "kurzfristig" fehlt bewusst: "wir suchen kurzfristig" meint meist "ab sofort".
TEMP_SIGNALS = [
    r"(?<!un)befristet", r"projektbasis", r"projektbezogen", r"drehtage", r"tagesgage", r"tagessatz",
    r"freelance", r"freiberuflich", r"freie mitarbeit", r"auf zeit", r"temporär", r"temporaer",
    r"projekteinsatz", r"produktionsdauer", r"für die dauer", r"aushilfe",
]


def _compile_term(term: str, flags: str):
    if term.startswith("re:"):
        return re.compile(term[3:], re.IGNORECASE)
    sep = "\x00"
    body = re.escape(term.lower().replace(" ", sep).replace("-", sep))
    body = body.replace(re.escape(sep), r"[\s\-/]?").replace(sep, r"[\s\-/]?")
    if "b" in flags:
        body = rf"(?<![a-zäöüß]){body}(?:in|innen|s)?(?![a-zäöüß])"
    return re.compile(body, re.IGNORECASE)


_TERMS = []
for _dept, _entries in JOB_TITLE_TAXONOMY.items():
    for _entry in _entries:
        _term, _flags = (_entry, "") if isinstance(_entry, str) else _entry
        _TERMS.append((_compile_term(_term, _flags), _dept, "c" in _flags))

_CONTEXT_RES = [re.compile(p, re.IGNORECASE) for p in CONTEXT_PATTERNS]
_SET_RE = re.compile("|".join(FILM_SET_SIGNALS), re.IGNORECASE)
_TEMP_RE = re.compile("|".join(TEMP_SIGNALS), re.IGNORECASE)
_REMOTE_RE = re.compile("|".join(REMOTE_PATTERNS), re.IGNORECASE)

TitleMatch = namedtuple("TitleMatch", "score departments reason candidate")


def has_film_context(title: str, description: str = "") -> bool:
    if any(p.search(title or "") for p in _CONTEXT_RES):
        return True
    return sum(1 for p in _CONTEXT_RES if p.search(description or "")) >= 2


def _matches(text: str, context: bool):
    strong, weak, pending = set(), set(), False
    for pattern, dept, needs_context in _TERMS:
        if pattern.search(text or ""):
            if not needs_context:
                strong.add(dept)
            elif context:
                weak.add(dept)
            else:
                pending = True
    return strong, weak, pending


def score_title(title: str, description: str = "", assume_context: bool = False) -> TitleMatch:
    """Wie gut passt das Berufsbild? assume_context=True fuer Quellen, die
    selbst schon Film/Video sind (Crew United, hinterlegte Medienfirmen)."""
    context = assume_context or has_film_context(title, description)

    strong, weak, pending_title = _matches(title, context)
    if strong:
        depts = sorted(strong | weak)
        return TitleMatch(1.0, depts, f"Berufsbild passt: {', '.join(depts)}.", False)
    if weak:
        depts = sorted(weak)
        return TitleMatch(0.85, depts, f"Berufsbild passt (mit Film-/Video-Bezug): {', '.join(depts)}.", False)

    d_strong, d_weak, pending_desc = _matches(description, context)
    if d_strong or d_weak:
        depts = sorted(d_strong | d_weak)
        return TitleMatch(0.5, depts, f"Titel unklar, Beschreibung nennt: {', '.join(depts)}.", False)

    return TitleMatch(
        0.0, [], "Kein Bezug zu Video/Film erkennbar.", pending_title or pending_desc
    )


def _contains_any(text: str, terms) -> bool:
    text = (text or "").lower()
    return any(t in text for t in terms)


def _is_conditional_city(text: str) -> bool:
    text = (text or "").lower()
    return _contains_any(text, CONDITIONAL_LOCATIONS) and not _contains_any(text, NOT_CONDITIONAL)


def score_location(location: str, title: str, description: str, departments=()):
    loc = (location or "").strip()
    if loc.lower().strip(" ,.") in UNSPECIFIC_LOCATIONS:
        loc = ""
    body = f"{title or ''} {description or ''}"
    set_related = bool(_SET_RE.search(body)) or bool(SET_DEPARTMENTS & set(departments))

    if _contains_any(loc, TARGET_LOCATIONS):
        return 1.0, "Standort Köln/Umland – dein Zielort."
    if _REMOTE_RE.search(loc) or _REMOTE_RE.search(title or ""):
        return 0.9, "Remote/ortsunabhängig – kein Umzug nötig."
    if loc and _is_conditional_city(loc):
        if set_related:
            return 0.9, "Frankfurt mit Set-/Produktionsbezug – bringt dich näher ans Filmset."
        return 0.2, "Frankfurt ohne Set-/Produktionsbezug – laut deiner Strategie eher nicht."

    if not loc:
        if _contains_any(body, TARGET_LOCATIONS):
            return 0.9, "Kein Standortfeld, aber der Anzeigentext nennt Köln/Umland."
        if _is_conditional_city(body):
            return (0.7, "Kein Standortfeld, Text nennt Frankfurt mit Set-Bezug.") if set_related else (
                0.3, "Kein Standortfeld, Text nennt Frankfurt ohne Set-Bezug.")
        if _TEMP_RE.search(body):
            return 0.9, "Standort unbekannt, aber zeitlich begrenzter Einsatz – passt ohne Umzug."
        return 0.5, "Standort unbekannt – bitte kurz prüfen."

    if _TEMP_RE.search(body):
        return 0.9, f"{loc}: zeitlich begrenzter Einsatz/Freelance – ok ohne Umzug."
    return 0.1, f"{loc}: dauerhafte Stelle außerhalb Köln/Frankfurt – laut deiner Strategie eher nicht."


def score_job(title: str, description: str, location: str, assume_context: bool = False):
    """Gesamtbewertung: (score 0-1, label 'top'|'pruefen'|'unpassend', Begruendung)."""
    title_match = score_title(title, description, assume_context)
    location_score, location_reason = score_location(location, title, description, title_match.departments)

    score = round(title_match.score * location_score, 2)
    if score >= 0.75:
        label = "top"
    elif score >= 0.45:
        label = "pruefen"
    else:
        label = "unpassend"
    return score, label, f"{title_match.reason} {location_reason}"


LABEL_TEXT = {
    "top": "Top-Treffer",
    "pruefen": "Prüfen",
    "unpassend": "Eher unpassend",
}
