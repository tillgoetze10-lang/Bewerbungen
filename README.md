# Bewerbungs-Board

Sammelt automatisch passende Stellen (Video, Film, Postproduktion, Set) und
gibt dir ein Board, auf dem du sie bewertest und deine Bewerbungen
vorbereitest: Aufgaben, Voraussetzungen, geforderte Unterlagen,
Ansprechpartner, Anschreiben und deine Dokumente an einem Ort.

## Starten (macOS)

**Doppelklick auf `start.command`.** Beim allerersten Mal richtet das Skript
alles selbst ein. Falls macOS warnt: Rechtsklick → „Öffnen“. Danach öffnet
sich der Browser von selbst (http://127.0.0.1:8765).

- Updates holt `start.command` bei jedem Start automatisch.
- Läuft die App schon, öffnet ein weiterer Doppelklick einfach den Browser.
- Zum Beenden das Terminal-Fenster schließen.
- Kurz nach dem Start sucht die App automatisch nach neuen Jobs und danach
  stündlich, solange sie läuft.
- Neue Top-Treffer meldet dein Mac mit einer Mitteilung oben rechts.

## So arbeitest du damit

1. **Board**: Neue Jobs landen in „Neu“, die besten Treffer oben. Eher
   unpassende sind eingeklappt. Karten per Drag & Drop weiterziehen:
   Interessant → In Vorbereitung → Beworben → Rückmeldung.
   „Löschen“ verschiebt ins Archiv, dort geht nichts verloren.
2. **Job anklicken**: Aufgaben, Voraussetzungen und verlangte Unterlagen
   (als Checkliste), Ansprechpartner mit E-Mail-Button, Links zur Anzeige
   und zur Firmen-Website, dazu Felder für Anschreiben und Notizen.
   Verlangte Unterlagen hakst du dort ab. Eine **Anschreiben-Vorlage** fügst du
   mit einem Klick ein, Anrede, Firma und Stelle sind dabei schon ausgefüllt.
3. **Beworben**: Ziehst du eine Karte nach „Beworben“, trägt die App das Datum
   ein. Nach 14 Tagen erscheint oben im Board „Nachfassen fällig“.
   Bewerbungsfristen aus der Anzeige werden erkannt und kurz vorher markiert.
4. **Meine Unterlagen**: Lebenslauf, Zeugnisse usw. einmal hochladen und bei
   jeder Bewerbung mit einem Klick verknüpfen. Dort pflegst du auch deine
   Anschreiben-Vorlagen mit Platzhaltern wie `{anrede}` und `{firma}`.
5. **Firmen**: Karriereseiten von Produktionsfirmen und Sendern eintragen. Sie
   werden bei jeder Suche mit durchsucht. Eine Vorschlagsliste mit Film- und
   TV-Firmen in Köln lässt sich per Klick übernehmen.
6. **Einstellungen**: Suchbegriffe und Orte, Quellen an/aus, API-Schlüssel.
7. **Status**: Zeigt, ob jede Quelle funktioniert. Bei einem echten Fehler
   erscheint oben ein roter Balken. Klick auf **„Für Claude kopieren“** und
   den Text im Chat einfügen, die Reparatur übernimmt Claude.

Jobs von LinkedIn und anderen Seiten: **„+ Job hinzufügen“ → Link einfügen.**
Alles Weitere wird automatisch ausgelesen.

## Quellen

| Quelle | Wie | Hinweis |
|---|---|---|
| **Adzuna** | offizielle API | **wichtigste Quelle**, kostenloser Schlüssel: https://developer.adzuna.com |
| **Jooble** | offizielle API | kostenloser Schlüssel auf Anfrage: https://jooble.org/api/about |
| **Crew United** | öffentliche Jobliste | Film/TV-Branche |
| **Google Jobs** | über SerpApi | Schlüssel nötig, kostenpflichtig, max. 1× täglich abgefragt |
| **Firmen-Karriereseiten** | öffentliche Seite der Firma | du trägst die Firmen ein |
| **Indeed / StepStone** | standardmäßig **aus** | blockieren automatische Abfragen (HTTP 403 bzw. Zeitüberschreitung). Jobs per Link-Import eintragen |
| **LinkedIn** | nur Link-Import | Nutzungsbedingungen verbieten automatische Abfragen |
| **Jobbörse der Arbeitsagentur** | nur Link-Import | Nutzungsbedingungen untersagen automatisierte Abfragen, die Schnittstelle antwortet mit 403 |

Regeln, damit die App auf der sicheren Seite bleibt: Sie respektiert
`robots.txt`, umgeht keinen Bot-Schutz, wartet zwischen zwei Anfragen an
dieselbe Seite und nutzt, wo es geht, offizielle Schnittstellen.
Blockiert eine Seite, steht sie auf der Status-Seite gelb als „blockiert“.
Das ist kein Fehler.

## Wie bewertet wird (`app/matching.py`)

- **Beruf**: eine Liste von Film-/Video-Berufen, vom Setrunner bis zum
  Colorist. Mehrdeutige Titel wie „Runner“, „Account Manager“ oder
  „Produktionsleitung“ zählen nur mit Film-/Video-Bezug in der Anzeige.
  Jobs ganz ohne Bezug werden gar nicht erst übernommen.
- **Ort**: Köln und direktes Umland (Hürth, Frechen, Pulheim, Bergisch Gladbach,
  Leverkusen, Brühl) passen immer. Frankfurt am Main nur mit Set- oder
  Produktionsbezug. Überall sonst nur zeitlich begrenzte Einsätze wie
  Drehtage, Freelance oder befristete Verträge. Remote passt auch.
- Ergebnis: **Top-Treffer / Prüfen / Eher unpassend** mit Begründung.
  Verbesserte Regeln gelten beim nächsten Start auch für schon gespeicherte Jobs.

## Für Entwicklung

```bash
.venv/bin/python -m unittest discover -s tests -t .   # Tests (ohne Internet, Quellen simuliert)
NO_AUTO_BROWSER=1 .venv/bin/python run.py            # Start ohne Browser
.venv/bin/python -m app.fetch_jobs                   # einen Suchlauf im Terminal
```

- Daten: `data/app.db` (SQLite) und `data/uploads/`. Beides ist nicht im
  Git-Repo, das sind deine persönlichen Dateien.
- Neue Spalten werden beim Start automatisch nachgerüstet (`app/db_setup.py`),
  vorhandene Daten bleiben erhalten.
- Technische Optionen in `config.yaml`: Suchintervall, Suche beim Start,
  Details auslesen, Timeout.
