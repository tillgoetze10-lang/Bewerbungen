"""Vorschlagsliste: Film-/TV-/Werbefirmen in Koeln und Frankfurt mit Jobseite.

Recherchiert im September 2026. Schwerpunkt: Firmen, die aktuell mit guter
Arbeit auffallen (Preise, Streaming-Produktionen fuer Netflix/Prime, grosse
Serien) und Adressen, ueber die man ans Set kommt. Nur Eintraege mit einer
gefundenen Karriere-/Jobseite - Firmen ohne eigene Jobseite laufen ueber
ihre Seite bei DWDL.jobs (Medien-Jobboerse).

Ob eine Seite auslesbar ist, zeigt nach dem ersten Suchlauf die Status-Seite.
"""

# (Name, Jobseite, Warum interessant, Gruppe)
SUGGESTED_COMPANIES = [
    # --- Koeln: Serien, Film, Streaming ---
    ("btf bildundtonfabrik", "https://btf-gmbh.jobs.personio.de/",
     "Netflix: „How to Sell Drugs Online (Fast)“ – Fiction, Shows, Werbung, Köln-Ehrenfeld", "Köln – Serien, Film & Streaming"),
    ("Gaumont Deutschland", "https://www.dwdl.de/jobboerse/firma_gaumontgmbh.html",
     "Netflix: „Unfamiliar“ (2026) – Serien & Kino, Köln/Berlin", "Köln – Serien, Film & Streaming"),
    ("LEONINE Studios / W&B Television", "https://leonine.jobs.personio.de/?language=de",
     "W&B Television: Grimme-Preis 2026 („Die Nichte des Polizisten“) – Köln", "Köln – Serien, Film & Streaming"),
    ("UFA Serial Drama", "https://www.dwdl.de/jobboerse/firma_ufaserialdrama.html",
     "Tägliche Serien, viele Set-Jobs (Aufnahmeleitung, Continuity, Baubühne)", "Köln – Serien, Film & Streaming"),
    ("Bavaria Fiction", "https://www.dwdl.de/jobboerse/firma_bavariafictiongmbh.html",
     "Große Fiction-Serien, sucht laufend Set-AL, Produktionsassistenz, Fahrer", "Köln – Serien, Film & Streaming"),
    ("filmpool entertainment", "https://jobs.filmpool-entertainment.de/de/jobs",
     "Einer der größten unabhängigen TV-Produzenten, ca. 600 Leute, Hürth/Köln", "Köln – Serien, Film & Streaming"),
    ("Warner Bros. ITVP Deutschland", "https://www.wbitvpgermany.com/vacancies",
     "Entertainment & Reality, Köln", "Köln – Serien, Film & Streaming"),
    ("ITV Studios Germany", "https://www.itvstudios.de/karriere",
     "Große Shows & Factual, Köln", "Köln – Serien, Film & Streaming"),
    ("Banijay Germany", "https://banijay.de/karriere.html",
     "Dach von 25+ Produzenten (u. a. Brainpool, Endemol Shine), Köln", "Köln – Serien, Film & Streaming"),
    ("Brainpool", "https://brainpool.de/karriere/",
     "Comedy & Show, Köln-Mülheim", "Köln – Serien, Film & Streaming"),
    ("i&u Studios", "https://www.iustudios.de/karriere",
     "Dokus & Reportagen (LEONINE/Mediawan), Köln", "Köln – Serien, Film & Streaming"),
    ("Picture Puzzle Medien", "https://www.picturepuzzlemedien.de/jobs",
     "Doku & Docu-Soap für ARD, RTL, RTL2 – inhouse Postproduktion & Dreh", "Köln – Serien, Film & Streaming"),

    # --- Koeln: Sender & Studios ---
    ("MMC Studios Köln", "https://mmc.de/unternehmen/karriere/",
     "Größte Film- & TV-Studios Deutschlands, Köln-Ossendorf", "Köln – Sender & Studios"),
    ("nobeo / Gravity Media", "https://nobeo.de/category/jobs/",
     "TV-Studios, Außenübertragung & Postproduktion, Hürth", "Köln – Sender & Studios"),
    ("WDR mediagroup", "https://wdr-mediagroup.com/de/karriere",
     "Produktion & Vermarktung des WDR", "Köln – Sender & Studios"),
    ("RTL Deutschland", "https://jobsearch.createyourowncareer.com/RTL/content/search/?locale=de_DE",
     "Sender, Köln", "Köln – Sender & Studios"),

    # --- Koeln: Postproduktion, Technik, Werbung ---
    ("D-Facto Motion", "https://www.d-facto-motion.de/de/karriere/",
     "Postproduktion & VFX: Schnitt, Grading, Sound (u. a. Köln)", "Köln – Postproduktion, Technik & Werbung"),
    ("Cape Cross", "https://www.capecross.de/",
     "Film- & Studiolicht, Technik für Film/TV/Show – Einstieg Licht & Grip", "Köln – Postproduktion, Technik & Werbung"),
    ("JORDAN Production", "https://www.jordan-production.de/jobs",
     "Werbe- & Imagefilme, Köln", "Köln – Postproduktion, Technik & Werbung"),

    # --- Frankfurt / Rhein-Main ---
    ("Neopol Film", "https://www.neopol-film.de/",
     "Kino, Serie & Doku aus Frankfurt", "Frankfurt / Rhein-Main"),
    ("ACHT Studio", "https://www.acht.studio/",
     "VFX & Postproduktion für Kino, TV und Werbung, Frankfurt/Hamburg", "Frankfurt / Rhein-Main"),
    ("4REEL", "https://www.4reel.com/",
     "Werbung, Doku & Social – Frankfurt/Rhein-Main", "Frankfurt / Rhein-Main"),

    # --- Branchen-Jobboersen ---
    ("DWDL.jobs Köln", "https://www.dwdl.de/jobboerse/ort_koeln.html",
     "Medien-Jobbörse, alle Stellen in Köln (ca. 40+) – deckt auch Firmen ohne eigene Jobseite ab", "Branchen-Jobbörsen"),
    ("DWDL.jobs Frankfurt", "https://www.dwdl.de/jobboerse/ort_Frankfurt.html",
     "Medien-Jobbörse, alle Stellen in Frankfurt – u. a. hr (Grimme-Preis 2026 für den Frankfurter Tatort)", "Branchen-Jobbörsen"),
]

SUGGESTION_GROUPS = [
    "Köln – Serien, Film & Streaming",
    "Köln – Sender & Studios",
    "Köln – Postproduktion, Technik & Werbung",
    "Frankfurt / Rhein-Main",
    "Branchen-Jobbörsen",
]


def open_suggestions(existing_sources):
    names = {s.name.lower() for s in existing_sources}
    urls = {s.career_url.rstrip("/").lower() for s in existing_sources}
    return [
        {"name": name, "url": url, "note": note, "group": group}
        for name, url, note, group in SUGGESTED_COMPANIES
        if name.lower() not in names and url.rstrip("/").lower() not in urls
    ]
