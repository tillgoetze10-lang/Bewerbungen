# Bewerbungs-Board

Ein selbst gehostetes Tool, das neue Stellenanzeigen sammelt und dir ein
Kanban-Board ("Scrum-Board") gibt, um sie zu bewerten und Bewerbungen
vorzubereiten (Anschreiben, Lebenslauf, Notizen - alles an einem Ort).

## Schnellstart (macOS, empfohlen)

Einmalig: `start.command` im Finder doppelklicken (Rechtsklick &rarr; "Oeffnen",
falls macOS beim ersten Mal wegen "unbekannter Entwickler" warnt). Das
Skript richtet beim allerersten Start automatisch alles ein (virtuelle
Umgebung, Abhaengigkeiten, `config.yaml`) und startet danach die App - der
Browser oeffnet sich von selbst auf http://127.0.0.1:5000.

Ab dann reicht fuer jeden weiteren Start wirklich nur noch: **Doppelklick
auf `start.command`.** Zum Beenden einfach das Terminal-Fenster schliessen,
das sich dabei oeffnet.

`start.command` holt sich bei jedem Start automatisch den neuesten Stand aus
Git (`git pull --ff-only`), bevor die App laeuft - du musst also nicht
selbst an Updates denken. Klappt der Pull mal nicht (z.B. offline), startet
es einfach mit dem vorhandenen Stand weiter, statt abzubrechen.

(Der Rest dieser README beschreibt den manuellen Weg per Terminal - nuetzlich
zum Verstehen, was im Hintergrund passiert, oder falls du z.B. auf Windows/Linux
oder einem Server ohne Doppelklick arbeitest.)

## Was es kann

- **Board:** Spalten `Neu -> Interessant -> In Vorbereitung -> Beworben -> Rueckmeldung erhalten`.
  Neue Jobs landen automatisch ganz oben in `Neu`.
- **Bewerten:** Jobs per Klick in eine andere Spalte schieben oder archivieren ("Loeschen" = Archiv, nichts geht verloren; endgueltiges Loeschen im Archiv moeglich).
- **Job-Detailseite:** Anschreiben-Textfeld, Notizen, Original-Link, verknuepfte Dokumente.
- **Meine Unterlagen:** zentrale Ablage fuer Lebenslauf, Anschreiben-Vorlagen, Zeugnisse - einmal hochladen, bei jeder Bewerbung verknuepfen.
- **Automatische Suche:** eingebauter Hintergrund-Scheduler durchsucht in konfigurierbarem Abstand mehrere Quellen nach deinen Suchprofilen (Suchbegriff + Ort).
- **Schnell hinzufuegen (Link):** einzelnen Job-Link einfuegen (z.B. von LinkedIn), das Tool liest Titel/Firma/Beschreibung selbst aus.
- **Firmen-Karriereseiten (`/firmen`):** eigene Firmen (Produktionsfirmen, Agenturen, Sender...) mit Link zur Karriereseite hinterlegen. Der Button "Jetzt nach neuen Jobs suchen" durchsucht dann Jobportale **und** alle hinterlegten Firmenseiten in einem Durchgang.
- **Automatische Ersteinschaetzung:** jeder gefundene Job wird direkt nach Berufsbild + Standort-Strategie bewertet (Top-Treffer / Pruefen / Eher unpassend) - siehe naechster Abschnitt.
- **Automatische Detail-Extraktion:** Ansprechpartner (Name/E-Mail/Telefon), Firmen-Website, Voraussetzungen und geforderte Bewerbungsunterlagen werden direkt aus der Anzeige gezogen - inkl. ehrlicher Anzeige, was NICHT gefunden wurde (siehe naechster Abschnitt).
- **Drag & Drop:** Karten lassen sich im Board direkt zwischen den Spalten verschieben (per Maus), alternativ geht's weiterhin per Dropdown auf der Karte.
- **Status-Seite (`/status`):** protokolliert dauerhaft, ob jede Quelle beim letzten Lauf funktioniert hat oder nicht - siehe naechster Abschnitt.

## Status-Seite: musst du nicht selbst Fehler verstehen

`/status` zeigt fuer jede Quelle (Portale + jede hinterlegte Firma) den
letzten Lauf: **OK** oder **Fehler** + Klartext-Grund + Zeitpunkt. Das wird
bei jedem Fetch-Lauf in der Datenbank protokolliert (`ScraperRun` in
`app/models.py`), nicht nur fluechtig als Flash-Meldung direkt nach dem
Klick - du kannst also auch Tage spaeter noch nachschauen.

**Falls etwas kaputt ist, musst du die Meldung nicht selbst verstehen:**
auf `/status` gibt es einen Button "Text kopieren", der eine fertige
Diagnose aller Quellen erzeugt. Den einfach in den Chat mit Claude
einfuegen - Claude repariert dann den betroffenen Scraper (z.B. wenn eine
Jobboerse ihr Seitenlayout geaendert hat oder neuen Bot-Schutz aktiviert
hat).

Wichtig zu wissen: Claude kann nicht dauerhaft auf deinem Rechner
mitlaufen oder von selbst merken, wenn eine Quelle kaputt geht - dafuer
braucht es einen kurzen Check von dir (z.B. einmal pro Woche `/status`
oeffnen) und die Diagnose in den Chat kopieren.

## Automatische Detail-Extraktion (Ansprechpartner, Voraussetzungen, Unterlagen)

Fuer jeden neu gefundenen Job ruft das Tool zusaetzlich die einzelne
Anzeigen-Seite ab (`app/extraction.py`) und versucht daraus zu lesen:

- **Ansprechpartner** (Name, E-Mail, Telefon) - per Muster wie "Ansprechpartner:", "Kontakt:" + E-Mail-/Telefon-Regex
- **Firmen-Website** - aus schema.org-Daten, falls die Seite `hiringOrganization.url`/`sameAs` ausliefert
- **Voraussetzungen** - aus schema.org-Feldern (`qualifications`, `skills`, ...) oder, falls nicht vorhanden, aus dem Textabschnitt unter Ueberschriften wie "Dein Profil"/"Anforderungen"
- **Geforderte Bewerbungsunterlagen** - Abgleich gegen Stichwoerter (Anschreiben, Lebenslauf, Zeugnisse, Arbeitsproben/Portfolio, Gehaltsvorstellung, Eintrittstermin)

**Das ist Text-Heuristik, kein Verstehen der Anzeige - und wird nie 100%
treffen.** Deshalb "beobachtet" das Tool sich dabei selbst so ehrlich wie
moeglich, statt falsche Sicherheit vorzutaeuschen:

- Jeder Job bekommt eine **Confidence-Einstufung** (Vollstaendig / Teilweise / Unsicher), sichtbar als farbige Box auf der Detailseite.
- Felder, die NICHT automatisch gefunden wurden, werden explizit aufgelistet ("bitte pruefen/ergaenzen").
- Alle Felder sind direkt im UI von Hand korrigierbar (kein Datenbank-Zugriff noetig).
- Button "Erneut extrahieren" auf der Detailseite ruft die Anzeige nochmal ab, falls sie sich geaendert hat oder die erste Extraktion nichts fand.

Anpassen/erweitern (z.B. weitere Kontakt-Phrasen oder Unterlagen-Stichwoerter): `app/extraction.py`.

Neue Job-Detailabrufe bedeuten mehr Requests pro Fetch-Lauf (ein zusaetzlicher
Abruf pro neu gefundenem, passendem Job - nicht pro Suchergebnis). Falls das
bei einer Quelle zu Bot-Schutz fuehrt, in `config.yaml` global abschalten:
`fetch_job_details: false` (dann bleiben Titel/Ort/Firma/Beschreibung wie
gehabt, aber ohne die Zusatzfelder).

## Automatische Bewertung (Berufsbild + Standort)

Damit das Firmen-Crawling nicht jede Stelle einer Firma ins Board kippt und
du auf einen Blick siehst, was wirklich relevant ist, bewertet
`app/matching.py` jeden Job automatisch. **Das ist nur eine Empfehlung -
es wird nichts automatisch geloescht oder versteckt, du entscheidest im
Board weiter selbst per Klick.**

**Berufsbezeichnungen:** eine Liste aus Video-/Filmberufen (Produktion &
Aufnahmeleitung, Kamera & Videografie, Postproduktion & Schnitt, Licht &
Grip, Motion Design, sowie die agenturtypischen Rollen wie Video Producer,
Content Creator, Junior Producer, Account Manager Video, Art/Creative
Director etc.). Jobs von Firmen-Karriereseiten, die zu **keiner** dieser
Bezeichnungen passen, werden gar nicht erst importiert. Liste erweitern:
`JOB_TITLE_TAXONOMY` in `app/matching.py`.

**Standort-Strategie** (nach deiner Vorgabe):
- **Köln** ist der geplante Zielort -> immer volle Punktzahl, unabhaengig vom Level.
- **Frankfurt** nur interessant, wenn die Anzeige erkennbar mit Set-/Produktionsarbeit
  zu tun hat (Stichwoerter wie "Dreh", "Set", "Produktion", "Postproduktion" etc.) -
  reine Buero-/Marketing-Videojobs in Frankfurt werden niedrig bewertet.
- **Alle anderen Orte** nur interessant, wenn die Anzeige nach einem zeitlich
  begrenzten Set-Einsatz klingt (Stichwoerter wie "befristet", "Drehtage",
  "Tagesgage", "Freelance", "Projekteinsatz" etc.) - laut deiner Vorgabe sind
  1-2 Wochen an einem Set irgendwo völlig ok, ein dauerhafter Umzug dorthin nicht.

Das ist Stichwort-basiert und daher nicht perfekt (ein Job ohne diese
Woerter in der Beschreibung landet im Zweifel bei "Pruefen" statt "Top" -
lieber einmal zu viel selbst nachschauen als einen guten Job automatisch
verstecken). Anpassen: `TARGET_CITY_TERMS`, `CONDITIONAL_CITY_TERMS`,
`FILM_SET_SIGNALS`, `TEMP_SIGNALS` in `app/matching.py`.

Auf jeder Job-Karte steht ein Badge (Top-Treffer / Pruefen / Eher
unpassend + Prozent-Score), auf der Detailseite zusaetzlich die
ausformulierte Begruendung. Die Spalte "Neu" ist nach Score sortiert,
sodass die vielversprechendsten neuen Treffer ganz oben stehen.

## Wichtiger rechtlicher Hinweis zu den Quellen

Automatisiertes Scraping ist nicht bei jeder Seite gleich unproblematisch:

| Quelle | Ansatz in diesem Tool |
|---|---|
| **Indeed** | Best-effort: liest die schema.org/JobPosting-Daten von den oeffentlichen Suchergebnisseiten. Kann durch Bot-Schutz blockiert werden. |
| **StepStone** | Gleicher Ansatz wie Indeed. StepStone nutzt haeufig aktiven Bot-Schutz (Cloudflare o.ae.) - kann fehlschlagen. |
| **Crew United** | Best-effort-Scraper, ungetestet (siehe `app/scrapers/crewunited.py`), da diese Umgebung beim Bauen keinen Internetzugriff auf die Seite hatte. Selektoren ggf. manuell anpassen. |
| **Google Jobs** | Keine automatische Massenabfrage von Google selbst (zu fragil/riskant). Optional ueber den Drittanbieter [SerpApi](https://serpapi.com/google-jobs-api) (eigener API-Key noetig, kostenpflichtig ab gewissem Volumen). |
| **LinkedIn** | **Bewusst nicht automatisiert durchsucht.** LinkedIns Nutzungsbedingungen untersagen Scraping explizit, und LinkedIn geht aktiv/rechtlich dagegen vor. Nutze stattdessen "Schnell hinzufuegen (Link)" fuer einzelne Anzeigen, die du dir selbst im Browser angeschaut hast - das ist ein einzelner, von dir ausgeloester Abruf, kein automatisiertes Crawling. |
| **Firmen-Karriereseiten** | Rechtlich unkritischer als die grossen Portale: es ist die eigene, oeffentliche Seite der Firma, die aktiv fuer offene Stellen wirbt - kein Drittanbieter-Marktplatz mit restriktiven ToS. Trotzdem: nur eigene, ordentlich gepflegte Firmenlisten eintragen (kein Massen-Crawling fremder Listen), moderates Abfrageintervall lassen (Standard: 1x/Stunde ueber den Scheduler) und bei `robots.txt`-Sperren einer Seite diese respektieren statt zu umgehen. |

**robots.txt wird technisch durchgesetzt, nicht nur empfohlen:** vor jedem
automatisierten Abruf (Suchergebnisseiten, Firmen-Karriereseiten) prueft
`app/scrapers/http_utils.py` die robots.txt der Zielseite fuer unseren
User-Agent und bricht den Abruf ab, wenn sie es untersagt (siehe
`_robots_allowed`). Nur der Einzel-Import per Link ("Schnell hinzufuegen")
ist davon ausgenommen, weil dort du selbst genau eine Seite abrufst, die du
dir angeschaut hast - das ist kein automatisiertes Crawling, an das sich
robots.txt richtet.

Wenn eine automatisierte Quelle blockiert wird, bricht das Tool nicht ab,
sondern loggt eine Warnung und macht mit den anderen Quellen weiter. Du
siehst Fehler/Warnungen auch als Meldung im Web-UI nach "Jetzt nach neuen
Jobs suchen".

**Diese Sandbox-Umgebung, in der die App gebaut wurde, hatte keinen Internetzugriff
auf die genannten Jobbörsen** (nur auf ein paar Paketregistries). Die Scraper
sind deshalb nach bestem Wissen implementiert, aber **auf deinem eigenen Rechner
noch nicht live gegen die echten Seiten getestet worden.** Nach dem ersten Lauf
bitte pruefen, ob sinnvolle Ergebnisse kommen, und bei Bedarf die Selektoren in
`app/scrapers/*.py` anpassen (die Fehlermeldungen im UI sagen dir, welche Quelle
Probleme macht).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp config.example.yaml config.yaml
# config.yaml anpassen: Suchbegriffe, Orte, welche Quellen aktiv sind
```

`config.yaml` steuert:
- `search_profiles`: eine Liste aus `keywords` + `location` (mehrere moeglich, z.B. verschiedene Jobtitel/Staedte)
- `sources`: welche Quelle aktiv ist
- `serpapi_key`: optional, fuer Google Jobs
- `fetch_interval_minutes`: wie oft der eingebaute Scheduler automatisch sucht (0 = aus, dann Cron nutzen)

## Starten

```bash
python run.py
```

`run.py` oeffnet automatisch den Standard-Browser auf http://127.0.0.1:5000,
sobald der Server steht (genau das macht auch `start.command`). Falls das
mal nicht gewuenscht ist (z.B. auf einem Server ohne Desktop), mit
`NO_AUTO_BROWSER=1 python run.py` starten.

Der eingebaute Scheduler sucht danach automatisch im konfigurierten Abstand
nach neuen Jobs, solange die App laeuft. Zusaetzlich gibt es im UI oben den
Button "Jetzt nach neuen Jobs suchen" fuer einen manuellen Lauf.

### Alternative: Suche per Cron/Taskplaner statt Dauerbetrieb

Falls die App nicht dauerhaft laufen soll, `fetch_interval_minutes: 0` setzen
und stattdessen z.B. per Cron alle 30 Minuten aufrufen:

```bash
*/30 * * * * cd /pfad/zu/Bewerbungen && .venv/bin/python -m app.fetch_jobs
```

## Daten & Dateien

- SQLite-Datenbank: `data/app.db` (wird beim ersten Start automatisch angelegt)
- Hochgeladene Dokumente: `data/uploads/`
- Beides ist in `.gitignore` und wird nicht eingecheckt - das sind deine persoenlichen Daten (Lebenslauf etc.), die sollten nicht ins Git-Repo.

## Naechste sinnvolle Ausbaustufen (nicht Teil dieser Basis)

- Deployment auf einem eigenen Server/NAS, damit die App wirklich rund um die Uhr laeuft
- E-Mail-/Push-Benachrichtigung bei neuen interessanten Treffern
- Volltextsuche/Filter im Board (nach Ort, Gehalt, Stichwort)
- Login/Passwortschutz, falls die App aus dem lokalen Netz erreichbar gemacht wird
