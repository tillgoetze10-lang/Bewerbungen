"""Vorschlagsliste: Film-/TV-Firmen im Raum Koeln mit Karriereseite.

Recherchiert im September 2026. Seiten koennen sich aendern - ob eine Seite
auslesbar ist, zeigt nach dem ersten Suchlauf die Status-Seite. Firmen, die
keine eigene Jobseite haben, laufen ueber ihre Seite bei DWDL.jobs
(Medien-Jobboerse).
"""

SUGGESTED_COMPANIES = [
    ("MMC Studios Köln", "https://mmc.de/unternehmen/karriere/", "Film- & TV-Studios, Köln-Ossendorf"),
    ("nobeo / Gravity Media", "https://nobeo.de/category/jobs/", "TV-Studios & Postproduktion, Hürth"),
    ("filmpool entertainment", "https://jobs.filmpool-entertainment.de/de/jobs", "TV-Produktion, Hürth/Köln"),
    ("UFA Serial Drama", "https://www.dwdl.de/jobboerse/firma_ufaserialdrama.html", "Serien, Köln (über DWDL.jobs)"),
    ("Bavaria Fiction", "https://www.dwdl.de/jobboerse/firma_bavariafictiongmbh.html", "Fiction, u. a. Köln (über DWDL.jobs)"),
    ("ITV Studios Germany", "https://www.itvstudios.de/karriere", "Entertainment & Factual, Köln"),
    ("Banijay Germany", "https://banijay.de/karriere.html", "u. a. Brainpool, Endemol Shine, Köln"),
    ("Brainpool", "https://brainpool.de/karriere/", "Comedy & Show, Köln"),
    ("i&u Studios", "https://www.iustudios.de/karriere", "Dokus & Reportagen, Köln"),
    ("btf bildundtonfabrik", "https://btf-gmbh.jobs.personio.de/", "Fiction, Shows, Werbung, Köln"),
    ("WDR mediagroup", "https://wdr-mediagroup.com/de/karriere", "Produktion & Vermarktung, Köln"),
    ("RTL Deutschland", "https://jobsearch.createyourowncareer.com/RTL/content/search/?locale=de_DE", "Sender, Köln"),
    ("DWDL.jobs (Medien-Jobbörse)", "https://www.dwdl.de/jobboerse/", "Branchen-Jobbörse für TV & Medien"),
]


def open_suggestions(existing_sources):
    names = {s.name.lower() for s in existing_sources}
    urls = {s.career_url.rstrip("/").lower() for s in existing_sources}
    return [
        {"name": name, "url": url, "note": note}
        for name, url, note in SUGGESTED_COMPANIES
        if name.lower() not in names and url.rstrip("/").lower() not in urls
    ]
