# Bewerbungs-Board

Ein selbst gehostetes Tool, das neue Stellenanzeigen sammelt und dir ein
Kanban-Board ("Scrum-Board") gibt, um sie zu bewerten und Bewerbungen
vorzubereiten (Anschreiben, Lebenslauf, Notizen - alles an einem Ort).

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

Dann im Browser: http://127.0.0.1:5000

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
